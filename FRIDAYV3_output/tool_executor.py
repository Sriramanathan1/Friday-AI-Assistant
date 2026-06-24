"""
tool_executor.py — FRIDAY Tool Executor (V4)

Receives a tool_call dict from Groq (name + arguments) and
runs the corresponding function.

CHANGES FROM V3:
  - send_whatsapp   → direct pywhatkit call (no plugin string parsing)
  - organise_files  → direct shutil logic (no plugin string parsing)
  - find_files      → direct os.walk logic (no plugin string parsing)
  - set_mode        → direct mode logic (no plugin string parsing)
  - smart_type      → uses ai_router_v4.ask_compose
  - coding_assist   → uses ai_router_v4.ask_coding
  - study_assist    → uses ai_router_v4.ask_tutor
  - save/recall/forget_memory → use memory_db (SQLite)
  - iot_control     → uses iot_plugin (alexa-remote2 bridge based)
  + search_memory   → NEW: fuzzy search facts + episodes
  + ingest_document → NEW: RAG document ingestion
  + query_documents → NEW: RAG document search
  + plan_task       → NEW: multi-step task planner
  + create_workflow → NEW: save named workflow
  + run_workflow    → NEW: execute saved workflow
"""

import os
import sys
import json
import time
import shutil
import webbrowser
import urllib.parse
import datetime
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice import speak

# ============================================================
# SYSTEM
# ============================================================

def control_volume(action: str, steps: int = 5) -> str:
    import pyautogui
    key_map = {
        "increase": "volumeup",
        "decrease": "volumedown",
        "mute":     "volumemute",
        "unmute":   "volumemute",
    }
    key = key_map.get(action)
    if not key:
        return f"Unknown volume action: {action}"
    presses = steps if action in ("increase", "decrease") else 1
    pyautogui.press(key, presses=presses)
    msg = f"Volume {action}d."
    speak(msg)
    return msg


def take_screenshot(save_path: str = "screenshot.png") -> str:
    import pyautogui
    screenshot = pyautogui.screenshot()
    screenshot.save(save_path)
    msg = f"Screenshot saved to {save_path}."
    speak("Screenshot saved.")
    return msg


def power_control(action: str) -> str:
    if action == "shutdown":
        speak("Shutting down the computer.")
        os.system("shutdown /s /t 3")
        return "Shutting down."
    elif action == "restart":
        speak("Restarting the computer.")
        os.system("shutdown /r /t 3")
        return "Restarting."
    return f"Unknown power action: {action}"


# ============================================================
# APP CONTROL
# ============================================================

def open_app(app: str) -> str:
    app = app.lower().strip()
    APP_COMMANDS = {
        "chrome":        "start chrome",
        "browser":       "start chrome",
        "notepad":       "notepad",
        "calculator":    "calc",
        "calc":          "calc",
        "vscode":        "code",
        "vs code":       "code",
        "spotify":       "spotify",
        "explorer":      "explorer",
        "file explorer": "explorer",
        "paint":         "mspaint",
        "word":          "winword",
        "excel":         "excel",
        "powerpoint":    "powerpnt",
        "task manager":  "taskmgr",
    }
    cmd = APP_COMMANDS.get(app)
    if cmd:
        os.system(cmd)
        speak(f"Opening {app}.")
        return f"Opened {app}."
    os.system(f"start {app}")
    speak(f"Trying to open {app}.")
    return f"Attempted to open {app}."


# ============================================================
# WEB
# ============================================================

def open_website(site: str) -> str:
    SITES = {
        "youtube":  "https://youtube.com",
        "gmail":    "https://mail.google.com",
        "whatsapp": "https://web.whatsapp.com",
        "linkedin": "https://linkedin.com",
        "github":   "https://github.com",
        "chatgpt":  "https://chatgpt.com",
    }
    url = SITES.get(site.lower())
    if url:
        webbrowser.open(url)
        speak(f"Opening {site}.")
        return f"Opened {site}."
    return f"Unknown site: {site}"


