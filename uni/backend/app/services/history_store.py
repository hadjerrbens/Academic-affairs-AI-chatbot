"""Chat history in MongoDB (async, Motor). One document per turn."""
from __future__ import annotations

from datetime import datetime, timezone


class HistoryStore:
    def __init__(self, db) -> None:
        self.col = db.chat_turns

    async def ensure_indexes(self) -> None:
        await self.col.create_index([("session_id", 1), ("created_at", 1)])

    async def save_turn(self, session_id, user_id, question, answer, tokens, meta) -> None:
        await self.col.insert_one({"session_id": session_id, "user_id": user_id, "question": question,
                                   "answer": answer, "tokens": tokens, "meta": meta,
                                   "created_at": datetime.now(timezone.utc)})

    async def messages(self, session_id: str, user_id: str | None, limit: int = 40) -> list[dict]:
        """[{role, content}] oldest first, only this user's turns of this session."""
        cursor = self.col.find({"session_id": session_id, "user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(limit)
        turns = list(reversed(await cursor.to_list(length=limit)))
        out: list[dict] = []
        for t in turns:
            out.append({"role": "user", "content": t["question"]})
            out.append({"role": "assistant", "content": t["answer"]})
        return out

    async def list_sessions(self, user_id: str, limit: int = 20) -> list[dict]:
        """A student's conversations, newest first: [{session_id, title, last_at, turns}]."""
        cursor = self.col.find({"user_id": user_id}, {"_id": 0, "session_id": 1, "question": 1, "created_at": 1}).sort("created_at", -1).limit(500)
        sessions: dict[str, dict] = {}
        for t in await cursor.to_list(length=500):  # newest first, so the last one seen is the opening question
            s = sessions.setdefault(t["session_id"], {"session_id": t["session_id"], "last_at": t["created_at"], "turns": 0, "title": ""})
            s["turns"] += 1
            s["title"] = t["question"]
        out = list(sessions.values())[:limit]
        for s in out:
            s["title"] = s["title"][:70]
            s["last_at"] = s["last_at"].isoformat()
        return out
