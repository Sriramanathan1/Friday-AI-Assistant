"""
smart_memory.py — ChatGPT-style autonomous memory for FRIDAY

FRIDAY passively listens to every conversation turn and autonomously
decides whether to save important facts about the user — without being
told to. Just like ChatGPT's Memory feature.

What it saves (examples):
  - "my name is XYZ"         → name = XYZ
  - "I study at XYZ school"  → school = XYZ
  - "I am interested in rubix cubes" → interest: rubix cubes
  - "I am 16 years old"      → age = 16
  - "I live in Chennai"      → city = Chennai
  - "my exam is next Monday" → upcoming_exam = next Monday
  - "I am preparing for JEE" → exam_goal = JEE

How it works:
  1. Every user command passes through extract_and_save_facts()
  2. NLP + pattern matching detects important personal facts
  3. Facts are saved to memory.json under a new "smart_facts" key
  4. FRIDAY injects these facts into every AI prompt (build_facts_context)
  5. User can ask "what do you know about me" to see all saved facts
"""

import re
import json
import os
from datetime import datetime

from memory import load_memory, save_memory

# ================= 📁 MEMORY KEY =================
FACTS_KEY = "smart_facts"

# ================= 🔍 PATTERN-BASED EXTRACTORS =================
# Each extractor is (compiled_regex, fact_key, value_group_index)

PATTERNS = [

    # ── Name ──
    (re.compile(r"\bmy name is ([a-z][a-z\s]{1,30})", re.I),           "name",          1),
    (re.compile(r"\bcall me ([a-z][a-z\s]{1,20})\b", re.I),            "name",          1),
    (re.compile(r"\bi am ([a-z][a-z\s]{1,20})\b", re.I),               "name_candidate", 1),  # lower confidence

    # ── School / College ──
    (re.compile(r"\bi (?:study|go|attend|am) (?:at|in|to) ([a-z0-9\s,.-]{4,60}school[a-z\s]*)", re.I),   "school", 1),
    (re.compile(r"\bi (?:study|go|attend|am) (?:at|in|to) ([a-z0-9\s,.-]{4,60}college[a-z\s]*)", re.I),  "college", 1),
    (re.compile(r"\bmy school is ([a-z0-9\s,.-]{4,60})", re.I),        "school",        1),
    (re.compile(r"\bmy college is ([a-z0-9\s,.-]{4,60})", re.I),       "college",       1),
    (re.compile(r"\bstudying (?:at|in) ([a-z0-9\s,.-]{4,60})", re.I),  "school",        1),

    # ── Class / Grade ──
    (re.compile(r"\bi(?:'m| am) in (?:class|grade) (\d{1,2}[a-z]?)\b", re.I), "class", 1),
    (re.compile(r"\bclass (\d{1,2}[a-z]?)\b", re.I),                   "class",         1),

    # ── Age ──
    (re.compile(r"\bi(?:'m| am) (\d{1,2}) years? old\b", re.I),        "age",           1),
    (re.compile(r"\bmy age is (\d{1,2})\b", re.I),                     "age",           1),

    # ── City / Location ──
    (re.compile(r"\bi live in ([a-z][a-z\s,]{2,40})\b", re.I),         "city",          1),
    (re.compile(r"\bi(?:'m| am) from ([a-z][a-z\s,]{2,40})\b", re.I),  "hometown",      1),
    (re.compile(r"\bmy city is ([a-z][a-z\s,]{2,30})\b", re.I),        "city",          1),

    # ── Interests / Hobbies ──
    (re.compile(r"\bi(?:'m| am) interested in ([a-z][a-z\s,]{3,60})", re.I),   "interest",  1),
    (re.compile(r"\bi love ([a-z][a-z\s,]{3,50})\b", re.I),            "interest",      1),
    (re.compile(r"\bi enjoy ([a-z][a-z\s,]{3,50})\b", re.I),           "interest",      1),
    (re.compile(r"\bmy hobby is ([a-z][a-z\s,]{3,50})\b", re.I),       "hobby",         1),
    (re.compile(r"\bi like (?:to |)([a-z][a-z\s,]{3,50})\b", re.I),    "interest",      1),

    # ── Exam goals ──
    (re.compile(r"\bpreparing for ([a-z][a-z\s]{2,30})\b", re.I),      "exam_goal",     1),
    (re.compile(r"\bmy (?:goal|target|aim) is ([a-z][a-z\s]{2,50})\b", re.I), "goal",   1),

    # ── Subject preference ──
    (re.compile(r"\bi (?:love|like|prefer|enjoy) ([a-z]+)\b.{0,20}?(?:subject|class|topic)", re.I), "favourite_subject", 1),

    # ── Language ──
    (re.compile(r"\bi speak ([a-z][a-z\s,]{2,30})\b", re.I),           "language",      1),

    # ── Nickname ──
    (re.compile(r"\beveryone calls me ([a-z][a-z\s]{1,20})\b", re.I),  "nickname",      1),
    (re.compile(r"\bfriends call me ([a-z][a-z\s]{1,20})\b", re.I),    "nickname",      1),
]

