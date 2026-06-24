"""
smart_memory.py — FRIDAY Autonomous Memory (V4)

FRIDAY passively listens to every conversation turn and automatically
saves important personal facts — just like ChatGPT's Memory feature.

CHANGES FROM V3:
  ✓ Backend switched from memory.json to memory_db.py (SQLite)
  ✓ LLM fallback extractor — when regex misses, ask Groq to extract facts
  ✓ build_facts_context() pulls from SQLite instead of JSON

What it saves (examples):
  "my name is Sri"           → name = Sri
  "I study at XYZ school"    → school = XYZ
  "I am interested in chess" → interest: [chess]
  "I am 16 years old"        → age = 16
  "I live in Chennai"        → city = Chennai
  "I am preparing for JEE"   → exam_goal = JEE
"""

import re
import json
from datetime import datetime


# ================= MEMORY BACKEND =================

def _save(key: str, value):
    """Persist a fact via memory_db."""
    from memory_db import save_fact, get_fact

    key   = key.strip().lower()
    if isinstance(value, str):
        value = value.strip().rstrip(".,!?")

    if not value or (isinstance(value, str) and len(value) < 2):
        return

    # For list-type keys, append rather than overwrite
    LIST_KEYS = {"interest", "hobby", "language"}
    if key in LIST_KEYS:
        existing = get_fact(key) or []
        if isinstance(existing, str):
            existing = [existing]
        v_lower = value.lower() if isinstance(value, str) else str(value).lower()
        if v_lower not in [x.lower() for x in existing]:
            existing.append(value)
            save_fact(key, existing)
            print(f"[SMART MEMORY] Appended {key}: {value}")
    else:
        old = None
        try:
            old = _load(key)
        except Exception:
            pass
        save_fact(key, value)
        if old != value:
            print(f"[SMART MEMORY] Saved {key}: {value!r}")


def _load(key: str):
    from memory_db import get_fact
    return get_fact(key)


# ================= NOISE FILTER =================

NOISE_WORDS = {
    "a", "an", "the", "this", "that", "it", "they", "he", "she", "we",
    "going", "trying", "not", "just", "also", "done", "sure", "great",
    "bad", "good", "okay", "yes", "no", "able", "ready"
}


# ================= REGEX PATTERNS =================
# (pattern, fact_key, capture_group_index)

PATTERNS = [

    # ── Name ──
    (re.compile(r"\bmy name is ([a-z][a-z\s]{1,30})", re.I),            "name",           1),
    (re.compile(r"\bcall me ([a-z][a-z\s]{1,20})\b", re.I),             "name",           1),
    (re.compile(r"\bi am ([a-z][a-z\s]{1,20})\b", re.I),                "name_candidate", 1),

    # ── School / College ──
    (re.compile(r"\bi (?:study|go|attend|am) (?:at|in|to) ([a-z0-9\s,.-]{4,60}school[a-z\s]*)", re.I),  "school",  1),
    (re.compile(r"\bi (?:study|go|attend|am) (?:at|in|to) ([a-z0-9\s,.-]{4,60}college[a-z\s]*)", re.I), "college", 1),
    (re.compile(r"\bmy school is ([a-z0-9\s,.-]{4,60})", re.I),         "school",         1),
    (re.compile(r"\bmy college is ([a-z0-9\s,.-]{4,60})", re.I),        "college",        1),
    (re.compile(r"\bstudying (?:at|in) ([a-z0-9\s,.-]{4,60})", re.I),   "school",         1),

    # ── Class / Grade ──
    (re.compile(r"\bi(?:'m| am) in (?:class|grade) (\d{1,2}[a-z]?)\b", re.I), "class",   1),
    (re.compile(r"\bclass (\d{1,2}[a-z]?)\b", re.I),                    "class",          1),

    # ── Age ──
    (re.compile(r"\bi(?:'m| am) (\d{1,2}) years? old\b", re.I),         "age",            1),
    (re.compile(r"\bmy age is (\d{1,2})\b", re.I),                      "age",            1),

    # ── City / Location ──
    (re.compile(r"\bi live in ([a-z][a-z\s,]{2,40})\b", re.I),          "city",           1),
    (re.compile(r"\bi(?:'m| am) from ([a-z][a-z\s,]{2,40})\b", re.I),   "hometown",       1),
    (re.compile(r"\bmy city is ([a-z][a-z\s,]{2,30})\b", re.I),         "city",           1),

    # ── Interests / Hobbies ──
    (re.compile(r"\bi(?:'m| am) interested in ([a-z][a-z\s,]{3,60})", re.I), "interest",  1),
    (re.compile(r"\bi love ([a-z][a-z\s,]{3,50})\b", re.I),             "interest",       1),
    (re.compile(r"\bi enjoy ([a-z][a-z\s,]{3,50})\b", re.I),            "interest",       1),
    (re.compile(r"\bmy hobby is ([a-z][a-z\s,]{3,50})\b", re.I),        "hobby",          1),
    (re.compile(r"\bi like (?:to |)([a-z][a-z\s,]{3,50})\b", re.I),     "interest",       1),

    # ── Exam goals ──
    (re.compile(r"\bpreparing for ([a-z][a-z\s]{2,30})\b", re.I),       "exam_goal",      1),
    (re.compile(r"\bmy (?:goal|target|aim) is ([a-z][a-z\s]{2,50})\b", re.I), "goal",     1),

    # ── Subject preference ──
    (re.compile(r"\bi (?:love|like|prefer|enjoy) ([a-z]+)\b.{0,20}?(?:subject|class|topic)", re.I), "favourite_subject", 1),

    # ── Language ──
    (re.compile(r"\bi speak ([a-z][a-z\s,]{2,30})\b", re.I),            "language",       1),

    # ── Nickname ──
    (re.compile(r"\beveryone calls me ([a-z][a-z\s]{1,20})\b", re.I),   "nickname",       1),
    (re.compile(r"\bfriends call me ([a-z][a-z\s]{1,20})\b", re.I),     "nickname",       1),
]