def web_search(query: str, open_browser: bool = False) -> str:
    try:
        from plugins.web import fetch_search_snippet
        snippet = fetch_search_snippet(query)
    except Exception as e:
        snippet = ""
        print(f"[TOOL] web_search error: {e}")

    if open_browser:
        url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
        webbrowser.open(url)

    if snippet:
        return f"Search results for '{query}':\n{snippet}"
    return f"No results found for '{query}'."


def get_weather(location: str = "") -> str:
    from plugins.web import fetch_weather
    if not location:
        try:
            from brain_v4 import get_location
            location = get_location()
        except Exception:
            location = "current location"
    result = fetch_weather(location)
    return result if result else f"Could not fetch weather for {location}."


def youtube_search(query: str) -> str:
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    webbrowser.open(url)
    speak(f"Searching YouTube for {query}.")
    return f"Opened YouTube search for '{query}'."


# ============================================================
# TIMER
# ============================================================

def set_timer(duration_seconds: int, label: str = "Timer") -> str:
    def _run():
        time.sleep(duration_seconds)
        msg = f"{label} done!"
        speak(msg)
        print(f"[TIMER] {msg}")

    threading.Thread(target=_run, daemon=True).start()
    mins, secs = divmod(duration_seconds, 60)
    if mins:
        human = f"{mins} minute{'s' if mins > 1 else ''}" + (f" {secs}s" if secs else "")
    else:
        human = f"{secs} second{'s' if secs > 1 else ''}"
    msg = f"{label} set for {human}."
    speak(msg)
    return msg


# ============================================================
# MESSAGING — Direct pywhatkit (no plugin string parsing)
# ============================================================

# Add your contacts here: name → phone (E.164 format)
CONTACTS = {
    "dad": "+919880393384",
    "mom": "",      # fill in
    "me":  "",      # fill in
}

def send_whatsapp(contact: str, message: str) -> str:
    """Send WhatsApp message directly via pywhatkit."""
    import pyautogui

    name = contact.strip().lower()
    phone = CONTACTS.get(name)

    if not phone:
        return f"Contact not found or no phone number saved for '{contact}'."

    try:
        import pywhatkit
        pywhatkit.sendwhatmsg_instantly(
            phone,
            message,
            wait_time=15,
            tab_close=False,
        )
        time.sleep(5)
        pyautogui.press("enter")
        speak(f"Message sent to {contact}.")
        return f"WhatsApp message sent to {contact}."
    except Exception as e:
        return f"WhatsApp error: {e}"


# ============================================================
# FILES — Direct logic (no plugin string parsing)
# ============================================================

FILE_CATEGORIES = {
    "Images":    (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"),
    "Videos":    (".mp4", ".mov", ".avi", ".mkv", ".wmv"),
    "Music":     (".mp3", ".wav", ".flac", ".aac", ".ogg"),
    "Documents": (".pdf", ".docx", ".txt", ".pptx", ".xlsx", ".csv", ".doc"),
    "Programs":  (".exe", ".msi", ".dmg"),
    "Code":      (".py", ".html", ".css", ".js", ".cpp", ".ino", ".java", ".ts"),
    "Archives":  (".zip", ".rar", ".7z", ".tar", ".gz"),
}

def organise_files(folder: str = "~/Downloads") -> str:
    """Sort files into category subfolders directly with shutil."""
    folder = os.path.expanduser(folder)
    if not os.path.isdir(folder):
        return f"Folder not found: {folder}"

    moved = 0
    for filename in os.listdir(folder):
        src = os.path.join(folder, filename)
        if os.path.isdir(src):
            continue
        ext = os.path.splitext(filename)[1].lower()
        category = next(
            (cat for cat, exts in FILE_CATEGORIES.items() if ext in exts),
            "Other"
        )
        dest_dir = os.path.join(folder, category)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, filename)
        if not os.path.exists(dest):
            shutil.move(src, dest)
            moved += 1

    msg = f"Organised {moved} files in {folder}."
    speak(msg)
    return msg


