import asyncio
import random
from collections.abc import Awaitable
from dataclasses import dataclass
import json
import os
from datetime import date, datetime, timedelta
from typing import Any, Callable, Sequence, Iterator, Iterable, AsyncIterator
import uuid
from dotenv import load_dotenv

load_dotenv()

DEFAULT_ROUTER_MODEL = os.environ.get("GROQ_ROUTER_MODEL", "openai/gpt-oss-20b")
DEFAULT_ANSWER_MODEL = os.environ.get("GROQ_ANSWER_MODEL", "openai/gpt-oss-120b")
DEFAULT_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
DEFAULT_DAILY_TOKEN_BUDGET = int(os.environ.get("GROQ_DAILY_TOKEN_BUDGET", "500000"))
DEFAULT_TIMEOUT = float(os.environ.get("GROQ_TIMEOUT", "30"))
DEFAULT_MAX_RETRIES = int(os.environ.get("GROQ_MAX_RETRIES", "3"))
CHAT_COMPLETIONS_PATH = "/chat/completions"
DEFAULT_MAX_COMPLETION_TOKENS = 1024

class LLMError(RuntimeError):
    pass


class LLMRateLimited(LLMError):
    pass


class LLMUnavailable(LLMError):
    pass


class BudgetExceeded(LLMError):
    pass

