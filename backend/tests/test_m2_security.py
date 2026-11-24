"""M2 security tests do not need a live MongoDB or any real credentials."""
from __future__ import annotations

import base64
import hashlib
import secrets
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.auth import AuthService, router
from app.core.security import (
    RateLimiter, TicketStore, decode_token, encode_token, fingerprint,
    hash_password, verify_password,
)


def _seeded_scrypt(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    s = base64.b64encode(salt).decode().rstrip("=")
    d = base64.b64encode(digest).decode().rstrip("=")
    return f"$scrypt$n=16384,r=8,p=1${s}${d}"


class FakeCollection:
    def __init__(self, data=()):
        self.rows = [dict(row) for row in data]

    def create_index(self, *args, **kwargs):
        return None

    def _matches(self, row, query):
        for name, wanted in query.items():
            actual = row.get(name)
            if isinstance(wanted, dict):
                if "$gt" in wanted and not (actual > wanted["$gt"]):
                    return False
                continue
            if actual != wanted:
                return False
        return True

    def find_one(self, query):
        return next((dict(row) for row in self.rows if self._matches(row, query)), None)

    def update_one(self, query, change):
        for row in self.rows:
            if self._matches(row, query):
                row.update(change.get("$set", {}))
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    def insert_one(self, data):
        self.rows.append(dict(data))

    def find_one_and_update(self, query, change):
        for row in self.rows:
            if self._matches(row, query):
                original = dict(row)
                row.update(change.get("$set", {}))
                return original
        return None


@pytest.fixture
def client():
    users = FakeCollection([
        {"user_id": "U-test", "student_id": "S-test", "email": "student@example.edu",
         "role": "student", "password_hash": _seeded_scrypt("strong-demo-password")},
    ])
    students = FakeCollection([{"student_id": "S-test", "has_unpaid_hold": False}])
    db = SimpleNamespace(users=users, students=students, refresh_sessions=FakeCollection())
    app = FastAPI()
    app.state.auth_service = AuthService(db, "temporary-test-key-do-not-use-in-production")
    app.include_router(router)
    return TestClient(app), db


def test_passwords_and_legacy_upgrade():
    hashed = hash_password("correct")
    assert hashed.startswith("$argon2id$")
    assert verify_password("correct", hashed) == (True, False)
    assert verify_password("wrong", hashed)[0] is False
    legacy = _seeded_scrypt("correct")
    assert verify_password("correct", legacy) == (True, True)
    assert verify_password("wrong", legacy)[0] is False


def test_jwt_requires_correct_type_and_signature():
    secret = "a-test-signing-key-long-enough-for-hs256-1234"
    access = encode_token("U1", secret, "access", 60)
    assert decode_token(access, secret, "access")["sub"] == "U1"
    with pytest.raises(ValueError):
        decode_token(access, secret, "refresh")
    with pytest.raises(ValueError):
        decode_token(access, "wrong-key-that-is-also-long-enough-for-hs256", "access")
    assert len(fingerprint("session-id")) == 64


def test_ticket_can_be_consumed_only_once():
    store = TicketStore(ttl=60)
    ticket = store.issue("U1")
    assert store.consume(ticket) == "U1"
    assert store.consume(ticket) is None
    assert store.consume("invented") is None


def test_rate_limit():
    limiter = RateLimiter(limit=2, window=60)
    assert limiter.allow("one") is True
    assert limiter.allow("one") is True
    assert limiter.allow("one") is False
    assert limiter.allow("another") is True


def test_login_refresh_rotation_logout_and_one_time_ticket(client):
    http, db = client
    wrong_email = http.post("/auth/login", json={"email": "unknown@example.edu", "password": "wrong"})
    wrong_pass = http.post("/auth/login", json={"email": "student@example.edu", "password": "wrong"})
    assert wrong_email.status_code == wrong_pass.status_code == 401
    assert wrong_email.json() == wrong_pass.json()

    logged = http.post("/auth/login", json={"email": "student@example.edu", "password": "strong-demo-password"})
    assert logged.status_code == 200
    tokens = logged.json()
    assert db.users.rows[0]["password_hash"].startswith("$argon2id$")
    who = http.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert who.status_code == 200
    assert who.json()["student_id"] == "S-test"
    assert "password_hash" not in who.json()

    ticket_response = http.post("/auth/ws-ticket", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert ticket_response.status_code == 200
    ticket = ticket_response.json()["ticket"]
    assert http.app.state.auth_service.tickets.consume(ticket) == "U-test"
    assert http.app.state.auth_service.tickets.consume(ticket) is None

    new = http.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert new.status_code == 200
    assert http.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    fresh = new.json()
    assert fresh["refresh_token"] != tokens["refresh_token"]
    assert http.post("/auth/logout", json={"refresh_token": fresh["refresh_token"]}).status_code == 200
    assert http.post("/auth/refresh", json={"refresh_token": fresh["refresh_token"]}).status_code == 401


def test_login_throttling(client):
    http, _ = client
    for _ in range(5):
        response = http.post("/auth/login", json={"email": "wrong@example.edu", "password": "wrong"})
        assert response.status_code == 401
    blocked = http.post("/auth/login", json={"email": "student@example.edu", "password": "strong-demo-password"})
    assert blocked.status_code == 429
