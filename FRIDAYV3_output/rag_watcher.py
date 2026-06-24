"""
rag_watcher.py — FRIDAY Automated RAG Watcher

Monitors Downloads, Documents, and Desktop for new supported files.
When a new file appears, FRIDAY asks the user (by voice) whether to
learn it. If the user says yes, the file is ingested into the RAG
store automatically. If no, it is marked as skipped and never asked
about again.

Supported file types: .pdf, .txt, .docx

Flow:
  startup → start_rag_watcher() called from main.py
    → background thread polls WATCH_FOLDERS every RAG_SCAN_INTERVAL seconds
    → new file found → speak("Found X. Should I learn it?")
    → listen for 5 seconds for "yes" / "no"
    → yes → ingest_document(file_path) → speak confirmation
    → no  → mark skipped, never ask again

Coexists with the existing manual ingest_document / query_documents
voice tools — those are completely unchanged.
"""

import os
import time
import threading
from pathlib import Path

from voice import speak

# ── Folders to watch ──────────────────────────────────────────────────────────
WATCH_FOLDERS = [
    os.path.expanduser("D:/Downloads"),
    os.path.expanduser("D:/Documents"),
    os.path.expandvars("%USERPROFILE%/Desktop"),
]

# File types the RAG store can actually ingest
RAG_EXTENSIONS = {".pdf", ".txt", ".docx"}

# How often to scan (seconds)
RAG_SCAN_INTERVAL = 20

# Only consider files created/modified in the last N seconds
# (avoids asking about files that were already there before FRIDAY started)
MAX_FILE_AGE_SECONDS = 3 * 60 * 60   # 3 hours

# Memory key for tracking files we've already handled (asked + answered)
_RAG_MEMORY_KEY = "rag_watcher_seen"

# ── State ─────────────────────────────────────────────────────────────────────
_watcher_thread  = None
_watcher_active  = False

# In-memory set of files already asked about this session.
# On startup we also load the persisted "skipped" set from memory.
_session_seen: set = set()   # asked OR ingested this session
_skipped_set:  set = set()   # user said "no" — never ask again (persisted)

# Lock so the listen-for-response step blocks the scan loop (one ask at a time)
_ask_lock = threading.Lock()


# ── Persistent memory helpers ─────────────────────────────────────────────────

def _load_skipped() -> set:
    """Load the set of file paths the user has previously declined."""
    try:
        from memory import load_memory
        memory = load_memory()
        return set(memory.get(_RAG_MEMORY_KEY, {}).get("skipped", []))
    except Exception:
        return set()


def _save_skipped(skipped: set):
    """Persist the skipped set so we don't re-ask across restarts."""
    try:
        from memory import load_memory, save_memory
        memory = load_memory()
        if _RAG_MEMORY_KEY not in memory:
            memory[_RAG_MEMORY_KEY] = {}
        memory[_RAG_MEMORY_KEY]["skipped"] = list(skipped)[-500:]  # cap size
        save_memory(memory)
    except Exception as e:
        print(f"[RAG WATCHER] Could not save skipped list: {e}")


# ── Voice listener (short, non-blocking) ──────────────────────────────────────

def _listen_for_yes_no(timeout: int = 6) -> bool | None:
    """
    Listen for a short spoken response.
    Returns True  → heard "yes" / "yeah" / "sure" / "go ahead" / "learn it"
    Returns False → heard "no" / "nope" / "skip" / "dont" / "ignore"
    Returns None  → heard nothing or couldn't tell
    """
    try:
        import speech_recognition as sr
        import requests
        from config import GROQ_API_KEY, GROQ_WHISPER_MODEL
        import io

        r = sr.Recognizer()
        r.energy_threshold      = 960
        r.pause_threshold       = 1.2
        r.non_speaking_duration = 0.5

        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.3)
            try:
                audio = r.listen(source, timeout=timeout, phrase_time_limit=5)
            except sr.WaitTimeoutError:
                return None

        # Transcribe via Groq Whisper (same as main.py)
        wav_bytes = audio.get_wav_data()
        response  = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav")},
            data={"model": GROQ_WHISPER_MODEL, "language": "en"},
            timeout=10,
        )
        if response.status_code != 200:
            return None

        text = response.json().get("text", "").strip().lower()
        print(f"[RAG WATCHER] Heard: {text!r}")

        YES_WORDS = {"yes", "yeah", "yep", "sure", "go ahead", "learn it",
                     "learn", "add it", "do it", "please", "ok", "okay",
                     "sounds good", "go for it"}
        NO_WORDS  = {"no", "nope", "nah", "skip", "dont", "don't", "ignore",
                     "not now", "later", "stop", "cancel", "no thanks"}

        if any(w in text for w in YES_WORDS):
            return True
        if any(w in text for w in NO_WORDS):
            return False
        return None

    except Exception as e:
        print(f"[RAG WATCHER] Listen error: {e}")
        return None


# ── Core ingest call ──────────────────────────────────────────────────────────

