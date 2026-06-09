import json
import os
from datetime import datetime

MEMORY_FILE = "memory.json"

# ================= 📦 DEFAULT STRUCTURE =================

DEFAULT_MEMORY = {

    # "my name is Sri", "i like dark mode"
    "preferences": {},

    # "when i say home, open chrome and spotify"
    "shortcuts": {},

    # { "open chrome": 5, "play youtube": 3 }
    "usage": {},

    # last correction context for each intent
    "corrections": {},

    # Autonomous ChatGPT-style memory — saved passively from conversation
    # e.g. { "name": "Sri", "school": "XYZ School", "interest": ["rubix cubes"] }
    "smart_facts": {}
}

# ================= 💾 LOAD / SAVE =================

def load_memory():

    if not os.path.exists(MEMORY_FILE):
        save_memory(DEFAULT_MEMORY)
        return DEFAULT_MEMORY

    with open(MEMORY_FILE, "r") as f:

        data = json.load(f)

    # migrate old flat memory files gracefully
    for key in DEFAULT_MEMORY:
        if key not in data:
            data[key] = DEFAULT_MEMORY[key]

    return data


def save_memory(memory):

    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)

# ================= 🧠 PREFERENCES =================

def remember_preference(key, value):
    """Store a user preference. e.g. remember_preference('name', 'Sri')"""

    memory = load_memory()
    memory["preferences"][key.strip().lower()] = value.strip()
    save_memory(memory)

    print(f"[MEMORY] Preference saved: {key} = {value}")


def recall_preference(key):
    """Recall a stored preference by key."""

    memory = load_memory()
    return memory["preferences"].get(key.strip().lower(), None)


def recall_all_preferences():
    """Return all stored preferences."""

    memory = load_memory()
    return memory["preferences"]

# ================= ⚡ SHORTCUTS =================

def save_shortcut(trigger, actions):
    """
    Save a custom voice shortcut.
    trigger: str  — e.g. "home"
    actions: list — e.g. ["open chrome", "open spotify"]
    """

    memory = load_memory()
    memory["shortcuts"][trigger.strip().lower()] = actions
    save_memory(memory)

    print(f"[MEMORY] Shortcut saved: '{trigger}' -> {actions}")


def get_shortcut(trigger):
    """Return the action list for a shortcut trigger, or None."""

    memory = load_memory()
    return memory["shortcuts"].get(trigger.strip().lower(), None)


def delete_shortcut(trigger):
    """Remove a shortcut."""

    memory = load_memory()

    if trigger.strip().lower() in memory["shortcuts"]:
        del memory["shortcuts"][trigger.strip().lower()]
        save_memory(memory)
        return True

    return False


def recall_all_shortcuts():
    """Return all saved shortcuts."""

    memory = load_memory()
    return memory["shortcuts"]

# ================= 📊 USAGE TRACKING =================

def log_usage(command):
    """
    Increment usage count for a command.
    Call this every time a command is successfully handled.
    """

    memory = load_memory()

    key = command.strip().lower()

    if key not in memory["usage"]:
        memory["usage"][key] = {
            "count": 0,
            "last_used": None
        }

    memory["usage"][key]["count"] += 1
    memory["usage"][key]["last_used"] = datetime.now().strftime(
        "%Y-%m-%d %H:%M"
    )

    save_memory(memory)


def get_top_commands(n=5):
    """Return the top N most used commands."""

    memory = load_memory()

    sorted_usage = sorted(
        memory["usage"].items(),
        key=lambda x: x[1]["count"],
        reverse=True
    )

    return sorted_usage[:n]

# ================= 🔁 CORRECTIONS =================

def save_correction(original_command, corrected_command, intent):
    """
    Save a correction so FRIDAY learns from mistakes.
    e.g. user said "no, I meant open spotify" after FRIDAY opened chrome.
    """

    memory = load_memory()

    if intent not in memory["corrections"]:
        memory["corrections"][intent] = []

    memory["corrections"][intent].append({
        "original": original_command.strip().lower(),
        "corrected": corrected_command.strip().lower(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
    })

    # keep only last 20 corrections per intent to avoid bloat
    memory["corrections"][intent] = memory["corrections"][intent][-20:]

    save_memory(memory)

    print(
        f"[MEMORY] Correction saved: "
        f"'{original_command}' -> '{corrected_command}'"
    )


def get_corrections(intent):
    """Return correction history for a given intent."""

    memory = load_memory()
    return memory["corrections"].get(intent, [])

# ================= 🔁 LEGACY COMPAT =================
# Keep old remember/recall working so nothing else breaks

def remember(key, value):
    remember_preference(key, value)


def recall(key):
    result = recall_preference(key)
    return result if result else "I don't remember that yet."