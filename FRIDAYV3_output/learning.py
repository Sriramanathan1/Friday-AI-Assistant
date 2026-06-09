import re

from voice import speak
from nlp_router import classify, is_intent
from memory import (
    remember_preference,
    recall_preference,
    recall_all_preferences,
    save_shortcut,
    get_shortcut,
    delete_shortcut,
    recall_all_shortcuts,
    save_correction,
    get_top_commands,
    save_memory,
    load_memory
)

# ================= 🧠 LEARNING PLUGIN =================
# Handles:
#   1. Preferences  — "remember that I like dark mode"
#   2. Shortcuts    — "when I say home, open chrome and spotify"
#   3. Corrections  — "no I meant open spotify"
#   4. Usage stats  — "what do I use most"
#   5. Forget       — "forget that I like dark mode"
#   6. Delete       — "delete my home shortcut"

# ================= 🔍 TRIGGER DETECTION =================

CORRECTION_TRIGGERS = [
    "no i meant",
    "no, i meant",
    "thats wrong",
    "not that",
    "wrong one",
    "not what i wanted",
    "no friday",
]

# ── Shortcut triggers: very specific, only match shortcut creation ──
SHORTCUT_TRIGGERS = [
    "when i say",
    "whenever i say",
    "if i say",
]

# ── Forget triggers ──
FORGET_TRIGGERS = [
    "forget that",
    "forget my",
    "forget i",
    "dont remember"
]

# ── Delete shortcut triggers ──
DELETE_SHORTCUT_TRIGGERS = [
    "delete my",
    "remove my",
    "delete shortcut",
    "remove shortcut"
]

# ── Preference triggers: must start with or contain these exact phrases ──
# These are STRICT — they must appear unambiguously
PREFERENCE_TRIGGERS = [
    "call me ",
    "my name is ",
    "remember that i like",
    "remember that i prefer",
    "remember that i hate",
    "remember that i love",
    "remember i like",
    "remember i prefer",
    "i prefer ",
    "i like ",
    "i love ",
    "i hate ",
    "i always use ",
]

# ── Recall triggers: only fire on very specific memory-recall phrases ──
RECALL_TRIGGERS = [
    "what do you know about me",
    "what have you learned about me",
    "show my preferences",
    "tell me my preferences",
    "what are my shortcuts",
    "list my shortcuts",
    "what do i use most",
    "show my usage stats",
]

# ── Phrases that MUST NOT be intercepted by learning even if a trigger word appears ──
# These are study/notes commands that contain words like "my" or "notes"
LEARNING_EXCLUSIONS = [
    "summarize",
    "summarise",
    "make notes",
    "create notes",
    "create flashcards",
    "generate notes",
    "bullet notes",
    "study notes",
    "from my screen",
    "from this pdf",
    "from this document",
    "homework",
    "solve",
    "explain",
    "quiz",
    "simulate",
    "study plan",
    "study schedule",
    "my downloads",
    "scan downloads",
]


def is_learning_command(command):
    """
    Detects learning commands (preferences, shortcuts, corrections, recall).
    Uses strict keyword matching with explicit exclusions to prevent
    study/notes commands from being intercepted.

    Returns: 'correction' | 'preference' | 'shortcut' | 'recall' |
             'forget' | 'delete_shortcut' | None
    """

    cmd = command.lower().strip()

    # ── Step 0: Check exclusions first — these NEVER belong to learning ──
    for exclusion in LEARNING_EXCLUSIONS:
        if exclusion in cmd:
            return None

    # ── Corrections: always catch these (time-sensitive, must fire fast) ──
    for trigger in CORRECTION_TRIGGERS:
        if trigger in cmd:
            return "correction"

    # ── Shortcuts: only match shortcut creation phrases ──
    for trigger in SHORTCUT_TRIGGERS:
        if trigger in cmd:
            return "shortcut"

    # ── Forget / delete shortcut ──
    for trigger in FORGET_TRIGGERS:
        if trigger in cmd:
            return "forget"

    for trigger in DELETE_SHORTCUT_TRIGGERS:
        if trigger in cmd:
            return "delete_shortcut"

    # ── Preferences: match strict phrases only ──
    for trigger in PREFERENCE_TRIGGERS:
        if trigger in cmd:
            return "preference"

    # ── Recall: match exact recall phrases only ──
    for trigger in RECALL_TRIGGERS:
        if trigger in cmd:
            return "recall"

    # ── NLP fallback: only use for preference/recall with HIGH threshold ──
    # This catches natural variants like "I always prefer Chrome"
    # but the 0.60 threshold prevents ambiguous matches
    intent, score, _ = classify(command, "learning", threshold=0.60)
    if intent in ("preference", "recall", "shortcut"):
        # Double-check: make sure score is genuinely high
        if score >= 0.60:
            print(f"[LEARNING NLP FALLBACK] intent={intent} score={score:.3f}")
            return intent

    return None

