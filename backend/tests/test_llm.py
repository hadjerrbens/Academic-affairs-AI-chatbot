"""Tests for llm.py using a fake transport (no network). Run: pytest"""
import asyncio
import json

import pytest

from app.core.llm import BudgetExceeded, GroqClient, LLMError, LLMUnavailable, TokenBudget


class FakeTransport:
    """Plays back a list of results. An Exception in the list is raised, a tuple is returned."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def request(self, url, headers, body):
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def ok(text="hello"):
    body = {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    return 200, {}, json.dumps(body).encode()


async def no_sleep(_seconds):
    pass


def make_client(script, **kw):
    transport = FakeTransport(script)
    client = GroqClient(api_key="test", transport=transport, sleep=no_sleep, **kw)
    return client, transport


MSG = [{"role": "user", "content": "hi"}]


def test_success():
    client, _ = make_client([ok("hi there")])
    assert asyncio.run(client.complete(MSG)) == "hi there"


def test_retries_on_429_then_succeeds():
    client, transport = make_client([(429, {"retry-after": "0"}, b"{}"), ok()])
    assert asyncio.run(client.complete(MSG)) == "hello"
    assert transport.calls == 2


def test_retries_on_network_error():
    client, transport = make_client([LLMUnavailable("timeout"), ok()])
    assert asyncio.run(client.complete(MSG)) == "hello"
    assert transport.calls == 2


def test_400_is_not_retried():
    client, transport = make_client([(400, {}, b'{"error": {"message": "bad"}}')])
    with pytest.raises(LLMError):
        asyncio.run(client.complete(MSG))
    assert transport.calls == 1


def test_missing_api_key():
    client = GroqClient(api_key="", transport=FakeTransport([]), sleep=no_sleep)
    client.api_key = ""
    with pytest.raises(LLMError):
        asyncio.run(client.complete(MSG))


def test_budget_exceeded():
    client, _ = make_client([ok()], budget=TokenBudget(limit=10))
    with pytest.raises(BudgetExceeded):
        asyncio.run(client.complete(MSG))


def test_budget_is_recorded():
    client, _ = make_client([ok()])
    asyncio.run(client.complete(MSG))
    assert asyncio.run(client.budget.used()) == 15
