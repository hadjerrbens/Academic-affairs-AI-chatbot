"""The agent loop: turns a student's question into a grounded answer.

Dependencies from other members are INJECTED (see wiring_example.py):
  retrieve(query, area)  -> list[{"text": str, "source": str}]   M5's retrieve_with_context
  keyword_route(text)    -> {"primary": label, "secondary": label|None}   M5's keyword router
  save_turn(...)         -> awaitable                              stores the turn

Events yielded by handle(): meta, delta, tool, citations, confirm, done, error."""
from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

from app.core.labels import (
    ALL_ROUTES, AREA_LABELS, AREAS_WITH_DOCS, LABEL_DESCRIPTIONS, OUT_OF_SCOPE, SMALLTALK,
)
from app.core.llm import BudgetExceeded, LLMError, LLMUnavailable, RateLimitExceeded
from app.core.tools import ToolContext, ToolRegistry
from app.services import chat_prompts as prompts

log = logging.getLogger(__name__)

MAX_INPUT_CHARS = 1000
MAX_TOOL_ROUNDS = 4
MIN_TURN_TOKENS = 4000  # below this much budget left we go straight to degraded mode
ANSWER_MAX_TOKENS = 1500

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INJECTION = re.compile(
    r"(ignore|forget|disregard)\s+(all\s+|any\s+|the\s+)?(previous|prior|above|your)\s+(instructions|rules|prompt)"
    r"|system\s+prompt|you\s+are\s+now|reveal\s+(your|the)\s+(prompt|instructions)",
    re.IGNORECASE,
)
_CITATION = re.compile(r"\[source\s*(\d+)\]", re.IGNORECASE)


# ----------------------------------------------------------------- helpers
@dataclass
class CleanInput:
    text: str
    flagged: bool


def clean_input(raw: str, max_len: int = MAX_INPUT_CHARS) -> CleanInput:
    text = _CONTROL_CHARS.sub("", str(raw or "")).strip()[:max_len]
    return CleanInput(text=text, flagged=bool(_INJECTION.search(text)))


def ground_citations(answer: str, n_sources: int) -> tuple[str, list[int]]:
    """Drop every [source N] marker that has no matching source. Returns (clean answer, cited numbers)."""
    cited: list[int] = []

    def keep_or_drop(match: re.Match) -> str:
        n = int(match.group(1))
        if 1 <= n <= n_sources:
            if n not in cited:
                cited.append(n)
            return f"[source {n}]"
        return ""

    cleaned = _CITATION.sub(keep_or_drop, answer)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).replace(" .", ".").strip()
    return cleaned, cited


