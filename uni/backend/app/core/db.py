"""One MongoDB connection setup for the whole app (one URI, one database name).

get_db()       -> Motor (async) database. Used by M3's calendar repo, chat history, retrieval.
get_sync_db()  -> PyMongo (sync) database. Used by auth, progress, records, pending actions, seeding.
Both point at the same database.
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings


@lru_cache
def get_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    s = get_settings()
    return AsyncIOMotorClient(s.mongodb_uri, serverSelectionTimeoutMS=5000)[s.mongodb_db]


@lru_cache
def get_sync_db():
    from pymongo import MongoClient
    s = get_settings()
    return MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=5000)[s.mongodb_db]