# Words that indicate this is NOT a personal fact (false positive guard)
NOISE_WORDS = {
    "a", "an", "the", "this", "that", "it", "they", "he", "she", "we",
    "going", "trying", "not", "just", "also", "done", "sure", "great",
    "bad", "good", "okay", "yes", "no", "able"
}

# ================= 🧠 NLP IMPORTANCE SCORER =================
# Beyond patterns, we use keyword signals to detect important personal context

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
    return any(signal in t for signal in IMPORTANCE_SIGNALS)


# ================= 💾 FACT STORAGE =================

def _load_facts() -> dict:
    memory = load_memory()
    if FACTS_KEY not in memory:
        memory[FACTS_KEY] = {}
    return memory[FACTS_KEY]


def _save_fact(key: str, value: str, source: str = ""):
    """Persist a single fact to memory.json"""
    memory = load_memory()
    if FACTS_KEY not in memory:
        memory[FACTS_KEY] = {}

    # Normalise
    key   = key.strip().lower()
    value = value.strip().rstrip(".,!?")

    # Skip very short or noisy values
    if len(value) < 2 or value.lower() in NOISE_WORDS:
        return

    # For list-type facts (interests, hobbies), append rather than overwrite
    LIST_KEYS = {"interest", "hobby", "language"}
    if key in LIST_KEYS:
        existing = memory[FACTS_KEY].get(key, [])
        if isinstance(existing, str):
            existing = [existing]
        if value.lower() not in [v.lower() for v in existing]:
            existing.append(value)
            memory[FACTS_KEY][key] = existing
            print(f"[SMART MEMORY] Appended {key}: {value}")
    else:
        old = memory[FACTS_KEY].get(key)
        memory[FACTS_KEY][key] = value
        if old != value:
            print(f"[SMART MEMORY] Saved {key}: {value!r}")

    memory[FACTS_KEY]["_last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_memory(memory)


# ================= 🔎 EXTRACTOR =================

def extract_and_save_facts(user_command: str):
    """
    Passively scan a user command and save any important personal facts.
    Called automatically from brain.py on every turn — no user instruction needed.
    """
    text = user_command.strip()

    # Quick filter: if no importance signal, skip expensive regex scan
    if not _has_importance_signal(text):
        return

    saved_any = False

    for pattern, fact_key, group_idx in PATTERNS:
        match = pattern.search(text)
        if match:
            value = match.group(group_idx).strip()

            # Skip low-confidence "i am <name>" if it looks like a statement, not a name
            # e.g. "i am ready" should not save "ready" as name
            if fact_key == "name_candidate":
                words = value.lower().split()
                if len(words) == 1 and words[0] not in NOISE_WORDS:
                    # Only save if it looks like a proper name (capitalised in original)
                    original_word = text[match.start(group_idx):match.end(group_idx)]
                    if original_word[0].isupper():
                        _save_fact("name", value, source=text)
                        saved_any = True
                continue  # don't process name_candidate further

            _save_fact(fact_key, value, source=text)
            saved_any = True

    if saved_any:
        print(f"[SMART MEMORY] Facts updated from: {text[:60]}")


# ================= 📜 RECALL =================

def get_all_facts() -> dict:
    """Return all saved smart facts."""
    facts = _load_facts()
    return {k: v for k, v in facts.items() if not k.startswith("_")}


def build_facts_context() -> str:
    """
    Build a compact context string to inject into AI prompts.
    Example:
        [User facts: name=Sri, school=XYZ School, interest=rubix cubes, coding]
    """
    facts = get_all_facts()
    if not facts:
        return ""

    parts = []
    for key, value in facts.items():
        if isinstance(value, list):
            parts.append(f"{key}={', '.join(value)}")
        else:
            parts.append(f"{key}={value}")

    return "[User facts: " + " | ".join(parts) + "]"


def summarise_facts_for_user() -> str:
    """
    Return a natural-language summary of everything FRIDAY knows about the user.
    Used when user asks "what do you know about me".
    """
    facts = get_all_facts()
    if not facts:
        return "I have not learned anything specific about you yet. Just keep talking to me naturally and I will pick up on things."

    lines = ["Here is what I know about you so far:"]
    for key, value in facts.items():
        if isinstance(value, list):
            lines.append(f"  • {key.replace('_',' ').title()}: {', '.join(value)}")
        else:
            lines.append(f"  • {key.replace('_',' ').title()}: {value}")

    return "\n".join(lines)


def forget_fact(key: str) -> bool:
    """Remove a specific fact from smart memory."""
    memory = load_memory()
    if FACTS_KEY in memory and key.lower() in memory[FACTS_KEY]:
        del memory[FACTS_KEY][key.lower()]
        save_memory(memory)
        print(f"[SMART MEMORY] Forgot: {key}")
        return True
    return False