def find_files(query: str, folder: str = "~") -> str:
    """Search for files matching a query directly with os.walk."""
    folder = os.path.expanduser(folder)
    query_lower = query.lower()
    matches = []

    try:
        for root, dirs, files in os.walk(folder):
            # Skip hidden and system dirs for performance
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       ("AppData", "node_modules", "__pycache__", "Windows")]
            for f in files:
                if query_lower in f.lower() or f.lower().endswith(query_lower):
                    matches.append(os.path.join(root, f))
                    if len(matches) >= 10:
                        break
            if len(matches) >= 10:
                break
    except PermissionError:
        pass

    if matches:
        result = f"Found {len(matches)} file(s):\n" + "\n".join(matches)
        speak(f"Found {len(matches)} files matching {query}.")
        return result
    return f"No files found matching '{query}'."


# ============================================================
# SMART TYPING
# ============================================================

def smart_type(request: str, tone: str = "professional") -> str:
    import pyperclip
    import pyautogui

    try:
        from ai_router_v4 import ask_compose
        text = ask_compose(request, tone=tone).strip()
        pyperclip.copy(text)
        speak("Ready to paste.")
        time.sleep(1)
        pyautogui.hotkey("ctrl", "v")
        return f"Typed: {text[:80]}..."
    except Exception as e:
        return f"Smart type error: {e}"


# ============================================================
# MEMORY (SQLite-backed via memory_db)
# ============================================================

def save_memory(key: str, value: str) -> str:
    try:
        from memory_db import save_fact
        save_fact(key.strip(), value.strip())
        return f"Remembered: {key} = {value}."
    except Exception as e:
        return f"Memory error: {e}"


def recall_memory(key: str = "") -> str:
    try:
        from memory_db import get_fact, get_all_facts
        if key:
            value = get_fact(key)
            return f"{key}: {value}" if value else f"Nothing saved for '{key}'."
        else:
            facts = get_all_facts()
            if not facts:
                return "I have not learned anything specific about you yet."
            lines = ["Here is what I know about you:"]
            for k, v in facts.items():
                if isinstance(v, list):
                    lines.append(f"  {k.replace('_', ' ').title()}: {', '.join(v)}")
                else:
                    lines.append(f"  {k.replace('_', ' ').title()}: {v}")
            return "\n".join(lines)
    except Exception as e:
        return f"Memory recall error: {e}"


def forget_memory(key: str) -> str:
    try:
        from memory_db import delete_fact
        if delete_fact(key):
            return f"Forgot: {key}."
        return f"Nothing found to forget for '{key}'."
    except Exception as e:
        return f"Memory forget error: {e}"


def search_memory(query: str) -> str:
    """Fuzzy search across saved facts and conversation episode history."""
    try:
        from memory_db import search_facts, search_episodes
        fact_hits    = search_facts(query)
        episode_hits = search_episodes(query, limit=5)
        results = fact_hits + episode_hits
        if results:
            return "\n".join(results[:10])
        return f"Nothing found in memory for '{query}'."
    except Exception as e:
        return f"Memory search error: {e}"


# ============================================================
# EMAIL
# ============================================================

def send_email(to: str, subject: str, body: str) -> str:
    try:
        from gmail_plugin import handle
        cmd = f"send email to {to} subject {subject} body {body}"
        handled = handle(cmd)
        return f"Email sent to {to}." if handled else "Could not send email."
    except Exception as e:
        return f"Email error: {e}"


def read_emails(count: int = 5) -> str:
    try:
        from gmail_plugin import handle
        handled = handle(f"read {count} emails")
        return "Fetched emails." if handled else "Could not read emails."
    except Exception as e:
        return f"Email read error: {e}"


# ============================================================
# MODES — Direct logic (no plugin string parsing)
# ============================================================

_ACTIVE_MODE = {"current": "normal"}

def get_mode() -> str:
    """Read the currently active focus mode (normal/study/coding/movie)."""
    return _ACTIVE_MODE["current"]