class RateLimitExceeded(LLMError):
    def __init__(
            self,
            message: str,
            retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after

class InvalidResponse(LLMError):
    pass


@dataclass
class LLMResult:
    content:str
    tool_calls:list
    usage:int
    model:str

@dataclass
class ToolCall :
    id: str
    name: str
    args: dict



class TokenBudget:
    def __init__(self,limit: int = DEFAULT_DAILY_TOKEN_BUDGET)->None:
        self._daily_limit = int(limit)
        if self._daily_limit < 0:
            raise ValueError("Token budget cannot be negative")

        self._day = date.today()
        self._lock = asyncio.Lock()

        self.used_tokens = 0
        self._calls = 0
        self._reserved_tokens = 0
        # Each request has its own reservation ID.
        # ID -> (reservation date, reserved amount)
        self._reservations: dict[str, tuple[date, int]] = {}


    @property
    def limit(self) -> int:
        return self._daily_limit


    async def calls(self) -> int:
        async with self._lock:
            self._reset_if_new_day()
            return self._calls

    async def used(self) -> int:
        async with self._lock:
            self._reset_if_new_day()
            return self.used_tokens

    def _reset_if_new_day(self) -> None:
        today = date.today()
        if today != self._day:
            self._day = today
            self._reset_counters()

    def _reset_counters(self)-> None:
        self.used_tokens = 0
        self._calls = 0
        self._reserved_tokens = 0

    #ch7al b9alk mn token
    #property so u dont have to call the method remaining() just remaining
    async def remaining(self)->int:
        async with self._lock:
            self._reset_if_new_day()
            if self.limit <= 0:
                return -1
            #max-that u just consumed
            return self._daily_limit-self.used_tokens-self._reserved_tokens

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """token estimate (4 characters per token) only used to *predict* the cost of a call before it happens and to account for streamed responses where the API does not report usage"""
        if not text:
            return 0
        return max(1,(len(text) + 3) // 4)

    def _estimate_messages_tokens(self,messages: Sequence[dict[str, Any]]) -> int:
        #y7sb ch7al kyn total t3 tokens haka estimation kon tkon kol char = 4 token
        total = 0
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            #message over head
            total+=4
        return total


    async def reserve_tokens(self,messages: Sequence[dict[str, Any]],max_completion_tokens: int ) ->str|None:
        if max_completion_tokens < 0:
            raise ValueError("Maximum completion tokens cannot be negative")
        # estimate prompt + maximum possible response.
        estimated_prompt = self._estimate_messages_tokens(messages)
        tokens = estimated_prompt + max_completion_tokens

        if tokens < 0:
            raise ValueError("Tokens cannot be negative")
        async with self._lock:
            self._reset_if_new_day()

            if self.limit > 0:
                available = (self._daily_limit - self.used_tokens - self._reserved_tokens)
                if tokens > available:
                    return None
            reservation_id = uuid.uuid4().hex
            self._reserved_tokens +=tokens
            self._reservations[reservation_id] = (self._day,tokens)
            return reservation_id

    #est ce que t9dr tzi t5dm bih
    async def can_use(self, tokens: int) -> bool:
        if tokens < 0:
            raise ValueError("Tokens cannot be negative")

        async with self._lock:
            self._reset_if_new_day()

            if self._daily_limit == 0:
                return True

            available = (
                    self._daily_limit
                    - self.used_tokens
                    - self._reserved_tokens
            )

            return tokens <= available


    async def record_usage(self, prompt_tokens: int , completion_tokens: int , reservation_id: str):
        if min(prompt_tokens, completion_tokens) < 0:
            raise ValueError("Token counts cannot be negative")
        async with self._lock:
            self._reset_if_new_day()
            reservation = self._reservations.pop(
                reservation_id, None
            )
            if reservation is None:
                raise ValueError("Reservation does not exist")
            reservation_day, reserved_amount = reservation
            # Only subtract if the reservation belongs to today.
            if reservation_day == self._day:
                self._reserved_tokens -= reserved_amount
            self.used_tokens += max(0,int(prompt_tokens)) + max(0,int(completion_tokens))
            #bruh u just called it
            self._calls += 1

    #t3tik description t3 usage day / limit / token used /ch7al b9alk token / ch7all 3yt / winta reset
    async def get_usage(self)-> dict[str,Any]:
        async with self._lock:
            self._reset_if_new_day()
            remaining = (
                self._daily_limit
                - self.used_tokens
                - self._reserved_tokens
                if self.limit > 0
                else -1
            )
            return {
                "day": self._day.isoformat(),
                "limit": self.limit,
                "used": self.used_tokens ,
                "reserved": self._reserved_tokens,
                "remaining":  remaining,
                "calls": self._calls,
                "resets_at": datetime.combine(
                    self._day + timedelta(days=1), datetime.min.time()
                ).isoformat(),
            }

    async def release_reservation(self,reservation_id: str) -> None:
        """Release reserved tokens when a request fails"""
        async with self._lock:
            self._reset_if_new_day()
            reservation = self._reservations.pop(
                reservation_id, None
            )
            if reservation is None:
                raise ValueError("Reservation does not exist")

            reservation_day, reserved_amount = reservation

            if reservation_day == self._day:
                self._reserved_tokens -= reserved_amount
    def estimate_messages_tokens(
            self,
            messages: Sequence[dict[str, Any]]
    ) -> int:
        return self._estimate_messages_tokens(messages)



class HttpxTransport:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        try:
            import httpx
        except ImportError as exc:
            raise LLMError("httpx is not installed. Run: pip install httpx") from exc
        self._httpx = httpx
        self._timeout = timeout

    @staticmethod
    def _lower(headers: Any) -> dict[str, str]:
        return {k.lower(): v for k, v in headers.items()}

    async def request(self, url: str, headers: dict[str, str], body: bytes):
        try:
            async with self._httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=headers, content=body)
        except self._httpx.HTTPError as exc:
            raise LLMUnavailable(f"Network error talking to Groq: {exc}") from exc
        return resp.status_code, self._lower(resp.headers), resp.content

    async def stream(self, url: str, headers: dict[str, str], body: bytes):
        try:
            async with self._httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream("POST", url, headers=headers, content=body) as resp:
                    if resp.status_code != 200:
                        raw = await resp.aread()
                        raise _error_for_status(
                            resp.status_code, self._lower(resp.headers), raw
                        )
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        except self._httpx.HTTPError as exc:
            raise LLMUnavailable(f"Network error talking to Groq: {exc}") from exc






class GroqClient:
    def __init__(self,api_key:str|None=None,base_url:str|None=None,route_model:str|None=None,answer_model:str|None=None,budget:TokenBudget|None=None,transport:Any|None=None,timeout:float = DEFAULT_TIMEOUT,max_retries:int=DEFAULT_MAX_RETRIES,sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.route_model = route_model or DEFAULT_ROUTER_MODEL
        self.answer_model = answer_model or DEFAULT_ANSWER_MODEL
        self.budget = budget if budget is not None else TokenBudget()
        self.transport = transport if transport is not None else HttpxTransport(timeout)
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._sleep = sleep

    async def complete(self,messages:Sequence[dict[str,Any]],model:str|None = None, temperature: float = 0.1,max_tokens : int|None = None,presence_penalty=-1,frequency_penalty=0.5 ,tools: Sequence[dict[str, Any]] | None = None,tool_choice: str | None = None) ->str:
        """Method	Inputs	Output	What it does
complete()	Messages, model, token limit, temperature, optional tools	LLMResult	Sends a request and waits for the complete answer"""
        message = await self.complete_message(
            messages,
            model=model or self.answer_model,
            temperature=temperature,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )
        return message.get("content") or ""

    async def complete_message(self,
                               messages: Sequence[dict[str, Any]],
                               model: str | None = None,
                               temperature: float = 0.1,
                               max_tokens: int | None = None,
                               presence_penalty=-1,
                               frequency_penalty=0.5,
                               tools: Sequence[dict[str, Any]] | None = None,
                               tool_choice: str | None = None) -> dict[str,Any]:

        completion_limit = (
            max_tokens if max_tokens is not None
            else DEFAULT_MAX_COMPLETION_TOKENS
        )
        payload : dict[str,Any] = {
            "model" :  model or self.answer_model,
            "messages" : list(messages),
            "temperature" : temperature,
            "max_tokens":completion_limit,
            "presence_penalty" : presence_penalty,
            "frequency_penalty" : frequency_penalty,
        }
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty
        if frequency_penalty is not None:
            payload["frequency_penalty"] = frequency_penalty
        if tools :
            payload["tools"] = list(tools)
            payload["tool_choice"] = tool_choice or "auto"
        reservation_id = await self.budget.reserve_tokens(
            messages,
            completion_limit
        )

        if not reservation_id:
            raise BudgetExceeded("Daily token budget exhausted.")
        try:
            response = await self._post(payload)
            usage = response.get("usage")
            if not isinstance(usage,dict):
                raise InvalidResponse("Groq response is missing token usage.")
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int):
                raise InvalidResponse("Groq returned invalid token usage.")
        except Exception:
            await self.budget.release_reservation(reservation_id)
            raise
        await self.budget.record_usage(prompt_tokens=prompt_tokens,completion_tokens=completion_tokens,reservation_id= reservation_id)
        choices = response.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise InvalidResponse("Groq response has no choices.")
        return choices[0].get("message") or {}



    def _url(self) -> str:
        return f"{self.base_url}{CHAT_COMPLETIONS_PATH}"

    def _headers(self) -> dict[str,str]:
        if not self.api_key:
            raise LLMError(
                "GROQ_API_KEY is not set. The chatbot cannot call the model "
                "without it; degraded mode will be used instead."
            )
        return {    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                    }

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = self._headers()
        url = self._url()

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                status, resp_headers, raw = await self.transport.request(url, headers, body)
            except LLMUnavailable as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                await self._sleep(self._backoff(attempt))
                continue
            except LLMError:
                raise
            except Exception as exc:  # network hiccup, DNS, timeout
                last_error = exc
                if attempt >= self.max_retries:
                    break
                await self._sleep(self._backoff(attempt))
                continue

            if status == 429:
                last_error = RateLimitExceeded(
                    "Groq rate limit reached (429).", self._retry_after(resp_headers)
                )
                if attempt >= self.max_retries:
                    break
                await self._sleep(
                    self._retry_after(resp_headers) or self._backoff(attempt)
                )
                continue

            if status >= 500:
                last_error = LLMUnavailable(f"Groq server error (HTTP {status}).")
                if attempt >= self.max_retries:
                    break
                await self._sleep(self._backoff(attempt))
                continue

            if status >= 400:
                raise LLMError(
                    f"Groq request failed (HTTP {status}): {_error_message(raw)}"
                )

            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise InvalidResponse(f"Groq returned non-JSON: {raw[:200]!r}") from exc

        if isinstance(last_error, LLMError):
            raise last_error
        raise LLMUnavailable(f"Groq call failed after {self.max_retries + 1} attempts: {last_error}")
    async def stream(
            self,
            messages: Sequence[dict[str, Any]],
            model: str | None = None,
            temperature: float = 0.1,
            presence_penalty=-1,
            frequency_penalty=0.5,
            max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        completion_limit = (
            max_tokens if max_tokens is not None
            else DEFAULT_MAX_COMPLETION_TOKENS
        )
        payload: dict[str, Any] = {
            "model": model or self.answer_model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": completion_limit,
            "presence_penalty" : presence_penalty,
            "frequency_penalty" :frequency_penalty,
            "stream": True,
        }
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty
        if frequency_penalty is not None:
            payload["frequency_penalty"] = frequency_penalty

        reservation_id = await self.budget.reserve_tokens(messages, completion_limit)
        if not reservation_id:
            raise BudgetExceeded(
                f"Daily token budget exhausted ."
            )
        prompt_estimate = self.budget.estimate_messages_tokens(messages)
        parts: list[str] = []
        finished = False
        try:
            async for chunk in self._post_stream(payload):
                parts.append(chunk)
                yield chunk
            finished = True
        finally:
            produced = self.budget.estimate_tokens("".join(parts))
            if finished or produced > 0:
                await self.budget.record_usage(prompt_estimate, produced, reservation_id)
            else:
                await self.budget.release_reservation(reservation_id)


    async def _post_stream( self,payload: dict[str, Any]) -> AsyncIterator[str]:

        body = json.dumps(payload).encode("utf-8")
        headers = self._headers()
        url = self._url()

        last_error: Exception | None = None
        yielded = False

        for attempt in range(self.max_retries + 1):
            try:
                async for text in _aiter_sse(self.transport.stream(url, headers, body)):
                    yielded = True
                    yield text
                return
            except (LLMUnavailable, RateLimitExceeded) as exc:
                last_error = exc

                if yielded or attempt >= self.max_retries:
                    break

                delay = getattr(exc, "retry_after", None) or self._backoff(attempt)
                await self._sleep(delay)

            except LLMError:
                raise

            except Exception as exc:
                last_error = exc

                if yielded or attempt >= self.max_retries:
                    break

                await self._sleep(self._backoff(attempt))

        if isinstance(last_error, LLMError):
            raise last_error

        raise LLMUnavailable(
            f"Groq stream failed after {self.max_retries + 1} attempts: "
            f"{last_error}"
        )


    async def complete_json(
            self,
            messages: Sequence[dict[str, Any]],
            model: str | None = None,
            temperature: float = 0.1,
            max_tokens: int | None = None,
    ) -> dict[str, Any]:

        raw = await self.complete(
            messages,
            model=model or self.route_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        try:
            return _parse_json_object(raw)

        except ValueError as exc:
            repair = list(messages) + [
                {
                    "role": "assistant",
                    "content": raw,
                },
                {
                    "role": "user",
                    "content": (
                        "That was not valid JSON. Reply with the same JSON "
                        "object and nothing else. No prose or code fences."
                    ),
                },
            ]

            repaired = await self.complete(
                repair,
                model=model or self.route_model,
                temperature=0.0,
                presence_penalty=-1,
                frequency_penalty=0.5,
                max_tokens=max_tokens,
            )

            try:
                return _parse_json_object(repaired)

            except ValueError as repair_error:
                raise InvalidResponse(
                    f"Model did not return valid JSON: {repair_error}"
                ) from exc


    @staticmethod
    def _retry_after(headers:dict[str,str])->float | None:
        value = headers.get("retry-after")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            return None

    @staticmethod
    def _backoff(attempt:int)->float:
        return min(2.0**attempt * 0.5, 8.0) + random.uniform(0.0, 0.5)


def _error_message(raw: bytes):
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return raw[:300].decode("utf-8", "replace")
    error = payload.get("error")
    if isinstance(error,dict):
        return str(error.get("message") or error)
    return str(error or payload)[:300]

def _iter_sse(chunks: Iterable[bytes]) -> Iterator[str]:
    buffer = ""
    for chunk in chunks:
        buffer+=chunk.decode("utf-8","replace")
        while "\n" in buffer:
            line , buffer = buffer.split("\n",1)
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if not data:
                continue
            if data == "[DONE]":
                return
            try:
                payload = json.loads(data)
            except ValueError:
                continue
            for choice in payload.get("choices") or []:
                delta =(choice.get("delta") or {}).get("content")
                if delta:
                    yield delta


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a JSON object out of a model response, tolerating fences/prose."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty response")

    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None

    if isinstance(parsed, dict):
        return parsed

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

    raise ValueError(f"no JSON object found in: {text[:200]!r}")


async def _aiter_sse(chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
    buffer = ""
    async for chunk in chunks:
        buffer += chunk.decode("utf-8", errors="replace")

        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()

            # Ignore lines that aren't SSE data.
            if not line.startswith("data:"):
                continue

            data = line[len("data:"):].strip()

            if not data:
                continue
            if data == "[DONE]":
                return

            try:
                payload = json.loads(data)
            except ValueError:
                continue

            for choice in payload.get("choices") or []:
                delta = (choice.get("delta") or {}).get("content")

                if isinstance(delta, str) and delta:
                    yield delta


def _error_for_status(
        status: int,
        headers: dict[str, str],
        raw: bytes
) -> Exception:
    message = _error_message(raw)

    if status == 429:
        retry_after = headers.get("retry-after")
        try:
            retry_value = float(retry_after) if retry_after else None
        except ValueError:
            retry_value = None
        return RateLimitExceeded(
            "Groq rate limit reached.",
            retry_after=retry_value
        )

    if status >= 500:
        return LLMUnavailable(
            f"Groq server error (HTTP {status}): {message}"
        )

    return LLMError(
        f"Groq request failed (HTTP {status}): {message}"
    )