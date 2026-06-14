"""Chainlit persistence (chat history / resumable threads) via SQLAlchemy data layer
on SQLite. Local to the container — history is lost on redeploy (single replica,
no volume). For durable history switch conninfo to an external Postgres.

Schema mirrors Chainlit's expected tables; column types use names that map to
sensible SQLite affinities. NOT NULL is relaxed (Chainlit builds inserts from
only the non-None keys, so required-but-omitted columns must not hard-fail).
"""
import os
import sqlite3

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

CHAINLIT_DB = os.getenv("CHAINLIT_DB_PATH", "chainlit.db")
CONNINFO = f"sqlite+aiosqlite:///{CHAINLIT_DB}"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    "id" TEXT PRIMARY KEY,
    "identifier" TEXT NOT NULL UNIQUE,
    "metadata" TEXT NOT NULL,
    "createdAt" TEXT
);
CREATE TABLE IF NOT EXISTS threads (
    "id" TEXT PRIMARY KEY,
    "createdAt" TEXT,
    "name" TEXT,
    "userId" TEXT,
    "userIdentifier" TEXT,
    "tags" TEXT,
    "metadata" TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    "id" TEXT PRIMARY KEY,
    "name" TEXT,
    "type" TEXT,
    "threadId" TEXT,
    "parentId" TEXT,
    "streaming" INTEGER,
    "waitForAnswer" INTEGER,
    "isError" INTEGER,
    "metadata" TEXT,
    "tags" TEXT,
    "input" TEXT,
    "output" TEXT,
    "createdAt" TEXT,
    "command" TEXT,
    "start" TEXT,
    "end" TEXT,
    "generation" TEXT,
    "showInput" TEXT,
    "language" TEXT,
    "indent" INTEGER,
    "defaultOpen" INTEGER,
    "autoCollapse" INTEGER,
    "icon" TEXT,
    "modes" TEXT,
    "feedback" TEXT
);
CREATE TABLE IF NOT EXISTS elements (
    "id" TEXT PRIMARY KEY,
    "threadId" TEXT,
    "type" TEXT,
    "url" TEXT,
    "chainlitKey" TEXT,
    "name" TEXT,
    "display" TEXT,
    "objectKey" TEXT,
    "size" TEXT,
    "page" INTEGER,
    "language" TEXT,
    "forId" TEXT,
    "mime" TEXT,
    "props" TEXT,
    "autoPlay" INTEGER,
    "playerConfig" TEXT,
    "path" TEXT
);
CREATE TABLE IF NOT EXISTS feedbacks (
    "id" TEXT PRIMARY KEY,
    "forId" TEXT,
    "threadId" TEXT,
    "value" INTEGER,
    "comment" TEXT
);
"""


# Columns added after the first schema version — ALTER them in for any pre-existing DB.
_MIGRATIONS = [
    ("steps", "autoCollapse", "INTEGER"), ("steps", "icon", "TEXT"),
    ("steps", "modes", "TEXT"), ("steps", "feedback", "TEXT"),
    ("elements", "autoPlay", "INTEGER"), ("elements", "playerConfig", "TEXT"),
    ("elements", "path", "TEXT"),
]


def init_chainlit_db() -> None:
    conn = sqlite3.connect(CHAINLIT_DB)
    try:
        conn.executescript(_SCHEMA)
        for table, col, typ in _MIGRATIONS:
            try:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN "{col}" {typ}')
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
    finally:
        conn.close()


@cl.data_layer
def get_data_layer():
    # storage_provider=None → text threads persist; file-element blobs are not stored.
    return SQLAlchemyDataLayer(conninfo=CONNINFO, storage_provider=None)
