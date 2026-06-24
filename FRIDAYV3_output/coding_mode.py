"""
coding_mode.py — FRIDAY Coding Mode
====================================
Gives FRIDAY full access to the currently open VS Code file.
Uses nvidia/nemotron-3-super-120b-a12b:free via OpenRouter.

Features:
- Voice commands to explain, refactor, fix, add features to the open file
- Shows diff as ghost text in VS Code (like autocomplete)
- Tab to accept, Escape to dismiss
- Auto line-completion after pause in typing (handled by VS Code extension)

Setup:
  Add OPENROUTER_API_KEY to your .env or config.py
"""

import os
import json
import time
import subprocess
import tempfile
import threading
import requests

from voice import speak

try:
    from config import OLLAMA_MODEL, OLLAMA_URL
except Exception:
    OLLAMA_MODEL, OLLAMA_URL = "phi3", "http://localhost:11434/api/generate"


# ── OpenRouter config ──
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL   = "nvidia/nemotron-3-super-120b-a12b:free"
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"

# ── Shared temp file that the VS Code extension watches ──
SUGGESTION_FILE = os.path.join(tempfile.gettempdir(), "friday_suggestion.json")
ACTIVE_FILE     = os.path.join(tempfile.gettempdir(), "friday_coding_active.flag")

# ── State ──
_coding_active = False


# =============================================================================
# 🔌 OpenRouter call
# =============================================================================

def call_openrouter(system_prompt: str, user_prompt: str, max_tokens: int = 2048) -> str:
    """Call Nemotron 3 Super via OpenRouter."""
    if not OPENROUTER_API_KEY:
        speak("OpenRouter API key is not set. Please add it to your dot env file.")
        return ""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://friday-assistant.local",
        "X-Title":       "FRIDAY",
    }

    body = {
        "model": OPENROUTER_MODEL,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
    }

    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except requests.exceptions.Timeout:
        speak("The AI took too long to respond. Try again.")
        return ""
    except Exception as e:
        print(f"[CODING MODE] OpenRouter error: {e}")
        speak("There was an error reaching the coding AI.")
        return ""


# =============================================================================
# 📂 VS Code file access
# =============================================================================

