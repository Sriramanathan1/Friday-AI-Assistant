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

EXPLAIN_TRIGGERS  = ["explain", "what does", "what is this", "how does this", "describe"]
REFACTOR_TRIGGERS = ["refactor", "clean up", "improve", "optimise", "optimize", "rewrite"]
FIX_TRIGGERS      = ["fix", "debug", "correct", "there is an error", "there is a bug", "broken"]
ADD_TRIGGERS      = ["add", "implement", "create", "write a function", "write a class", "insert"]


def is_coding_command(command: str) -> bool:
    """Returns True if this command should be handled by coding mode."""
    cmd = command.lower()
    all_triggers = EXPLAIN_TRIGGERS + REFACTOR_TRIGGERS + FIX_TRIGGERS + ADD_TRIGGERS
    return any(t in cmd for t in all_triggers)


def handle(command: str) -> bool:
    """Main entry point called by brain.py when coding mode is active."""

    cmd = command.lower()

    # Get active file
    file_path = get_active_vscode_file()
    if not file_path:
        speak("I could not find the active VS Code file. Make sure a file is open and saved.")
        return True

    code = read_file(file_path)
    if not code:
        speak("The file appears to be empty.")
        return True

    # Route to correct action in a background thread so FRIDAY stays responsive
    if any(t in cmd for t in EXPLAIN_TRIGGERS):
        threading.Thread(target=action_explain,  args=(file_path, code, command), daemon=True).start()
        return True

    if any(t in cmd for t in REFACTOR_TRIGGERS):
        threading.Thread(target=action_refactor, args=(file_path, code, command), daemon=True).start()
        return True

    if any(t in cmd for t in FIX_TRIGGERS):
        threading.Thread(target=action_fix,      args=(file_path, code, command), daemon=True).start()
        return True

    if any(t in cmd for t in ADD_TRIGGERS):
        threading.Thread(target=action_add_feature, args=(file_path, code, command), daemon=True).start()
        return True

    return False


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