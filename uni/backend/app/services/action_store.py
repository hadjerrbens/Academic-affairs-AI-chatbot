"""Pending actions (the confirm gate). Tools only PROPOSE; a click on Confirm consumes the action once.
Stored in MongoDB (pending_actions) with a TTL index, so a proposal expires by itself."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4


class PendingActionStore:
    def __init__(self, db, ttl_s: int = 120) -> None:
        self.col = db.pending_actions
        self.ttl_s = ttl_s

    def ensure_indexes(self) -> None:
        self.col.create_index("action_id", unique=True)
        self.col.create_index("expires_at", expireAfterSeconds=0)

    def propose(self, user_id: str, action: str, payload: dict, summary: str) -> str:
        action_id = "act_" + uuid4().hex[:12]
        now = datetime.now(timezone.utc)
        self.col.insert_one({"action_id": action_id, "user_id": user_id, "action": action, "payload": payload,
                             "summary": summary, "status": "pending", "created_at": now,
                             "expires_at": now + timedelta(seconds=self.ttl_s)})
        return action_id

    def consume(self, action_id: str, user_id: str) -> dict | None:
        """Atomically pending -> confirmed, only for the owner and only before expiry. None if not possible."""
        return self.col.find_one_and_update(
            {"action_id": action_id, "user_id": user_id, "status": "pending",
             "expires_at": {"$gt": datetime.now(timezone.utc)}},
            {"$set": {"status": "confirmed"}}, projection={"_id": 0})

    def cancel(self, action_id: str, user_id: str) -> bool:
        res = self.col.update_one({"action_id": action_id, "user_id": user_id, "status": "pending"},
                                  {"$set": {"status": "cancelled"}})
        return res.modified_count == 1