def set_mode(mode: str, active: bool = True) -> str:
    import subprocess

    mode = mode.lower().strip()

    if not active or mode == "normal":
        _ACTIVE_MODE["current"] = "normal"
        speak("Normal mode. All focus modes deactivated.")
        return "Switched to normal mode."

    _ACTIVE_MODE["current"] = mode

    if mode == "study":
        speak("Study mode activated. I am ready to help with your studies.")
        try:
            subprocess.Popen("spotify.exe", shell=True)
        except Exception:
            pass
        return "Study mode activated."

    elif mode == "coding":
        speak("Coding mode activated. VS Code is opening.")
        try:
            subprocess.Popen(["code", "."], shell=True)
        except Exception:
            pass
        return "Coding mode activated."

    elif mode == "movie":
        import pyautogui
        speak("Movie mode. Dimming volume and going full screen.")
        pyautogui.press("f11")
        return "Movie mode activated."

    return f"Unknown mode: {mode}"


# ============================================================
# CODING
# ============================================================

def coding_assist(task: str, language: str = "python") -> str:
    try:
        from ai_router_v4 import ask_coding
        result = ask_coding(task, language=language)
        speak(result)  # speak the real answer — a placeholder ack alone left this silent
        return result
    except Exception as e:
        return f"Coding assist error: {e}"


# ============================================================
# STUDY
# ============================================================

def study_assist(task: str, subject: str = "") -> str:
    try:
        from ai_router_v4 import ask_tutor
        result = ask_tutor(task, subject=subject)
        speak(result)  # speak the real explanation — a placeholder ack alone left this silent
        return result
    except Exception as e:
        return f"Study assist error: {e}"


# ============================================================
# IoT — via iot_plugin (alexa-remote2 Node bridge)
# ============================================================

def iot_control(device: str, action: str) -> str:
    """
    `device` already includes any location/descriptor the LLM
    extracted (e.g. "bedroom ac"), and `action` is natural language
    (e.g. "turn on", "set brightness to 50"). iot_plugin's
    handle_structured() parses the action and runs _find_best_device
    against `device` directly — no need to combine them into one
    string, so word order doesn't matter. This is what enables
    fuzzy matching against real Alexa device names like
    "Master Bedroom AC".
    """
    try:
        from iot_plugin import handle_structured
        handled = handle_structured(device, action)
        return f"IoT: {action} {device}." if handled else f"Could not control {device}."
    except Exception as e:
        return f"IoT error: {e}"


# ============================================================
# RAG — Document ingestion and retrieval
# ============================================================

def ingest_document(file_path: str) -> str:
    """Read a file and store it in the RAG vector store."""
    try:
        from rag_store import ingest
    except ImportError:
        return "RAG store not available. Install sentence-transformers and numpy."

    file_path = os.path.expanduser(file_path)
    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        elif ext == ".pdf":
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            except ImportError:
                return "pdfplumber not installed. Run: pip install pdfplumber"
        elif ext in (".docx",):
            try:
                import docx
                doc = docx.Document(file_path)
                text = "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                return "python-docx not installed. Run: pip install python-docx"
        else:
            return f"Unsupported file type: {ext}. Supported: .txt, .pdf, .docx"

        if not text.strip():
            return "File appears to be empty or could not be parsed."

        ingest(file_path, text)
        name = os.path.basename(file_path)
        speak(f"Document ingested: {name}")
        return f"Ingested '{name}' into knowledge base."

    except Exception as e:
        return f"Ingest error: {e}"


def query_documents(query: str, top_k: int = 3) -> str:
    """Search the RAG vector store for relevant passages."""
    try:
        from rag_store import search
    except ImportError:
        return "RAG store not available. Install sentence-transformers and numpy."

    try:
        results = search(query, top_k=top_k)
        if results:
            return "\n---\n".join(results)
        return "No relevant passages found in your documents."
    except Exception as e:
        return f"Document query error: {e}"


# ============================================================
# MULTI-STEP PLANNING
# ============================================================

def plan_task(goal: str, steps: list) -> str:
    """
    Execute a list of sub-tasks in sequence by feeding each back
    through the brain's tool loop.
    """
    speak(f"Starting task: {goal}. {len(steps)} steps.")
    results = []

    for i, step in enumerate(steps, 1):
        print(f"[PLAN] Step {i}/{len(steps)}: {step}")
        try:
            # Import here to avoid circular import at module load
            from brain_v4 import run_tool_loop
            result = run_tool_loop(step)
            results.append(f"Step {i} ({step}): done")
        except Exception as e:
            results.append(f"Step {i} ({step}): error — {e}")

        time.sleep(0.5)  # brief pause between steps

    summary = f"Task '{goal}' complete. " + " | ".join(results)
    speak(f"All {len(steps)} steps done.")
    return summary


