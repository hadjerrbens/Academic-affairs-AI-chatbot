"""M2 routes: mount router and configure app.state.auth_service in M3's main.py."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.core.security import (
    DUMMY_HASH, RateLimiter, TicketStore, decode_token, encode_token,
    fingerprint, hash_password, verify_password,
)

ACCESS_SECONDS = 15 * 60
REFRESH_SECONDS = 7 * 24 * 60 * 60
INVALID_LOGIN = "Invalid email or password."
router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    student_id: str
    email: str
    role: str
    standing: str | None = None
    has_unpaid_hold: bool = False

    @property
    def id(self):
        """M4's ToolContext.user.id corresponds to student_id."""
        return self.student_id


class AuthService:
    def __init__(self, db, jwt_secret: str, standing_loader=None):
        if not jwt_secret or jwt_secret == "change-me":
            raise ValueError("Configure a strong JWT_SECRET in .env")
        self.db, self.secret, self.standing_loader = db, jwt_secret, standing_loader
        self.rate_limiter = RateLimiter()
        self.tickets = TicketStore()

    def ensure_indexes(self):
        self.db.users.create_index("email", unique=True)
        self.db.refresh_sessions.create_index("jti_hash", unique=True)
        self.db.refresh_sessions.create_index("expires_at", expireAfterSeconds=0)

    def _pair(self, user):
        uid, jti = user["user_id"], uuid4().hex
        now = datetime.now(timezone.utc)
        self.db.refresh_sessions.insert_one({
            "user_id": uid, "jti_hash": fingerprint(jti),
            "expires_at": now + timedelta(seconds=REFRESH_SECONDS), "revoked": False,
        })
        return {"access_token": encode_token(uid, self.secret, "access", ACCESS_SECONDS),
                "refresh_token": encode_token(uid, self.secret, "refresh", REFRESH_SECONDS, jti=jti),
                "token_type": "bearer", "expires_in": ACCESS_SECONDS}

    def login(self, email: str, password: str):
        user = self.db.users.find_one({"email": email.strip().lower()})
        valid, upgrade = verify_password(password, user["password_hash"] if user else DUMMY_HASH)
        if not user or not valid:
            return None
        if upgrade:
            self.db.users.update_one(
                {"user_id": user["user_id"], "password_hash": user["password_hash"]},
                {"$set": {"password_hash": hash_password(password)}},
            )
        return self._pair(user)

    def refresh(self, refresh_token: str):
        try:
            payload = decode_token(refresh_token, self.secret, "refresh")
        except ValueError:
            return None
        # Atomic consume: a given refresh token can be used at most once.
        result = self.db.refresh_sessions.find_one_and_update(
            {"user_id": payload["sub"], "jti_hash": fingerprint(payload["jti"]),
             "revoked": False, "expires_at": {"$gt": datetime.now(timezone.utc)}},
            {"$set": {"revoked": True}},
        )
        if not result:
            return None
        user = self.db.users.find_one({"user_id": payload["sub"]})
        return self._pair(user) if user else None

    def logout(self, refresh_token: str):
        try:
            payload = decode_token(refresh_token, self.secret, "refresh")
        except ValueError:
            return
        self.db.refresh_sessions.update_one(
            {"user_id": payload["sub"], "jti_hash": fingerprint(payload["jti"])},
            {"$set": {"revoked": True}},
        )

    def authenticate(self, token: str):
        try:
            user_id = decode_token(token, self.secret, "access")["sub"]
        except ValueError:
            return None
        user = self.db.users.find_one({"user_id": user_id})
        if not user:
            return None
        sid = user["student_id"]
        student = self.db.students.find_one({"student_id": sid}) or {}
        try:
            standing = self.standing_loader(sid) if self.standing_loader else None
        except Exception:
            standing = None  # Keep the account usable if the M3 Prolog bridge is temporarily down.
        if isinstance(standing, dict):
            standing = standing.get("status")
        return AuthUser(user_id, sid, user["email"], user.get("role", "student"),
                        standing, str(student.get("has_unpaid_hold", False)).strip().lower() == "true")


def service(request: Request) -> AuthService:
    result = getattr(request.app.state, "auth_service", None)
    if result is None:
        raise HTTPException(503, "Authentication is not configured")
    return result


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    auth: AuthService = Depends(service),
) -> AuthUser:
    user = auth.authenticate(credentials.credentials) if credentials else None
    if not user:
        raise HTTPException(401, "Please log in", headers={"WWW-Authenticate": "Bearer"})
    return user


require_auth = get_current_user


def get_current_student_id(user: AuthUser = Depends(get_current_user)) -> str:
    """For M1's existing endpoints that expect a student_id string."""
    return user.student_id


class Credentials(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


@router.post("/login")
def login(body: Credentials, request: Request, auth: AuthService = Depends(service)):
    ip = request.client.host if request.client else "unknown"
    if not auth.rate_limiter.allow(ip):
        raise HTTPException(429, "Too many login attempts")
    tokens = auth.login(body.email, body.password)
    if tokens is None:
        raise HTTPException(401, INVALID_LOGIN)
    return tokens


@router.post("/refresh")
def refresh(body: RefreshRequest, auth: AuthService = Depends(service)):
    tokens = auth.refresh(body.refresh_token)
    if tokens is None:
        raise HTTPException(401, "Invalid refresh token")
    return tokens


@router.post("/logout")
def logout(body: LogoutRequest, auth: AuthService = Depends(service)):
    if body.refresh_token:
        auth.logout(body.refresh_token)
    return {"ok": True}


@router.get("/me")
def me(user: AuthUser = Depends(get_current_user)):
    return {"user_id": user.user_id, "student_id": user.student_id,
            "email": user.email, "role": user.role}


@router.post("/ws-ticket")
def ws_ticket(user: AuthUser = Depends(get_current_user), auth: AuthService = Depends(service)):
    return {"ticket": auth.tickets.issue(user.user_id), "expires_in": auth.tickets.ttl}