def get_active_vscode_file() -> str | None:
    """Return the path of the currently active file in VS Code."""
    try:
        result = subprocess.run(
            ["code", "--status"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if line.strip().startswith("Active:"):
                path = line.split("Active:")[-1].strip()
                if os.path.isfile(path):
                    return path
    except Exception:
        pass

    # Fallback: read from the shared state file the extension writes
    state_file = os.path.join(tempfile.gettempdir(), "friday_active_file.txt")
    if os.path.isfile(state_file):
        with open(state_file) as f:
            path = f.read().strip()
            if os.path.isfile(path):
                return path

    return None

def read_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[CODING MODE] Cannot read file: {e}")
        return ""


def write_file(path: str, content: str):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"[CODING MODE] Cannot write file: {e}")


# =============================================================================
# 💡 Send suggestion to VS Code extension
# =============================================================================

def send_suggestion(original: str, suggested: str, file_path: str, mode: str = "diff"):
    """
    Write suggestion JSON that the VS Code extension picks up.

    mode:
      'diff'     → show inline diff, Tab to accept
      'complete' → ghost text line completion at cursor
    """
    payload = {
        "mode":        mode,
        "file_path":   file_path,
        "original":    original,
        "suggested":   suggested,
        "timestamp":   time.time(),
    }
    with open(SUGGESTION_FILE, "w") as f:
        json.dump(payload, f)
    print(f"[CODING MODE] Suggestion written ({mode})")


def clear_suggestion():
    """Remove the suggestion file (dismisses ghost text in VS Code)."""
    if os.path.exists(SUGGESTION_FILE):
        os.remove(SUGGESTION_FILE)


# =============================================================================
# 🤖 AI actions
# =============================================================================

SYSTEM_PROMPT = """You are FRIDAY, an expert AI coding assistant integrated into VS Code.
You have full access to the user's currently open file.

Rules:
- Return ONLY the modified/completed code — no markdown fences, no explanations outside the code
- Preserve the original code style, indentation, and language
- For explanations, speak naturally in 2-3 sentences
- For completions, return only the completed line(s), nothing else
- Never add placeholder comments like '# TODO' unless asked
"""


def action_explain(file_path: str, code: str, command: str):
    """Explain the current file or a specific part."""
    speak("Let me read the file.")
    prompt = f"File: {file_path}\n\nCode:\n{code}\n\nUser asked: {command}\n\nExplain this concisely in 2-3 sentences as FRIDAY."
    response = call_openrouter(SYSTEM_PROMPT, prompt, max_tokens=300)
    if response:
        print(f"[CODING MODE] Explanation: {response}")
        speak(response)


def action_refactor(file_path: str, code: str, command: str):
    """Refactor the entire file."""
    speak("Refactoring. One moment.")
    prompt = (
        f"File: {file_path}\n\nOriginal code:\n{code}\n\n"
        f"User request: {command}\n\n"
        "Return the complete refactored file. Code only, no markdown."
    )
    suggested = call_openrouter(SYSTEM_PROMPT, prompt, max_tokens=4096)
    if suggested:
        send_suggestion(code, suggested, file_path, mode="diff")
        speak("Done. Review the changes in VS Code and press Tab to accept, or Escape to dismiss.")


def action_fix(file_path: str, code: str, command: str):
    """Fix bugs or errors in the file."""
    speak("Analysing the code for issues.")
    prompt = (
        f"File: {file_path}\n\nCode:\n{code}\n\n"
        f"User request: {command}\n\n"
        "Fix all issues. Return the complete corrected file. Code only, no markdown."
    )
    suggested = call_openrouter(SYSTEM_PROMPT, prompt, max_tokens=4096)
    if suggested:
        send_suggestion(code, suggested, file_path, mode="diff")
        speak("Fixed. Press Tab in VS Code to apply, or Escape to dismiss.")


def action_add_feature(file_path: str, code: str, command: str):
    """Add a new feature or block of code."""
    speak("On it.")
    prompt = (
        f"File: {file_path}\n\nCurrent code:\n{code}\n\n"
        f"User request: {command}\n\n"
        "Add the requested feature. Return the complete updated file. Code only, no markdown."
    )
    suggested = call_openrouter(SYSTEM_PROMPT, prompt, max_tokens=4096)
    if suggested:
        send_suggestion(code, suggested, file_path, mode="diff")
        speak("Added. Review in VS Code and press Tab to accept.")


def action_complete_line(file_path: str, code: str, cursor_line: str):
    """Auto-complete the current line."""
    prompt = (
        f"File: {file_path}\n\nFull file context:\n{code}\n\n"
        f"Current incomplete line: {cursor_line}\n\n"
        "Complete this line. Return ONLY the completed version of that single line. No explanation."
    )
    suggested = call_openrouter(SYSTEM_PROMPT, prompt, max_tokens=150)
    if suggested:
        send_suggestion(cursor_line, suggested, file_path, mode="complete")


# =============================================================================
# 🎯 Command router
# =============================================================================

EXPLAIN_TRIGGERS  = [
    "explain", "what does", "what is this", "how does this", "describe",
    "walk me through", "what's going on", "what's happening", "understand this",
]
REFACTOR_TRIGGERS = [
    "refactor", "clean up", "cleanup", "improve", "optimise", "optimize",
    "rewrite", "simplify", "restructure", "tidy", "make this better",
    "make it better", "polish", "style", "format", "make the", "make this",
    "nicer", "modernize", "modernise",
]
FIX_TRIGGERS      = [
    "fix", "debug", "correct", "there is an error", "there is a bug",
    "broken", "bug", "error", "not working", "doesn't work", "isn't working",
    "issue", "crash", "find the bug", "find the issue", "wrong with",
]
ADD_TRIGGERS      = [
    "add", "implement", "create", "write a function", "write a class",
    "insert", "build", "new feature", "make a", "generate", "set up",
]


def _classify_with_nlp(command: str) -> str:
    """
    Second-pass classifier for commands the trigger-word list doesn't
    catch (e.g. 'what's wrong here', 'tidy this up a bit'). Runs locally
    via Ollama — fast, free, no Groq or OpenRouter round-trip just to
    decide whether a sentence is even coding-related.

    Returns one of: 'explain', 'refactor', 'fix', 'add', 'none'.
    """
    prompt = (
        "You are a strict intent classifier for a hands-free coding assistant. "
        "The user is in CODING MODE and just spoke this sentence out loud:\n\n"
        f"\"{command}\"\n\n"
        "Classify it into EXACTLY ONE category:\n"
        "EXPLAIN - asking what code does or how it works\n"
        "REFACTOR - asking to clean up, restyle, or improve existing code\n"
        "FIX - asking to fix a bug or error\n"
        "ADD - asking to add or implement something new\n"
        "NONE - not related to code at all (background noise, a different topic, small talk)\n\n"
        "Reply with exactly one word: EXPLAIN, REFACTOR, FIX, ADD, or NONE."
    )
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 5},
            },
            timeout=6,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip().upper()
        print(f"[CODING NLP] {command!r} -> {text!r}")
        for cat in ("EXPLAIN", "REFACTOR", "FIX", "ADD"):
            if cat in text:
                return cat.lower()
        return "none"
    except Exception as e:
        print(f"[CODING NLP] classifier unavailable, defaulting to none: {e}")
        return "none"