# ============================================================
# WORKFLOWS
# ============================================================

def create_workflow(name: str, steps: list) -> str:
    """Save a named workflow to memory."""
    try:
        from memory_db import save_workflow
        save_workflow(name.strip().lower(), steps)
        speak(f"Workflow {name} saved with {len(steps)} steps.")
        return f"Workflow '{name}' saved with {len(steps)} steps: {', '.join(steps)}"
    except Exception as e:
        return f"Workflow save error: {e}"


def run_workflow(name: str) -> str:
    """Load and execute a saved workflow."""
    try:
        from memory_db import get_workflow
        steps = get_workflow(name.strip().lower())
        if not steps:
            return f"No workflow named '{name}' found. Create one first."
        return plan_task(goal=name, steps=steps)
    except Exception as e:
        return f"Workflow run error: {e}"


# ============================================================
# SPEAK (fallback)
# ============================================================

def speak_response(text: str) -> str:
    print(f"FRIDAY: {text}")
    threading.Thread(target=speak, args=(text,), daemon=True).start()
    return text


# ============================================================
# DISPATCHER
# ============================================================

EXECUTOR_MAP = {
    "control_volume":   control_volume,
    "take_screenshot":  take_screenshot,
    "power_control":    power_control,
    "open_app":         open_app,
    "open_website":     open_website,
    "web_search":       web_search,
    "get_weather":      get_weather,
    "youtube_search":   youtube_search,
    "set_timer":        set_timer,
    "send_whatsapp":    send_whatsapp,
    "organise_files":   organise_files,
    "find_files":       find_files,
    "smart_type":       smart_type,
    "save_memory":      save_memory,
    "recall_memory":    recall_memory,
    "forget_memory":    forget_memory,
    "search_memory":    search_memory,
    "send_email":       send_email,
    "read_emails":      read_emails,
    "set_mode":         set_mode,
    "coding_assist":    coding_assist,
    "study_assist":     study_assist,
    "iot_control":      iot_control,
    "ingest_document":  ingest_document,
    "query_documents":  query_documents,
    "plan_task":        plan_task,
    "create_workflow":  create_workflow,
    "run_workflow":     run_workflow,
    "speak_response":   speak_response,
}

MAX_RESULT_CHARS = 800  # Truncate long tool results to protect token budget

# openai/gpt-oss models (used via Groq) have a documented training prior
# toward calling certain tool names from OpenAI's own internal agentic
# conventions, even when those names were never in the schema we sent —
# e.g. calling "live_search" when only "web_search" was offered. Rather
# than erroring out, redirect known aliases to the real implementation.
TOOL_ALIASES = {
    "live_search":     "web_search",
    "browser_search":  "web_search",
    "browser.search":  "web_search",
    "internet_search": "web_search",
    "search":          "web_search",
}


def execute_tool(tool_name: str, arguments: dict) -> str:
    """
    Execute a single tool call and return the result string.
    Long results are truncated to stay within Groq's context window.
    """
    fn = EXECUTOR_MAP.get(tool_name)

    if not fn:
        alias = TOOL_ALIASES.get(tool_name)
        if alias:
            print(f"[TOOL] '{tool_name}' isn't a defined tool — redirecting to '{alias}'")
            fn = EXECUTOR_MAP.get(alias)

    if not fn:
        return f"Unknown tool: {tool_name}"
    try:
        result = fn(**arguments)
    except TypeError as e:
        return f"Tool argument error for {tool_name}: {e}"
    except Exception as e:
        return f"Tool execution error for {tool_name}: {e}"

    # Truncate long results
    result = str(result)
    if len(result) > MAX_RESULT_CHARS:
        result = result[:MAX_RESULT_CHARS] + "…[truncated]"
    return result