class RateLimiter:
    """At most max_calls messages per session in a sliding window."""

    def __init__(self, max_calls: int = 10, window: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.max_calls, self.window, self._clock = max_calls, window, clock
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.max_calls:
            return False
        hits.append(now)
        return True


class InMemoryTurnStore:
    """Default save_turn. Replace with a MongoDB-backed function."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []

    async def save_turn(self, session_id, user_id, question, answer, tokens, meta) -> None:
        self.turns.append({"session_id": session_id, "user_id": user_id, "question": question,
                           "answer": answer, "tokens": tokens, "meta": meta})


def _event(name: str, data: Any) -> dict:
    return {"event": name, "data": data}


def _no_retrieval(query: str, area: str) -> list[dict]:
    return []


def _no_keyword_route(text: str) -> dict:
    return {"primary": OUT_OF_SCOPE, "secondary": None}


# ------------------------------------------------------------------ service
class ChatService:
    def __init__(
        self,
        llm,
        registry: ToolRegistry,
        *,
        retrieve: Callable[[str, str], list[dict]] = _no_retrieval,
        keyword_route: Callable[[str], dict] = _no_keyword_route,
        save_turn: Callable[..., Awaitable[None]] | None = None,
        rate_limiter: RateLimiter | None = None,
        areas_with_docs=AREAS_WITH_DOCS,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.retrieve = retrieve
        self.keyword_route = keyword_route
        self.save_turn = save_turn or InMemoryTurnStore().save_turn
        self.rate_limiter = rate_limiter or RateLimiter()
        self.areas_with_docs = set(areas_with_docs)

    # ---------------------------------------------------------- routing
    async def _route(self, text: str) -> tuple[dict, bool]:
        """Returns (route, llm_unusable). Tries the router model, falls back to M5's keyword router."""
        messages = [{"role": "system", "content": prompts.ROUTER_PROMPT}, {"role": "user", "content": text}]
        try:
            result = await self.llm.complete_json(messages, max_tokens=1024)
            primary, secondary = result.get("primary"), result.get("secondary")
            if primary not in ALL_ROUTES:
                raise ValueError("router returned an unknown label")
            if secondary not in AREA_LABELS or secondary == primary:
                secondary = None
            return {"primary": primary, "secondary": secondary}, False
        except Exception as exc:  # bad JSON, unknown label, Groq problems: use the keyword router
            log.warning("LLM routing failed (%s); using keyword router", exc)
            # Only "the LLM is not available" failures mean degraded mode. A bad JSON answer does not.
            unavailable = isinstance(exc, (BudgetExceeded, RateLimitExceeded, LLMUnavailable))
            return self._keyword(text), unavailable

    def _keyword(self, text: str) -> dict:
        try:
            route = self.keyword_route(text)
            primary = route.get("primary")
            if primary not in ALL_ROUTES:
                primary = OUT_OF_SCOPE
            secondary = route.get("secondary")
            return {"primary": primary, "secondary": secondary if secondary in AREA_LABELS else None}
        except Exception:
            log.exception("keyword router failed")
            return {"primary": OUT_OF_SCOPE, "secondary": None}

    # ----------------------------------------------------- static texts
    @staticmethod
    def _refusal() -> str:
        topics = "; ".join(LABEL_DESCRIPTIONS.values())
        return f"I can only help with academic affairs: {topics}. Please ask me about one of these."

    @staticmethod
    def _greeting() -> str:
        return "Hello! I can help with grading, transcripts, GPA, exams and other academic questions."

    # --------------------------------------------------- degraded mode
    async def _degraded(self, route: dict, ctx: ToolContext):
        """No LLM: run the routed tool directly and return its summary. The numbers still work."""
        for tool in self.registry.tools_for_areas([route["primary"]]):
            if not tool.safe_without_llm or not (tool.public or ctx.authenticated):
                continue
            result = await self.registry.execute(tool.name, {}, ctx)
            ok = "error" not in result
            yield _event("tool", {"name": tool.name, "ok": ok})
            if ok and isinstance(result.get("summary"), str):
                yield _event("_answer", f"{result['summary']}\n\n{prompts.DEGRADED_NOTE}")
                return
        yield _event("_answer", f"Sorry, I cannot answer that right now. {prompts.DEGRADED_NOTE}")

    # -------------------------------------------------------- tool loop
    async def _tool_loop(self, messages: list[dict], specs: list[dict], ctx: ToolContext):
        offered = {s["function"]["name"] for s in specs}
        for _ in range(MAX_TOOL_ROUNDS):
            msg = await self.llm.complete_message(
                messages, temperature=0.1, max_tokens=ANSWER_MAX_TOKENS, tools=specs or None
            )
            calls = msg.get("tool_calls") or []
            if not calls:
                yield _event("_answer", msg.get("content") or "")
                return
            # Send back only the fields the API needs (models may add extra ones such as "reasoning").
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for call in calls:
                fn = call.get("function") or {}
                name = fn.get("name", "")
                if name in offered:
                    result = await self.registry.execute(name, fn.get("arguments"), ctx)
                else:  # the model asked for a tool we did not offer this turn
                    result = {"error": "unknown_tool", "message": f"Tool '{name}' is not available."}
                yield _event("tool", {"name": name, "ok": "error" not in result})
                if result.get("requires_confirmation"):
                    yield _event("confirm", {
                        "action_id": result.get("action_id"),
                        "summary": result.get("summary"),
                        "fee": result.get("fee"),
                        "estimated_days": result.get("estimated_days"),
                    })
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
        # Still asking for tools after the last round: force a final answer without tools.
        msg = await self.llm.complete_message(messages, temperature=0.1, max_tokens=ANSWER_MAX_TOKENS)
        yield _event("_answer", msg.get("content") or "")

    # ------------------------------------------------------------ a turn
    async def _turn(self, text: str, flagged: bool, ctx: ToolContext, history: list[dict], meta: dict):
        degraded = not await self.llm.budget.can_use(MIN_TURN_TOKENS)
        if degraded:
            route = self._keyword(text)
        else:
            route, degraded = await self._route(text)
        meta.update(route, degraded=degraded)
        yield _event("meta", dict(meta))

        primary, secondary = route["primary"], route["secondary"]

        if primary == OUT_OF_SCOPE:
            yield _event("_answer", self._refusal())
            return

        if primary == SMALLTALK:
            reply = self._greeting()
            if not degraded:
                try:
                    msg = await self.llm.complete_message(
                        [{"role": "system", "content": prompts.SMALLTALK_PROMPT},
                         {"role": "user", "content": text}], temperature=0.3, max_tokens=300)
                    reply = msg.get("content") or reply
                except LLMError:
                    pass
            yield _event("_answer", reply)
            return

        areas = [a for a in (primary, secondary) if a]
        if self.registry.needs_login(areas, ctx.authenticated):
            yield _event("_answer", prompts.LOGIN_PROMPT)
            return

        if degraded:
            async for ev in self._degraded(route, ctx):
                yield ev
            return

        specs = self.registry.specs_for(areas, ctx.authenticated)

        passages: list[dict] = []
        for area in areas:
            if area in self.areas_with_docs:
                try:
                    passages.extend(self.retrieve(text, area))
                except Exception:
                    log.exception("retrieval failed for %s", area)
        sources = "\n".join(f"[source {i}] {p.get('text', '')}" for i, p in enumerate(passages, 1)) or "(none)"
        system = prompts.ANSWER_PROMPT.format(
            extra=prompts.INJECTION_WARNING if flagged else "", sources=sources)
        messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": text}]

        answer = ""
        try:
            async for ev in self._tool_loop(messages, specs, ctx):
                if ev["event"] == "_answer":
                    answer = ev["data"]
                else:
                    yield ev
        except LLMError as exc:  # budget gone or Groq down in the middle of the turn
            log.warning("LLM failed during the turn (%s); degraded answer", exc)
            meta["degraded"] = True
            async for ev in self._degraded(route, ctx):
                yield ev
            return

        answer, cited = ground_citations(answer, len(passages))
        if not answer:
            answer = "Sorry, I could not produce an answer. Please rephrase your question."
        if cited:
            yield _event("citations", [{"n": n, "source": passages[n - 1].get("source")} for n in cited])
        yield _event("_answer", answer)

    # ------------------------------------------------------- public API
    async def handle(self, session_id: str, ctx: ToolContext, message: str,
                     history: list[dict] | None = None) -> AsyncIterator[dict]:
        clean = clean_input(message)
        if not clean.text:
            yield _event("error", {"code": "empty_message", "message": "Please type a question."})
            return
        if not self.rate_limiter.allow(session_id):
            yield _event("error", {"code": "rate_limited", "message": "Too many messages. Please wait a moment."})
            return

        used_before = await self.llm.budget.used()
        meta: dict[str, Any] = {}
        answer = ""
        try:
            async for ev in self._turn(clean.text, clean.flagged, ctx, history or [], meta):
                if ev["event"] == "_answer":
                    answer = ev["data"]
                    yield _event("delta", answer)
                else:
                    yield ev
        except Exception:
            log.exception("chat turn failed")
            yield _event("error", {"code": "internal", "message": "Something went wrong. Please try again."})
            return

        tokens = (await self.llm.budget.used()) - used_before
        try:
            await self.save_turn(session_id, getattr(ctx.user, "id", None), clean.text, answer, tokens, meta)
        except Exception:
            log.exception("could not save the turn")  # losing a history row must not break the answer
        yield _event("done", {"tokens": tokens})
