"""SQLite storage. The database file lives in data/ and is git-ignored.

Timestamps are UTC strings in SQLite's own "YYYY-MM-DD HH:MM:SS" format so
they compare correctly as text. Tags are stored as ",tag1,tag2," so a single
tag can be matched with LIKE '%,tag,%'.
"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id          INTEGER PRIMARY KEY,
    business    TEXT NOT NULL,
    email       TEXT NOT NULL COLLATE NOCASE,
    name        TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    suburb      TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'subscribed'
                CHECK (status IN ('subscribed', 'unsubscribed', 'bounced')),
    source      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (business, email)
);

CREATE TABLE IF NOT EXISTS templates (
    id          INTEGER PRIMARY KEY,
    business    TEXT NOT NULL,
    name        TEXT NOT NULL,
    subject     TEXT NOT NULL,
    body        TEXT NOT NULL,
    style       TEXT NOT NULL DEFAULT 'plain' CHECK (style IN ('plain', 'branded')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (business, name)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id          INTEGER PRIMARY KEY,
    business    TEXT NOT NULL,
    name        TEXT NOT NULL,
    template_id INTEGER NOT NULL REFERENCES templates(id),
    tag         TEXT NOT NULL DEFAULT '',   -- empty = every subscribed contact
    skip_tag    TEXT NOT NULL DEFAULT '',   -- contacts with this tag are left out
    status      TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'sending', 'partial', 'sent')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    sent_at     TEXT
);

CREATE TABLE IF NOT EXISTS sequences (
    id          INTEGER PRIMARY KEY,
    business    TEXT NOT NULL,
    name        TEXT NOT NULL,
    trigger_tag TEXT NOT NULL,
    exit_tags   TEXT NOT NULL DEFAULT '',   -- stored like contacts.tags
    active      INTEGER NOT NULL DEFAULT 1,
    UNIQUE (business, name)
);

CREATE TABLE IF NOT EXISTS sequence_steps (
    id          INTEGER PRIMARY KEY,
    sequence_id INTEGER NOT NULL REFERENCES sequences(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    delay_days  INTEGER NOT NULL,           -- days after the previous step (or enrolment)
    template_id INTEGER NOT NULL REFERENCES templates(id),
    UNIQUE (sequence_id, position)
);

CREATE TABLE IF NOT EXISTS enrollments (
    id            INTEGER PRIMARY KEY,
    sequence_id   INTEGER NOT NULL REFERENCES sequences(id) ON DELETE CASCADE,
    contact_id    INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    enrolled_at   TEXT NOT NULL,
    next_position INTEGER NOT NULL,
    next_due_at   TEXT,
    status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'completed', 'stopped')),
    UNIQUE (sequence_id, contact_id)
);

CREATE TABLE IF NOT EXISTS sends (
    id            INTEGER PRIMARY KEY,
    business      TEXT NOT NULL,
    contact_id    INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    email         TEXT NOT NULL,
    campaign_id   INTEGER REFERENCES campaigns(id),
    enrollment_id INTEGER REFERENCES enrollments(id) ON DELETE SET NULL,
    step_position INTEGER,
    subject       TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('sent', 'failed')),
    error         TEXT NOT NULL DEFAULT '',
    sent_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS sends_business_time ON sends (business, sent_at);
CREATE INDEX IF NOT EXISTS sends_campaign ON sends (campaign_id, contact_id);
CREATE INDEX IF NOT EXISTS enrollments_due ON enrollments (status, next_due_at);
"""

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA journal_mode = WAL")  # dashboard and background sends share the file
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring databases created by older versions up to the current schema."""
    added = {
        "templates": ("style", "TEXT NOT NULL DEFAULT 'plain'"
                               " CHECK (style IN ('plain', 'branded'))"),
        "campaigns": ("skip_tag", "TEXT NOT NULL DEFAULT ''"),
    }
    for table, (column, definition) in added.items():
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.commit()


def now() -> str:
    return datetime.now(timezone.utc).strftime(TIME_FORMAT)


def shift(ts: str, *, days: float = 0, hours: float = 0) -> str:
    dt = datetime.strptime(ts, TIME_FORMAT) + timedelta(days=days, hours=hours)
    return dt.strftime(TIME_FORMAT)


def clean_tag(tag: str) -> str:
    # '_' and '%' are LIKE wildcards, so tags are limited to letters, digits and '-'.
    return re.sub(r"[^a-z0-9-]", "", re.sub(r"[\s_]+", "-", tag.strip().lower())).strip("-")


def tag_list(stored: str) -> list[str]:
    return [t for t in stored.split(",") if t]


def store_tags(tags) -> str:
    """Accepts a comma-separated string or an iterable; returns ',a,b,' or ''."""
    if isinstance(tags, str):
        tags = tags.split(",")
    clean = sorted({clean_tag(t) for t in tags} - {""})
    return f",{','.join(clean)}," if clean else ""


def has_any_tag(stored: str, wanted: str) -> bool:
    return bool(set(tag_list(stored)) & set(tag_list(wanted)))
