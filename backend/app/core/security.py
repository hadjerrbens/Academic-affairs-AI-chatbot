"""M2 authentication helpers: Argon2id, signed JWTs and one-time tickets.

MVP storage is injected by AuthService. No secrets are hardcoded here.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, InvalidHashError

HASHER = PasswordHasher(type=Type.ID)
DUMMY_HASH = HASHER.hash("invalid-demo-password")


def hash_password(password: str) -> str:
    return HASHER.hash(password)


def _b64decode(value: str) -> bytes:
    # The shipped demo dataset uses Passlib's scrypt encoding.
    return base64.b64decode(value.replace(".", "+") + "=" * (-len(value) % 4))


def verify_password(password: str, encoded: str) -> tuple[bool, bool]:
    """Return (correct, requires_argon2_upgrade), supporting existing scrypt demo hashes."""
    if encoded.startswith("$argon2id$"):
        try:
            correct = HASHER.verify(encoded, password)
            return bool(correct), HASHER.check_needs_rehash(encoded)
        except (VerificationError, InvalidHashError, ValueError):
            return False, False
    if encoded.startswith("$scrypt$"):
        try:
            _, scheme, options, salt, digest = encoded.split("$")
            if scheme != "scrypt":
                return False, False
            params = dict(part.split("=", 1) for part in options.split(","))
            n, r, p = (int(params[k]) for k in ("n", "r", "p"))
            if n < 2 or n & (n - 1) or n > 262144 or not 1 <= r <= 32 or not 1 <= p <= 16:
                return False, False
            reference = _b64decode(digest)
            calculated = hashlib.scrypt(
                password.encode(), salt=_b64decode(salt), n=n, r=r, p=p,
                dklen=len(reference), maxmem=64 * 1024 * 1024,
            )
            correct = hmac.compare_digest(calculated, reference)
            return correct, correct
        except (ValueError, KeyError, TypeError, MemoryError):
            return False, False
    return False, False


def encode_token(user_id: str, secret: str, kind: str, lifetime_seconds: int, *, jti: str | None = None) -> str:
    now = int(time.time())
    claim = {"sub": user_id, "typ": kind, "iat": now, "exp": now + lifetime_seconds}
    if jti:
        claim["jti"] = jti
    return jwt.encode(claim, secret, algorithm="HS256")


def decode_token(token: str, secret: str, kind: str) -> dict:
    try:
        claim = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["sub", "typ", "iat", "exp"]})
        if claim.get("typ") != kind or not claim.get("sub") or (kind == "refresh" and not claim.get("jti")):
            raise ValueError("Wrong token type")
        return claim
    except (jwt.PyJWTError, ValueError) as exc:
        raise ValueError("Invalid or expired token") from exc


def fingerprint(jti: str) -> str:
    return hashlib.sha256(jti.encode()).hexdigest()


class RateLimiter:
    """Small, per-IP sliding window limiter for a single-process demo."""

    def __init__(self, limit: int = 5, window: int = 60):
        self.limit, self.window = limit, window
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


class TicketStore:
    """Single-use short-lived tickets consumed by M1's websocket integration."""

    def __init__(self, ttl: int = 60):
        self.ttl = ttl
        self.items = {}
        self.lock = threading.Lock()

    def issue(self, user_id: str) -> str:
        ticket = secrets.token_urlsafe(32)
        with self.lock:
            self.items[ticket] = (user_id, time.monotonic() + self.ttl)
        return ticket

    def consume(self, ticket: str) -> str | None:
        with self.lock:
            value = self.items.pop(ticket, None)
        if not value or value[1] <= time.monotonic():
            return None
        return value[0]
