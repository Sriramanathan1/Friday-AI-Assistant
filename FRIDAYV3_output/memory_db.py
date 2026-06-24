"""
memory_db.py — FRIDAY SQLite Memory Backend (V4)

Replaces memory.json. Stores:
  - facts        : key/value user facts (name, city, interests, ...)
  - episodes     : conversation history (role, content, timestamp)
  - usage_log    : raw command log (for analytics / search_memory)
  - workflows    : named sequences of voice commands

Used by:
  - smart_memory.py   (facts)
  - tool_executor.py  (facts, search, workflows)
  - brain_v4.py       (episodes, session summary)
"""

import sqlite3
import json
import os
import threading
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "friday_memory.db")
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _init_db():
    with _lock, _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                key   TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                role    TEXT,
                content TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS usage_log (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                name  TEXT PRIMARY KEY,
                steps TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at)")


_init_db()


# ================================================================
#  FACTS
# ================================================================

def save_fact(key: str, value) -> None:
    """Save/overwrite a fact. Lists/dicts are JSON-encoded."""
    key = key.strip().lower()
    stored = json.dumps(value) if isinstance(value, (list, dict)) else str(value)

    with _lock, _conn() as c:
        c.execute(
            """INSERT INTO facts (key, value, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                                               updated_at=excluded.updated_at""",
            (key, stored),
        )


def get_fact(key: str):
    """Return a fact's value (decoded from JSON if it's a list/dict), or None."""
    key = key.strip().lower()
    with _conn() as c:
        row = c.execute("SELECT value FROM facts WHERE key = ?", (key,)).fetchone()

    if row is None:
        return None

    raw = row[0]
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, (list, dict)):
            return decoded
    except (json.JSONDecodeError, TypeError):
        pass
    return raw


def get_all_facts() -> dict:
    """Return all facts as {key: value}, decoding list/dict values."""
    with _conn() as c:
        rows = c.execute("SELECT key, value FROM facts ORDER BY updated_at DESC").fetchall()

    result = {}
    for key, raw in rows:
        try:
            decoded = json.loads(raw)
            result[key] = decoded if isinstance(decoded, (list, dict)) else raw
        except (json.JSONDecodeError, TypeError):
            result[key] = raw
    return result


def delete_fact(key: str) -> bool:
    """Delete a fact. Returns True if a row was removed."""
    key = key.strip().lower()
    with _lock, _conn() as c:
        cur = c.execute("DELETE FROM facts WHERE key = ?", (key,))
    return cur.rowcount > 0


def search_facts(query: str) -> list[str]:
    """Return formatted 'key: value' strings for facts matching the query."""
    query_lower = query.lower()
    results = []
    for key, value in get_all_facts().items():
        text = f"{key}: {value if not isinstance(value, list) else ', '.join(str(v) for v in value)}"
        if query_lower in key.lower() or query_lower in text.lower():
            results.append(f"[Fact] {text}")
    return results


# ================================================================
#  EPISODES (conversation history)
# ================================================================

def log_episode(role: str, content: str) -> None:
    """Append a conversation turn (role: 'user' | 'assistant')."""
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO episodes (role, content, created_at) VALUES (?, ?, datetime('now'))",
            (role, content),
        )


def get_recent_episodes(n: int = 10) -> list[dict]:
    """
    Return the last `n` conversation turns as a list of
    {"role": ..., "content": ...} dicts, oldest first — ready to
    splice directly into a Groq `messages` list.
    """
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content FROM episodes ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()

    rows.reverse()
    return [{"role": role, "content": content} for role, content in rows]


def get_session_summary_text(n: int = 20) -> str:
    """
    Build a short '[Recent conversation: ...]' summary string for the
    system prompt, based on the last `n` episodes.
    """
    episodes = get_recent_episodes(n=n)
    if not episodes:
        return ""

    parts = []
    for ep in episodes[-n:]:
        snippet = ep["content"].strip().replace("\n", " ")
        if len(snippet) > 100:
            snippet = snippet[:100] + "..."
        parts.append(f"{ep['role']}: {snippet}")

    return "[Recent conversation:\n" + "\n".join(parts) + "\n]"


def search_episodes(query: str, limit: int = 5) -> list[str]:
    """Return formatted past conversation turns matching the query."""
    query_lower = f"%{query.lower()}%"
    with _conn() as c:
        rows = c.execute(
            """SELECT role, content, created_at FROM episodes
               WHERE LOWER(content) LIKE ?
               ORDER BY id DESC LIMIT ?""",
            (query_lower, limit),
        ).fetchall()

    return [f"[{created_at}] {role}: {content}" for role, content, created_at in rows]


# ================================================================
#  USAGE LOG
# ================================================================

def log_usage(command: str) -> None:
    """Log a raw user command for analytics / future search."""
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO usage_log (command, created_at) VALUES (?, datetime('now'))",
            (command,),
        )


# ================================================================
#  WORKFLOWS
# ================================================================

def save_workflow(name: str, steps: list) -> None:
    name = name.strip().lower()
    with _lock, _conn() as c:
        c.execute(
            """INSERT INTO workflows (name, steps, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(name) DO UPDATE SET steps=excluded.steps,
                                                updated_at=excluded.updated_at""",
            (name, json.dumps(steps)),
        )


def get_workflow(name: str) -> list | None:
    name = name.strip().lower()
    with _conn() as c:
        row = c.execute("SELECT steps FROM workflows WHERE name = ?", (name,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None


def list_workflows() -> list[str]:
    with _conn() as c:
        rows = c.execute("SELECT name FROM workflows ORDER BY name").fetchall()
    return [r[0] for r in rows]


def delete_workflow(name: str) -> bool:
    name = name.strip().lower()
    with _lock, _conn() as c:
        cur = c.execute("DELETE FROM workflows WHERE name = ?", (name,))
    return cur.rowcount > 0


# ================================================================
#  ONE-TIME MIGRATION FROM memory.json (V3 -> V4)
# ================================================================

def migrate_from_json(json_path: str) -> int:
    """
    Import facts from the old memory.json (V3) into the facts table.

    V3's memory.json stores personal facts under a "smart_facts" key
    (e.g. {"smart_facts": {"city": "Chennai", "interest": [...], "_last_updated": ...}}).
    If that key is missing, falls back to treating the whole JSON as a
    flat facts dict (for older/simpler memory.json formats).

    Safe to call multiple times — existing keys are overwritten with
    the JSON values only if the JSON has them.

    Returns number of facts migrated.
    """
    if not os.path.exists(json_path):
        return 0

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0

    if not isinstance(data, dict):
        return 0

    source = data.get("smart_facts") if isinstance(data.get("smart_facts"), dict) else data

    count = 0
    for key, value in source.items():
        if key.startswith("_"):  # skip internal/meta keys (e.g. _last_updated)
            continue
        save_fact(key, value)
        count += 1

    return count