def _classify_action(command: str) -> str | None:
    """
    Returns 'explain' | 'refactor' | 'fix' | 'add' | None.
    Trigger words are checked first — instant, zero cost, and catch the
    large majority of phrasing. Only genuinely ambiguous sentences fall
    through to the local NLP classifier.
    """
    cmd = command.lower()
    if any(t in cmd for t in EXPLAIN_TRIGGERS):
        return "explain"
    if any(t in cmd for t in REFACTOR_TRIGGERS):
        return "refactor"
    if any(t in cmd for t in FIX_TRIGGERS):
        return "fix"
    if any(t in cmd for t in ADD_TRIGGERS):
        return "add"

    nlp_result = _classify_with_nlp(command)
    return nlp_result if nlp_result != "none" else None


def is_coding_command(command: str) -> bool:
    """
    Returns True if this command should be handled by coding mode.
    Kept for any external callers — note this re-runs classification, so
    prefer calling handle() directly and checking its return value when
    you also need the result acted on (avoids a duplicate NLP call).
    """
    return _classify_action(command) is not None


def handle(command: str) -> bool:
    """
    Main entry point called by brain_v4.py's coding-mode gate.
    Returns True if this was recognized as a coding request and acted on
    (or hit a clear handled failure like 'no file open'). Returns False
    if the sentence isn't actually coding-related, so the caller can
    silently ignore it without ever touching Groq or OpenRouter.
    """
    action = _classify_action(command)
    if action is None:
        return False  # not a coding command — caller should ignore quietly

    file_path = get_active_vscode_file()
    if not file_path:
        speak("I could not find the active VS Code file. Make sure a file is open and saved.")
        return True

    code = read_file(file_path)
    if not code:
        speak("The file appears to be empty.")
        return True

    action_fn = {
        "explain":  action_explain,
        "refactor": action_refactor,
        "fix":      action_fix,
        "add":      action_add_feature,
    }[action]

    # Run in a background thread so FRIDAY stays responsive
    threading.Thread(target=action_fn, args=(file_path, code, command), daemon=True).start()
    return True


# =============================================================================
# ⌨️ Auto line-completion watcher (called from coding mode startup)
# =============================================================================

def start_autocomplete_watcher():
    """
    Watches for cursor pause events sent by the VS Code extension.
    When the extension detects a pause in typing, it writes the current
    line to a trigger file. This watcher picks it up and calls the AI.
    """
    trigger_file = os.path.join(tempfile.gettempdir(), "friday_autocomplete_trigger.json")
    last_mtime   = 0

    print("[CODING MODE] Autocomplete watcher started.")

    while True:
        try:
            if os.path.isfile(trigger_file):
                mtime = os.path.getmtime(trigger_file)
                if mtime != last_mtime:
                    last_mtime = mtime
                    with open(trigger_file) as f:
                        data = json.load(f)
                    file_path   = data.get("file_path", "")
                    cursor_line = data.get("line", "")
                    if file_path and cursor_line.strip():
                        code = read_file(file_path)
                        # Run in background so watcher loop doesn't block
                        threading.Thread(
                            target=action_complete_line,
                            args=(file_path, code, cursor_line),
                            daemon=True
                        ).start()
        except Exception as e:
            print(f"[CODING MODE] Watcher error: {e}")

        time.sleep(0.5)