def _ingest_file(file_path: str):
    """Call the existing tool_executor.ingest_document() function."""
    try:
        from tool_executor import ingest_document
        result = ingest_document(file_path)
        print(f"[RAG WATCHER] Ingest result: {result}")
        return result
    except Exception as e:
        print(f"[RAG WATCHER] Ingest error: {e}")
        return f"Error ingesting file: {e}"


# ── Ask + ingest (runs in the scan loop's thread, protected by _ask_lock) ─────

def _ask_and_maybe_ingest(file_path: str, file_name: str):
    """
    Speak the prompt, wait for a response, and ingest if the user says yes.
    Protected by _ask_lock so we never ask about two files simultaneously.
    """
    global _skipped_set

    with _ask_lock:
        speak(
            f"I found a new file called {file_name}. "
            f"Would you like me to learn it and add it to my knowledge base?"
        )

        answer = _listen_for_yes_no(timeout=7)

        if answer is True:
            speak(f"Learning {file_name} now.")
            result = _ingest_file(file_path)
            speak(f"Done. I have learned {file_name}. You can now ask me questions about it.")
            print(f"[RAG WATCHER] Ingested: {file_path}")

        elif answer is False:
            speak("Okay, I will skip that file.")
            _skipped_set.add(file_path)
            _save_skipped(_skipped_set)
            print(f"[RAG WATCHER] Skipped (user said no): {file_path}")

        else:
            # No response — don't ingest, but also don't permanently skip.
            # We'll ask again next scan if the file is still fresh.
            # To avoid repeating every 20s, add to session_seen but NOT skipped.
            print(f"[RAG WATCHER] No clear answer — will not ask again this session: {file_path}")
            # Already added to _session_seen by caller before this function runs.


# ── Scanner ───────────────────────────────────────────────────────────────────

def _scan_folders():
    """
    Scan all WATCH_FOLDERS for new RAG-eligible files.
    For each new file found, ask the user if they want it ingested.
    """
    now = time.time()

    for folder in WATCH_FOLDERS:
        folder_path = Path(folder)
        if not folder_path.exists():
            continue

        try:
            entries = list(folder_path.iterdir())
        except PermissionError:
            continue

        for f in entries:
            if not f.is_file():
                continue

            if f.suffix.lower() not in RAG_EXTENSIONS:
                continue

            file_path = str(f)

            # Skip if already handled this session
            if file_path in _session_seen:
                continue

            # Skip if user previously said no
            if file_path in _skipped_set:
                continue

            # Skip if already in the RAG store
            try:
                from rag_store import list_sources
                if file_path in list_sources():
                    _session_seen.add(file_path)
                    continue
            except Exception:
                pass

            # Skip files that are too old (existed long before FRIDAY started)
            try:
                file_age = now - f.stat().st_mtime
                if file_age > MAX_FILE_AGE_SECONDS:
                    _session_seen.add(file_path)  # silence it permanently this session
                    continue
            except Exception:
                continue

            # New file — mark session-seen now so the loop doesn't re-trigger
            # while we're still inside _ask_and_maybe_ingest
            _session_seen.add(file_path)

            print(f"[RAG WATCHER] New eligible file: {f.name}")
            _ask_and_maybe_ingest(file_path, f.name)


# ── Background loop ───────────────────────────────────────────────────────────

def _watcher_loop():
    global _watcher_active
    print("[RAG WATCHER] Background watcher started.")

    # Give FRIDAY a moment to finish startup speech before asking anything
    time.sleep(10)

    while _watcher_active:
        try:
            _scan_folders()
        except Exception as e:
            print(f"[RAG WATCHER] Loop error: {e}")

        time.sleep(RAG_SCAN_INTERVAL)

    print("[RAG WATCHER] Stopped.")


# ── Public API ────────────────────────────────────────────────────────────────

def start_rag_watcher():
    """
    Start the automated RAG watcher in a daemon background thread.
    Call this once from main.py alongside start_watcher() and start_gmail_monitor().
    """
    global _watcher_thread, _watcher_active, _skipped_set

    if _watcher_active:
        print("[RAG WATCHER] Already running.")
        return

    # Load persisted skipped list
    _skipped_set = _load_skipped()

    _watcher_active = True
    _watcher_thread = threading.Thread(target=_watcher_loop, daemon=True)
    _watcher_thread.start()
    print("[RAG WATCHER] Started — watching Downloads, Documents, Desktop.")


def stop_rag_watcher():
    """Stop the watcher."""
    global _watcher_active
    _watcher_active = False
    print("[RAG WATCHER] Stopped.")


def get_status() -> dict:
    """Return current watcher status (useful for debugging)."""
    try:
        from rag_store import chunk_count, list_sources
        sources = list_sources()
        chunks  = chunk_count()
    except Exception:
        sources, chunks = [], 0

    return {
        "active":        _watcher_active,
        "session_seen":  len(_session_seen),
        "skipped":       len(_skipped_set),
        "rag_sources":   len(sources),
        "rag_chunks":    chunks,
    }