# ================= 1. PREFERENCES =================

def handle_preference(command):

    cmd = command.lower().strip()

    if "call me " in cmd:
        name = cmd.split("call me ", 1)[1].strip()
        remember_preference("name", name)
        speak("Got it. I will call you " + name + " from now on.")
        return True

    if "my name is " in cmd:
        name = cmd.split("my name is ", 1)[1].strip()
        remember_preference("name", name)
        speak("Nice to meet you " + name + ". I will remember that.")
        return True

    for trigger in ["remember that i ", "remember i "]:
        if trigger in cmd:
            remainder = cmd.split(trigger, 1)[1].strip()
            _store_natural_preference(remainder)
            return True

    for trigger in ["i prefer ", "i like ", "i love ", "i hate ", "i always "]:
        if cmd.startswith(trigger) or (" " + trigger) in cmd:
            idx = cmd.find(trigger)
            remainder = cmd[idx + len(trigger):].strip()
            _store_natural_preference(trigger.strip() + " " + remainder)
            return True

    speak("I heard you but was not sure what to remember. Try saying: remember that I like dark mode.")
    return True


def _store_natural_preference(phrase):

    phrase = phrase.strip().lower()

    CATEGORIES = {
        "browser":      ["chrome", "firefox", "edge", "opera", "brave"],
        "theme":        ["dark mode", "light mode", "dark", "light"],
        "music":        ["spotify", "youtube music", "apple music"],
        "editor":       ["vscode", "pycharm", "notepad", "sublime"],
        "name":         ["call me", "name is"],
        "notification": ["loud", "silent", "quiet", "notifications"],
    }

    matched_category = None

    for category, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in phrase:
                matched_category = category
                break

    FILLER = ["i like", "i prefer", "i love", "i hate",
              "i always", "like", "prefer", "love", "hate", "use", "always"]

    value = phrase
    for filler in FILLER:
        value = value.replace(filler, "").strip()

    key = matched_category if matched_category else phrase.split()[0]

    remember_preference(key, value)
    speak("Got it. I will remember that you " + phrase + ".")

# ================= 2. SHORTCUTS =================

def handle_shortcut(command):

    cmd = command.lower().strip()

    # Regex looks for action verb as separator instead of relying on comma
    # so it works even when STT drops punctuation.
    # "on" is normalised to "and" by brain.py before reaching here.

    match = re.search(
        r"(?:when(?:ever)?|if) i say (.+?)(?:[,،])? ?(open|play|launch|start|close|search|type|run) (.+)",
        cmd
    )

    if not match:
        speak("I did not catch that. Try: when I say home, open chrome and spotify.")
        return True

    trigger     = match.group(1).strip()
    action_verb = match.group(2).strip()
    actions_raw = match.group(3).strip()

    # split on "and", "on" (STT mishear), or comma
    actions = [
        a.strip()
        for a in re.split(r"\band\b|\bon\b|,", actions_raw)
        if a.strip()
    ]

    # prepend the action verb back onto first action so it makes sense
    # e.g. trigger="home", verb="open", actions=["chrome","spotify"]
    # -> stored as ["open chrome", "spotify"]
    # brain will route each action through process_command anyway
    actions[0] = action_verb + " " + actions[0]

    save_shortcut(trigger, actions)

    actions_spoken = " and ".join(actions)
    speak("Shortcut saved. When you say " + trigger + ", I will " + actions_spoken + ".")

    return True


def run_shortcut(trigger, process_fn):

    actions = get_shortcut(trigger)

    if not actions:
        return False

    speak("Running your " + trigger + " shortcut.")

    for action in actions:
        print(f"[SHORTCUT] Running: {action}")
        process_fn(action)

    return True


def check_shortcut(command, process_fn):

    cmd = command.lower().strip()
    return run_shortcut(cmd, process_fn)

# ================= 3. CORRECTIONS =================

last_command = {"text": None, "intent": None}


