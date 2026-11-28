import asyncio
import json
from datetime import date

import pytest

from app.core.tools import MAX_RESULT_CHARS, MAX_TOOLS_PER_REQUEST, Tool, ToolContext, ToolRegistry

CTX = ToolContext(user=object(), today=date(2026, 11, 21), registration_term="2027S", current_term="2026F")
ANON = ToolContext(user=None, today=date(2026, 11, 21), registration_term="2027S", current_term="2026F")
EMPTY = {"type": "object", "properties": {}, "required": []}


def run(coro):
    return asyncio.run(coro)


def make_registry():
    registry = ToolRegistry()

    @registry.tool(name="echo", description="echo", areas=["a"], public=True, parameters={
        "type": "object", "properties": {"text": {"type": "string"}, "n": {"type": "integer"},
                                         "mode": {"type": "string", "enum": ["x", "y"]}},
        "required": ["text"]})
    def echo(ctx, text, n=0, mode="x"):
        return {"text": text, "n": n, "mode": mode}

    @registry.tool(name="boom", description="fails", areas=["a"], public=True, parameters=EMPTY)
    def boom(ctx):
        raise RuntimeError("secret internal detail")

    @registry.tool(name="huge", description="big", areas=["a"], public=True, parameters=EMPTY)
    def huge(ctx):
        return {"data": "x" * (MAX_RESULT_CHARS * 2)}

    @registry.tool(name="private", description="needs login", areas=["b"], parameters=EMPTY)
    async def private(ctx):
        return {"ok": True}

    return registry


def test_unknown_tool_returns_error_dict():
    assert run(make_registry().execute("nope", {}, CTX))["error"] == "unknown_tool"


@pytest.mark.parametrize("args", [
    {}, {"text": 5}, {"text": "a", "extra": 1}, {"text": "a", "n": True},
    {"text": "a", "n": "3"}, {"text": "a", "mode": "z"}, {"text": "x" * 500}, [], "not json",
])
def test_bad_args_return_error_dict(args):
    out = run(make_registry().execute("echo", args, CTX))
    assert out["error"] == "bad_arguments"


def test_good_args_dict_and_json_string():
    registry = make_registry()
    assert run(registry.execute("echo", {"text": "hi", "n": 2}, CTX)) == {"text": "hi", "n": 2, "mode": "x"}
    assert run(registry.execute("echo", '{"text": "hi"}', CTX))["text"] == "hi"


def test_handler_exception_is_contained_and_not_leaked():
    out = run(make_registry().execute("boom", {}, CTX))
    assert out["error"] == "tool_failed" and "secret" not in json.dumps(out)


def test_huge_result_is_truncated():
    out = run(make_registry().execute("huge", {}, CTX))
    assert out["truncated"] is True and len(out["preview"]) == MAX_RESULT_CHARS


def test_login_required_for_non_public_tool():
    registry = make_registry()
    assert run(registry.execute("private", {}, ANON))["error"] == "login_required"
    assert run(registry.execute("private", {}, CTX)) == {"ok": True}


def test_no_schema_may_have_student_id():
    registry = ToolRegistry()
    bad = {"type": "object", "properties": {"student_id": {"type": "string"}}, "required": []}
    with pytest.raises(ValueError):
        registry.add(Tool("bad", "d", bad, lambda ctx: {}, ("a",)))
    nested = {"type": "object", "properties": {"x": {"type": "object", "properties": {"student_id": {}}}}}
    with pytest.raises(ValueError):
        registry.add(Tool("bad2", "d", nested, lambda ctx: {}, ("a",)))
    for tool in make_registry().all_tools():
        assert "student_id" not in json.dumps(tool.spec())


def test_specs_for_never_returns_more_than_six():
    registry = ToolRegistry()
    for i in range(10):
        registry.add(Tool(f"t{i}", "d", EMPTY, lambda ctx: {}, ("a",), public=True))
    assert len(registry.specs_for(["a"], authenticated=True)) == MAX_TOOLS_PER_REQUEST == 6


def test_specs_hide_login_tools_and_needs_login():
    registry = make_registry()
    assert registry.specs_for(["b"], authenticated=False) == []
    assert len(registry.specs_for(["b"], authenticated=True)) == 1
    assert registry.needs_login(["b"], False) is True
    assert registry.needs_login(["a"], False) is False  # has public tools
    assert registry.needs_login(["b"], True) is False
    assert registry.needs_login(["zzz"], False) is False  # no tools at all is not a login problem


def test_duplicate_and_bad_schema_rejected():
    registry = ToolRegistry()
    registry.add(Tool("t", "d", EMPTY, lambda ctx: {}, ("a",)))
    with pytest.raises(ValueError):
        registry.add(Tool("t", "d", EMPTY, lambda ctx: {}, ("a",)))
    with pytest.raises(ValueError):
        registry.add(Tool("u", "d", {"type": "array"}, lambda ctx: {}, ("a",)))
