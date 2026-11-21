"""Tool registry. Every feature registers its tools here; the agent loop only asks the registry for
specs and for execution. Rules enforced here (and tested):
  - execute() NEVER raises: it always returns a dict, with an "error" key when something is wrong
  - no tool schema may contain student_id: the student is always taken from ToolContext.user
  - specs_for() returns at most 6 tools, to save tokens
  - huge results are truncated"""
from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterable

log = logging.getLogger(__name__)

MAX_TOOLS_PER_REQUEST = 6
MAX_RESULT_CHARS = 6000
MAX_STRING_ARG_CHARS = 200
FORBIDDEN_PARAMS = frozenset({"student_id"})

_TYPES = {
    "string": str, "integer": int, "number": (int, float),
    "boolean": bool, "object": dict, "array": list,
}


@dataclass
class ToolContext:
    user: Any | None  # None means "not logged in". Tools read the student from here, never from args.
    today: date
    registration_term: str
    current_term: str

    @property
    def authenticated(self) -> bool:
        return self.user is not None


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Any]  # handler(ctx, **args) -> dict, sync or async
    areas: tuple[str, ...]
    public: bool = False  # public tools work without login
    safe_without_llm: bool = False  # may be run directly in degraded mode (no args, no writes)

    def spec(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


def _contains_forbidden(schema: Any) -> bool:
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key in FORBIDDEN_PARAMS or _contains_forbidden(value):
                return True
    elif isinstance(schema, list):
        return any(_contains_forbidden(v) for v in schema)
    return False


def validate_args(schema: dict, args: Any) -> str | None:
    """Tiny JSON-schema subset: required, unknown keys, type, enum. Returns an error text or None."""
    if not isinstance(args, dict):
        return "arguments must be a JSON object"
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in args:
            return f"missing required argument '{key}'"
    for key, value in args.items():
        if key not in props:
            return f"unknown argument '{key}'"
        spec = props[key]
        wanted = spec.get("type")
        if wanted:
            is_bool_for_number = isinstance(value, bool) and wanted in ("integer", "number")
            if is_bool_for_number or not isinstance(value, _TYPES[wanted]):
                return f"argument '{key}' must be of type {wanted}"
        if "enum" in spec and value not in spec["enum"]:
            return f"argument '{key}' must be one of {spec['enum']}"
        if isinstance(value, str) and len(value) > MAX_STRING_ARG_CHARS:
            return f"argument '{key}' is too long"
    return None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # ---- registration
    def add(self, tool: Tool) -> Tool:
        if _contains_forbidden(tool.parameters):
            raise ValueError(f"tool '{tool.name}': schemas must not contain student_id (use ctx.user)")
        if tool.parameters.get("type") != "object":
            raise ValueError(f"tool '{tool.name}': parameters must be an object schema")
        if tool.name in self._tools:
            raise ValueError(f"tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        return tool

    def tool(self, *, name: str, description: str, parameters: dict, areas: Iterable[str],
             public: bool = False, safe_without_llm: bool = False):
        """Decorator form:  @registry.tool(name=..., description=..., parameters=..., areas=[...])"""
        def decorator(fn: Callable[..., Any]):
            self.add(Tool(name, description, parameters, fn, tuple(areas), public, safe_without_llm))
            return fn
        return decorator

    # ---- queries
    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def tools_for_areas(self, areas: Iterable[str]) -> list[Tool]:
        wanted = set(areas)
        return [t for t in self._tools.values() if wanted & set(t.areas)]

    def specs_for(self, areas: Iterable[str], authenticated: bool) -> list[dict]:
        chosen = [t for t in self.tools_for_areas(areas) if t.public or authenticated]
        return [t.spec() for t in chosen[:MAX_TOOLS_PER_REQUEST]]

    def needs_login(self, areas: Iterable[str], authenticated: bool) -> bool:
        """True when the areas have tools, but none of them works without logging in."""
        if authenticated:
            return False
        tools = self.tools_for_areas(areas)
        return bool(tools) and not any(t.public for t in tools)

    # ---- execution
    async def execute(self, name: str, args: Any, ctx: ToolContext) -> dict:
        """Never raises. Success -> the handler's dict. Failure -> {"error": code, "message": text}."""
        tool = self._tools.get(name)
        if tool is None:
            return {"error": "unknown_tool", "message": f"There is no tool called '{name}'."}

        if args is None or args == "":
            args = {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                return {"error": "bad_arguments", "message": "Arguments are not valid JSON."}
        problem = validate_args(tool.parameters, args)
        if problem:
            return {"error": "bad_arguments", "message": problem}

        if not tool.public and not ctx.authenticated:
            return {"error": "login_required", "message": "The student must log in first."}

        try:
            result = tool.handler(ctx, **args)
            if inspect.isawaitable(result):
                result = await result
        except Exception:  # a broken tool must not break the chat
            log.exception("tool %s failed", name)
            return {"error": "tool_failed", "message": "The tool failed. Please try again later."}

        if not isinstance(result, dict):
            result = {"result": result}
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) > MAX_RESULT_CHARS:
            return {"truncated": True, "preview": text[:MAX_RESULT_CHARS]}
        return result


# Default shared registry, so features can use @register_tool(...) like the brief says.
registry = ToolRegistry()
register_tool = registry.tool