# ================= IMPORTANCE SIGNALS =================

IMPORTANCE_SIGNALS = [
    "my name", "i am", "i study", "i go to", "i live", "my school",
    "my college", "my class", "my grade", "i am interested", "i love",
    "i enjoy", "i like", "my hobby", "preparing for", "my goal",
    "my target", "my aim", "i speak", "everyone calls me",
    "friends call me", "call me", "my age", "i am from", "my city",
    "my favourite", "my favorite", "i hate", "i prefer", "my exam",
    "i am in class", "i am in grade", "i am studying",
]

def _has_importance_signal(text: str) -> bool:
    t = text.lower()
    return any(s in t for s in IMPORTANCE_SIGNALS)


# ================= EXTRACTOR =================

def extract_and_save_facts(user_command: str):
    """
    Passively scan a user command and save any personal facts.
    Called automatically from brain_v4.py on every turn.

    Two-pass approach:
      Pass 1: Fast regex patterns
      Pass 2: LLM extraction (if regex found nothing but signals present)
    """
    text = user_command.strip()

    # Quick filter
    if not _has_importance_signal(text):
        return

    saved_any = False

    # ── Pass 1: Regex ──
    for pattern, fact_key, group_idx in PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        value = match.group(group_idx).strip()

        # Handle low-confidence name_candidate
        if fact_key == "name_candidate":
            words = value.lower().split()
            if len(words) == 1 and words[0] not in NOISE_WORDS:
                original = text[match.start(group_idx):match.end(group_idx)]
                if original[0].isupper():
                    _save("name", value)
                    saved_any = True
            continue

        # Skip noisy single-word values
        if value.lower() in NOISE_WORDS or len(value) < 2:
            continue

        _save(fact_key, value)
        saved_any = True

    # ── Pass 2: LLM fallback (only if regex found nothing) ──
    if not saved_any:
        _llm_extract(text)


def _llm_extract(text: str):
    """
    Ask Groq to extract personal facts as JSON.
    Runs in a background thread so it doesn't slow down the main loop.
    """
    def _run():
        try:
            from ai_router_v4 import extract_facts_with_llm
            facts = extract_facts_with_llm(text)
            if not facts:
                return
            for k, v in facts.items():
                if k and v and str(v).strip():
                    _save(k, str(v).strip())
            if facts:
                print(f"[SMART MEMORY] LLM extracted: {facts}")
        except Exception as e:
            print(f"[SMART MEMORY] LLM extraction error: {e}")

    import threading
    threading.Thread(target=_run, daemon=True).start()


# ================= RECALL / SUMMARY =================

def get_all_facts() -> dict:
    """Return all saved smart facts."""
    from memory_db import get_all_facts as db_get_all
    return db_get_all()


def build_facts_context() -> str:
    """
    Build a compact context string to inject into AI prompts.
    Example:
        [User facts: name=Sri | school=XYZ | interest=chess, coding]
    """
    facts = get_all_facts()
    if not facts:
        return ""

    parts = []
    for key, value in list(facts.items())[:12]:  # cap to avoid token bloat
        if isinstance(value, list):
            parts.append(f"{key}={', '.join(str(v) for v in value)}")
        else:
            parts.append(f"{key}={value}")

    return "[User facts: " + " | ".join(parts) + "]"


def summarise_facts_for_user() -> str:
    """
    Return a natural-language summary of everything FRIDAY knows.
    Triggered by: 'what do you know about me'
    """
    facts = get_all_facts()
    if not facts:
        return (
            "I have not learned anything specific about you yet. "
            "Just keep talking to me naturally and I will pick things up."
        )

    lines = ["Here is what I know about you so far:"]
    for key, value in facts.items():
        label = key.replace("_", " ").title()
        if isinstance(value, list):
            lines.append(f"  {label}: {', '.join(str(v) for v in value)}")
        else:
            lines.append(f"  {label}: {value}")

    return "\n".join(lines)


def forget_fact(key: str) -> bool:
    """Remove a specific fact from memory."""
    from memory_db import delete_fact
    return delete_fact(key)
