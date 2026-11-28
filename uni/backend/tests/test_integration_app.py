"""End to end on a fake MongoDB: seed -> login -> chat (fake LLM, real tools) -> confirm. No network, no Prolog."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mongomock import MongoClient
from mongomock_motor import AsyncMongoMockClient

from app.core.config import get_settings
from app.core.llm import TokenBudget
from app.core.security import hash_password
from app.data.seed_loader import check_against_manifest, seed_all

SEED = Path(__file__).resolve().parents[2] / "data" / "seed"


class FakeLLM:
    """Router picks the area from the test; the answer model asks for one tool, then says OK."""
    def __init__(self, area, tool=None, args=None):
        self.area, self.tool, self.args, self.budget, self.calls = area, tool, args or {}, TokenBudget(), 0

    async def complete_json(self, messages, **kw):
        return {"primary": self.area, "secondary": None}

    async def complete_message(self, messages, **kw):
        self.calls += 1
        if self.tool and self.calls == 1:
            return {"content": "", "tool_calls": [{"id": "c1", "type": "function",
                    "function": {"name": self.tool, "arguments": json.dumps(self.args)}}]}
        return {"content": "Here is the answer."}


def parse(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(l.split(": ", 1) for l in block.split("\n") if ": " in l)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://unused")
    monkeypatch.setenv("MONGODB_DB", "t")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("TODAY_OVERRIDE", "2026-10-27")
    get_settings.cache_clear()
    sync_db = MongoClient()["t"]
    counts = seed_all(sync_db, SEED)
    assert check_against_manifest(counts, SEED) == []
    for sid in ("S0000001", "S0000003", "S0000010"):
        sync_db.users.update_one({"student_id": sid}, {"$set": {"password_hash": hash_password("pw-test-123")}})
    # the async client must see the same data
    adb = AsyncMongoMockClient()["t"]
    return sync_db, adb


def make_client(env, llm):
    from app.api.main import create_app
    sync_db, adb = env
    return TestClient(create_app(db=adb, sync_db=sync_db, llm=llm))


def login(client, student):
    r = client.post("/auth/login", json={"email": f"{student.lower()}@student.example.edu", "password": "pw-test-123"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def ask(client, text, headers=None):
    r = client.post("/chat/stream", json={"session_id": "session-test-1", "message": text}, headers=headers or {})
    assert r.status_code == 200, r.text
    return parse(r.text)


def test_standing_probation_for_s3_through_real_tool(env):
    with make_client(env, FakeLLM("academic_standing", "get_academic_standing")) as c:
        events = ask(c, "What is my standing?", login(c, "S0000003"))
    tools = [d for e, d in events if e == "tool"]
    assert tools == [{"name": "get_academic_standing", "ok": True}]
    assert events[-1][0] == "done"


def test_anonymous_gets_login_prompt_for_private_data(env):
    with make_client(env, FakeLLM("academic_standing", "get_academic_standing")) as c:
        events = ask(c, "What is my standing?")
    text = "".join(d for e, d in events if e == "delta")
    assert "log in" in text.lower()


def test_public_tool_works_without_login(env):
    with make_client(env, FakeLLM("proctoring", "get_proctoring_info", {"exam_type": "online"})) as c:
        events = ask(c, "How does online proctoring work?")
    assert ("tool", {"name": "get_proctoring_info", "ok": True}) in events


def test_transcript_confirm_flow_writes_once(env):
    sync_db, _ = env
    llm = FakeLLM("transcripts", "propose_transcript_request", {"kind": "unofficial", "delivery": "email"})
    with make_client(env, llm) as c:
        h = login(c, "S0000001")
        events = ask(c, "I need an unofficial transcript by email", h)
        confirm = [d for e, d in events if e == "confirm"]
        assert confirm and confirm[0]["action_id"]
        before = sync_db.transcript_requests.count_documents({"student_id": "S0000001"})
        r = c.post(f"/actions/{confirm[0]['action_id']}/confirm", headers=h)
        assert r.status_code == 200, r.text
        assert sync_db.transcript_requests.count_documents({"student_id": "S0000001"}) == before + 1
        assert c.post(f"/actions/{confirm[0]['action_id']}/confirm", headers=h).status_code == 410  # only once


def test_someone_else_cannot_confirm_my_action(env):
    llm = FakeLLM("transcripts", "propose_transcript_request", {"kind": "unofficial", "delivery": "email"})
    with make_client(env, llm) as c:
        h1, h3 = login(c, "S0000001"), login(c, "S0000003")
        action = [d for e, d in ask(c, "unofficial transcript by email", h1) if e == "confirm"][0]["action_id"]
        assert c.post(f"/actions/{action}/confirm", headers=h3).status_code == 410


def test_history_is_private_to_the_user(env):
    with make_client(env, FakeLLM("smalltalk")) as c:
        h = login(c, "S0000001")
        ask(c, "hello", h)
        assert len(c.get("/history/session-test-1", headers=h).json()) == 2
        assert c.get("/history/session-test-1").json() == []  # anonymous sees nothing of it


def seed_async(sync_db, adb):
    import asyncio
    async def go():
        for name in ("calendar_events", "exam_schedules", "exam_rules", "enrollments"):
            await adb[name].delete_many({})
            await adb[name].insert_many(list(sync_db[name].find({}, {"_id": 0})))
    asyncio.run(go())


def test_calendar_and_exam_tools_read_the_database(env, monkeypatch):
    sync_db, adb = env
    monkeypatch.setattr("app.core.db.get_db", lambda: adb)
    seed_async(sync_db, adb)
    llm = FakeLLM("exam_schedules", "get_my_exam_schedule")
    with make_client(env, llm) as c:
        h = login(c, "S0000001")
        events = ask(c, "when are my exams?", h)
    assert ("tool", {"name": "get_my_exam_schedule", "ok": True}) in events
    llm = FakeLLM("academic_calendar", "get_academic_calendar")
    with make_client(env, llm) as c:
        events = ask(c, "academic calendar")
    assert ("tool", {"name": "get_academic_calendar", "ok": True}) in events


def test_session_list_is_private_and_newest_first(env):
    with make_client(env, FakeLLM("smalltalk")) as c:
        h1, h3 = login(c, "S0000001"), login(c, "S0000003")
        c.post("/chat/stream", json={"session_id": "session-aaaa-1", "message": "first question"}, headers=h1)
        c.post("/chat/stream", json={"session_id": "session-bbbb-2", "message": "second question"}, headers=h1)
        rows = c.get("/history", headers=h1).json()
        assert [r["session_id"] for r in rows] == ["session-bbbb-2", "session-aaaa-1"]
        assert rows[0]["title"] == "second question" and rows[0]["turns"] == 1
        assert c.get("/history", headers=h3).json() == []
        assert c.get("/history").status_code == 401
