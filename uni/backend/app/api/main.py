"""FastAPI entry point. Run:  uvicorn app.api.main:create_app --factory --reload   (from backend/)

Routes: /health, /auth/* (M2), POST /chat/stream (SSE), GET /history/{session_id},
        POST /actions/{id}/confirm|cancel (the only write path), all backed by MongoDB."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.routes.auth import AuthService, AuthUser, _bearer, get_current_user, router as auth_router
from app.core.config import get_settings, get_today
from app.core.tools import ToolContext, ToolRegistry
from app.data.policy_repo import PolicyRepo
from app.data.progress_repo import ProgressRepo
from app.data.records_repo import RecordsRepo
from app.domain.intent_router import keyword_route
from app.services import calendar_service
from app.services.action_store import PendingActionStore
from app.services.chat_service import ChatService
from app.services.history_store import HistoryStore
from app.services.policy_service import PolicyService
from app.services.progress_service import ProgressService, configure_progress_service
from app.services.records_service import RecordsService, TranscriptNotAllowed

log = logging.getLogger("uni_chatbot")
_CHUNK = re.compile(r"\S+\s*")


class ChatBody(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    message: str = Field(max_length=2000)


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def build_registry(sync_db, settings):
    """Wire every feature into one registry. Returns the pieces the routes need."""
    from app.core.retrieval import PolicyRetriever

    progress_repo = ProgressRepo(sync_db)
    progress = ProgressService(progress_repo)
    configure_progress_service(progress)
    actions = PendingActionStore(sync_db, settings.confirm_ttl_s)
    records = RecordsService(RecordsRepo(db=sync_db), progress.get_blocks_transcripts, actions.propose)
    policy = PolicyService(PolicyRepo(sync_db), progress_repo)
    registry = ToolRegistry()
    progress.register(registry)
    records.register(registry)
    policy.register(registry)
    calendar_service.register(registry)
    retriever = PolicyRetriever(sync_db, settings.voyage_api_key)
    return registry, progress, records, actions, retriever


def create_app(*, db=None, sync_db=None, llm=None) -> FastAPI:
    settings = get_settings()
    if db is None:
        from app.core.db import get_db
        db = get_db()
    if sync_db is None:
        from app.core.db import get_sync_db
        sync_db = get_sync_db()
    if llm is None:
        from app.core.llm import GroqClient
        llm = GroqClient(api_key=settings.groq_api_key)

    registry, progress, records, actions, retriever = build_registry(sync_db, settings)
    history = HistoryStore(db)
    auth = AuthService(sync_db, jwt_secret=settings.jwt_secret, standing_loader=progress.get_standing_status)
    chat = ChatService(llm, registry, retrieve=retriever.retrieve, keyword_route=keyword_route,
                       save_turn=history.save_turn)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        auth.ensure_indexes()
        actions.ensure_indexes()
        await history.ensure_indexes()
        yield

    app = FastAPI(title="University Academic Affairs Chatbot", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    app.state.auth_service = auth
    app.state.db, app.state.chat, app.state.history = db, chat, history
    app.state.records, app.state.actions = records, actions
    app.include_router(auth_router)

    def optional_user(credentials=Depends(_bearer), request: Request = None):
        """No token = anonymous (public tools only). A bad or expired token = 401 so the UI can refresh once."""
        if credentials is None:
            return None
        user = request.app.state.auth_service.authenticate(credentials.credentials)
        if user is None:
            raise HTTPException(401, "Please log in", headers={"WWW-Authenticate": "Bearer"})
        return user

    @app.get("/health")
    async def health():
        try:
            await db.command("ping")
            return {"status": "ok", "database": "up"}
        except Exception:
            return {"status": "degraded", "database": "down"}

    @app.post("/chat/stream")
    async def chat_stream(body: ChatBody, user: AuthUser | None = Depends(optional_user)):
        today = get_today()
        try:
            info = await calendar_service.get_term_info(db, today)
            current, registering = info.current_term or "", info.registration_term or ""
        except Exception:
            log.exception("could not read the academic calendar")
            current = registering = ""
        ctx = ToolContext(user=user, today=today, registration_term=registering, current_term=current)
        uid = user.id if user else None
        past = await history.messages(body.session_id, uid, limit=12)

        async def events():
            async for ev in chat.handle(body.session_id, ctx, body.message, past):
                if ev["event"] == "delta":  # typing effect: the answer arrives in word chunks
                    for piece in _CHUNK.findall(str(ev["data"])):
                        yield sse("delta", piece)
                        await asyncio.sleep(0.012)
                else:
                    yield sse(ev["event"], ev["data"])

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/history")
    async def list_history(user: AuthUser = Depends(get_current_user)):
        return await history.list_sessions(user.id)

    @app.get("/history/{session_id}")
    async def get_history(session_id: str, user: AuthUser | None = Depends(optional_user)):
        return await history.messages(session_id, user.id if user else None)

    @app.post("/actions/{action_id}/confirm")
    def confirm(action_id: str, user: AuthUser = Depends(get_current_user)):
        doc = actions.consume(action_id, user.id)
        if doc is None:
            raise HTTPException(410, "This request expired or was already handled. Ask the assistant again.")
        if doc["action"] == "transcript_request":
            p = doc["payload"]
            try:
                rec = records.request_transcript(user, p["kind"], p["delivery"], get_today())
            except TranscriptNotAllowed as exc:
                raise HTTPException(409, "; ".join(exc.reasons))
            return {"ok": True, "status": "confirmed", "fee": rec["fee"],
                    "message": f"Your {p['kind']} transcript request ({p['delivery']}) was submitted."}
        raise HTTPException(400, "Unknown action type.")

    @app.post("/actions/{action_id}/cancel")
    def cancel(action_id: str, user: AuthUser = Depends(get_current_user)):
        if not actions.cancel(action_id, user.id):
            raise HTTPException(410, "This request expired or was already handled.")
        return {"ok": True, "status": "cancelled", "message": "Request cancelled."}

    return app
