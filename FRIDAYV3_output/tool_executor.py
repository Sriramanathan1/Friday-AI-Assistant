"""
tool_executor.py — FRIDAY Tool Executor (V4)  [FIXED]

Key fixes vs previous version:
  - live_search  → calls web.search_and_summarise() and speaks the result
  - study_assist → calls plugins/study_mode.handle() (full feature engine)
  - send_email   → calls gmail_plugin.compose_and_send() directly (not string hack)
  - read_emails  → calls gmail_plugin.read_latest() directly
  - set_mode     → starts autocomplete watcher for coding mode (was missing)
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


def live_search(query: str) -> str:
    """
    FIX: was missing from EXECUTOR_MAP entirely.
    Calls search_and_summarise() → Groq-spoken summary + links, then speaks it.
    """
    try:
        from plugins.web import search_and_summarise
        result = search_and_summarise(query)
        spoken = result.get("spoken", "")
        links  = result.get("links", [])

        if spoken:
            speak(spoken)

        # Build a text result Groq can see (it has already been spoken)
        link_lines = [f"  • {r['title']}: {r['url']}" for r in links if r.get("url")]
        full = spoken
        if link_lines:
            full += "\n\nTop links:\n" + "\n".join(link_lines)
        return full or f"No results found for '{query}'."

    except Exception as e:
        # Fallback to plain snippet
        try:
            from plugins.web import fetch_search_snippet
            snippet = fetch_search_snippet(query)
            if snippet:
                speak(snippet)
                return snippet
        except Exception:
            pass
        return f"Search error: {e}"


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
# MESSAGING — Direct pywhatkit
# ============================================================

CONTACTS = {
    "dad": "+919880393384",
    "mom": "",
    "me":  "",
}

def send_whatsapp(contact: str, message: str) -> str:
    import pyautogui

    name  = contact.strip().lower()
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
# FILES
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
    folder = os.path.expanduser(folder)
    query_lower = query.lower()
    matches = []

    try:
        for root, dirs, files in os.walk(folder):
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
# EMAIL — FIX: call gmail_plugin functions directly, not via string hack
# ============================================================

def send_email(to: str, subject: str, body: str) -> str:
    """
    FIX: previously called gmail_plugin.handle() with a constructed string
    which was fragile. Now calls compose_and_send() directly with proper args.
    """
    try:
        from gmail_plugin import compose_and_send
        # compose_and_send resolves 'to' as a contact name key first,
        # then falls back to treating it as a raw email address.
        ok = compose_and_send(
            recipient_name=to,
            subject_hint=subject,
            body_hint=body,
        )
        if ok:
            return f"Email sent to {to}."
        return f"Could not send email to {to}. Check that the address is in EMAIL_CONTACTS."
    except Exception as e:
        return f"Email error: {e}"


def read_emails(count: int = 5) -> str:
    """
    FIX: previously called handle() with a constructed string.
    Now reads directly from the Gmail API and returns a summary.
    """
    try:
        from gmail_plugin import get_gmail_service
        service = get_gmail_service()
        result  = service.users().messages().list(
            userId="me",
            labelIds=["INBOX", "UNREAD"],
            maxResults=count,
        ).execute()
        messages = result.get("messages", [])
        if not messages:
            return "No unread emails."

        summaries = []
        for msg in messages[:count]:
            m = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
            headers = {h["name"]: h["value"] for h in m["payload"]["headers"]}
            snippet = m.get("snippet", "")[:100]
            summaries.append(
                f"From: {headers.get('From','?')} | "
                f"Subject: {headers.get('Subject','(no subject)')} | "
                f"Preview: {snippet}"
            )

        text = f"You have {len(messages)} unread email(s):\n" + "\n".join(summaries)
        speak(f"You have {len(messages)} unread emails.")
        return text

    except Exception as e:
        return f"Email read error: {e}"


# ============================================================
# MODES — FIX: set_mode now starts autocomplete watcher for coding mode
# ============================================================

_ACTIVE_MODE = {"current": "normal"}

def get_mode() -> str:
    return _ACTIVE_MODE["current"]

def set_mode(mode: str, active: bool = True) -> str:
    import subprocess

    mode = mode.lower().strip()

    if not active or mode == "normal":
        _ACTIVE_MODE["current"] = "normal"
        # Clear coding mode flag file
        import tempfile
        flag = os.path.join(tempfile.gettempdir(), "friday_coding_active.flag")
        if os.path.exists(flag):
            os.remove(flag)
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

        # FIX: write the flag file so the VS Code extension knows FRIDAY is active
        import tempfile
        flag = os.path.join(tempfile.gettempdir(), "friday_coding_active.flag")
        open(flag, "w").close()

        # FIX: start the autocomplete watcher (was only done in plugins/modes.py
        # which is never called from brain_v4)
        _start_autocomplete_watcher()
        return "Coding mode activated."

    elif mode == "movie":
        import pyautogui
        speak("Movie mode. Dimming volume and going full screen.")
        pyautogui.press("f11")
        return "Movie mode activated."

    return f"Unknown mode: {mode}"


_autocomplete_thread = None

def _start_autocomplete_watcher():
    """Start coding-mode autocomplete watcher — only one thread ever."""
    global _autocomplete_thread
    if _autocomplete_thread is not None and _autocomplete_thread.is_alive():
        return
    try:
        from coding_mode import start_autocomplete_watcher
        _autocomplete_thread = threading.Thread(
            target=start_autocomplete_watcher,
            daemon=True,
        )
        _autocomplete_thread.start()
        print("[TOOL] Autocomplete watcher started.")
    except Exception as e:
        print(f"[TOOL] Could not start autocomplete watcher: {e}")


# ============================================================
# CODING — fallback (used when NOT in coding mode gate)
# ============================================================

def coding_assist(task: str, language: str = "python") -> str:
    try:
        from ai_router_v4 import ask_coding
        result = ask_coding(task, language=language)
        speak(result)
        return result
    except Exception as e:
        return f"Coding assist error: {e}"


# ============================================================
# STUDY — FIX: routes to study_mode.handle() (full feature engine)
# instead of just calling ask_tutor() for a plain text answer
# ============================================================

def study_assist(task: str, subject: str = "") -> str:
    """
    FIX: previously called ai_router_v4.ask_tutor() which returned plain text
    and had none of the quiz/solve/explain/simulate/graph features.

    Now routes to plugins/study_mode.handle() which is the full study engine.
    Falls back to ask_tutor() only if study_mode is unavailable.
    """
    try:
        from plugins.study_mode import handle as study_handle
        # Reconstruct a natural command from task + subject so the study
        # engine's NLP router can classify it correctly
        cmd = task
        if subject and subject.lower() not in task.lower():
            cmd = f"{task} {subject}".strip()
        print(f"[STUDY ASSIST] Routing to study_mode.handle(): {cmd!r}")
        acted = study_handle(cmd)
        if acted:
            return f"Study mode handled: {task}"
        # study_mode.handle() returned False — fall through to tutor
    except Exception as e:
        print(f"[STUDY ASSIST] study_mode unavailable, using tutor fallback: {e}")

    # Fallback: plain tutor answer
    try:
        from ai_router_v4 import ask_tutor
        result = ask_tutor(task, subject=subject)
        speak(result)
        return result
    except Exception as e:
        return f"Study assist error: {e}"


# ============================================================
# IoT
# ============================================================

def iot_control(device: str, action: str) -> str:
    try:
        from iot_plugin import handle_structured
        handled = handle_structured(device, action)
        return f"IoT: {action} {device}." if handled else f"Could not control {device}."
    except Exception as e:
        return f"IoT error: {e}"


# ============================================================
# RAG
# ============================================================

def ingest_document(file_path: str) -> str:
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
    speak(f"Starting task: {goal}. {len(steps)} steps.")
    results = []

    for i, step in enumerate(steps, 1):
        print(f"[PLAN] Step {i}/{len(steps)}: {step}")
        try:
            from brain_v4 import run_tool_loop
            result = run_tool_loop(step)
            results.append(f"Step {i} ({step}): done")
        except Exception as e:
            results.append(f"Step {i} ({step}): error — {e}")

        time.sleep(0.5)

    summary = f"Task '{goal}' complete. " + " | ".join(results)
    speak(f"All {len(steps)} steps done.")
    return summary


# ============================================================
# WORKFLOWS
# ============================================================

def create_workflow(name: str, steps: list) -> str:
    try:
        from memory_db import save_workflow
        save_workflow(name.strip().lower(), steps)
        speak(f"Workflow {name} saved with {len(steps)} steps.")
        return f"Workflow '{name}' saved with {len(steps)} steps: {', '.join(steps)}"
    except Exception as e:
        return f"Workflow save error: {e}"


def run_workflow(name: str) -> str:
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
    "live_search":      live_search,      # FIX: was missing entirely
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

MAX_RESULT_CHARS = 800

# Redirect known LLM hallucinated tool aliases to real implementations
TOOL_ALIASES = {
    "live_search":     "live_search",    # self (in case Groq uses old alias)
    "browser_search":  "live_search",
    "browser.search":  "live_search",
    "internet_search": "live_search",
    "search":          "live_search",
}


def execute_tool(tool_name: str, arguments: dict) -> str:
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

    result = str(result)
    if len(result) > MAX_RESULT_CHARS:
        result = result[:MAX_RESULT_CHARS] + "…[truncated]"
    return result