def handle_correction(command, process_fn):

    cmd = command.lower().strip()

    corrected = None

    for trigger in CORRECTION_TRIGGERS:
        if trigger in cmd:
            corrected = cmd.split(trigger, 1)[1].strip()
            break

    if not corrected:
        speak("Sorry about that. What did you want me to do?")
        return True

    if last_command["text"]:
        save_correction(
            original_command=last_command["text"],
            corrected_command=corrected,
            intent=last_command["intent"] or "unknown"
        )

    speak("My mistake. Let me " + corrected + ".")
    process_fn(corrected)

    return True

# ================= 4. RECALL / STATS =================

def handle_recall(command):

    cmd = command.lower().strip()

    if "use most" in cmd or "most used" in cmd:

        top = get_top_commands(5)

        if not top:
            speak("I have not tracked enough usage yet.")
            return True

        lines = [c + " " + str(data["count"]) + " times" for c, data in top]
        summary = ", ".join(lines[:3])
        speak("Your most used commands are: " + summary + ".")

        print("\n[USAGE STATS]")
        for c, data in top:
            print(f"  {c}: {data['count']}x (last: {data['last_used']})")

        return True

    if "shortcut" in cmd:

        shortcuts = recall_all_shortcuts()

        if not shortcuts:
            speak("You have not saved any shortcuts yet.")
            return True

        names = ", ".join(shortcuts.keys())
        speak("Your shortcuts are: " + names + ".")

        print("\n[SHORTCUTS]")
        for trigger, actions in shortcuts.items():
            print(f"  '{trigger}' -> {actions}")

        return True

    prefs = recall_all_preferences()

    if not prefs:
        speak("I do not know much about you yet. Tell me your preferences!")
        return True

    name = prefs.get("name", None)
    greeting = "Here is what I know about you" + (", " + name if name else "") + ". "

    lines = [k + ": " + v for k, v in prefs.items()]
    summary = ". ".join(lines[:4])

    speak(greeting + summary)

    print("\n[PREFERENCES]")
    for k, v in prefs.items():
        print(f"  {k}: {v}")

    return True

# ================= 5. FORGET PREFERENCE =================

def handle_forget(command):

    cmd = command.lower().strip()

    memory = load_memory()

    key = None

    for trigger in FORGET_TRIGGERS:
        if trigger in cmd:
            key = cmd.split(trigger, 1)[1].strip()
            break

    if not key:
        speak("I was not sure what to forget. Try: forget that I like dark mode.")
        return True

    for filler in ["i like", "i prefer", "i hate", "i love", "that i", "that", "my", "i"]:
        key = key.replace(filler, "").strip()

    if key in memory["preferences"]:
        del memory["preferences"][key]
        save_memory(memory)
        speak("Done. I have forgotten that.")
    else:
        matched_key = next(
            (k for k in memory["preferences"] if key in k or k in key),
            None
        )

        if matched_key:
            del memory["preferences"][matched_key]
            save_memory(memory)
            speak("Done. I have forgotten your " + matched_key + " preference.")
        else:
            speak("I do not have anything saved about " + key + ".")

    return True

# ================= 6. DELETE SHORTCUT =================

def handle_delete_shortcut(command):

    cmd = command.lower().strip()

    match = re.search(r"(?:delete|remove) my (.+?) shortcut", cmd)

    if not match:
        match = re.search(r"(?:delete|remove) (?:my )?(.+)", cmd)

    if not match:
        speak("Which shortcut should I delete?")
        return True

    trigger = match.group(1).strip()
    trigger = trigger.replace("shortcut", "").strip()

    success = delete_shortcut(trigger)

    if success:
        speak("Done. I have deleted your " + trigger + " shortcut.")
    else:
        speak("I could not find a shortcut called " + trigger + ".")

    return True

# ================= 🎯 MAIN HANDLE =================

def handle(command, learning_type, process_fn=None):
    """
    Central entry point called from brain.py.

    learning_type: 'correction' | 'preference' | 'shortcut' | 'recall' |
                   'forget' | 'delete_shortcut'
    process_fn: brain.process_command — needed for corrections and shortcuts
    """

    if learning_type == "preference":
        return handle_preference(command)

    if learning_type == "shortcut":
        return handle_shortcut(command)

    if learning_type == "correction":
        return handle_correction(command, process_fn)

    if learning_type == "recall":
        return handle_recall(command)

    if learning_type == "forget":
        return handle_forget(command)

    if learning_type == "delete_shortcut":
        return handle_delete_shortcut(command)

    return False