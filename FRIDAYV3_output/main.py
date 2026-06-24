import speech_recognition as sr
import traceback
import pyautogui
import time
import threading
import io
import numpy as np
from dotenv import load_dotenv
load_dotenv()

import requests
from config import GROQ_API_KEY, GROQ_WHISPER_MODEL

from brain_v4 import process_command
from voice import speak

import text_input
from study_planner import run_startup_interview
from download_watcher import start_watcher
from gmail_plugin import start_monitor as start_gmail_monitor
from task_queue import start_proactive_loop

# ── One-time migration from old memory.json (V3 -> V4 SQLite) ──
try:
    import os as _os
    from memory_db import migrate_from_json, get_all_facts as _get_all_facts
    # memory.json lives at the project root, one level above this file's
    # directory (FRIDAYV3_output/).
    _old_memory = _os.path.join(_os.path.dirname(__file__), "..", "memory.json")
    if not _get_all_facts():  # only migrate if SQLite facts table is empty
        _migrated = migrate_from_json(_old_memory)
        if _migrated:
            print(f"[MEMORY] Migrated {_migrated} facts from memory.json -> SQLite.")
except Exception as _e:
    print(f"[MEMORY] Migration skipped: {_e}")

# ── Start proactive background checks (e.g. unread email alerts) ──
try:
    start_proactive_loop()
except Exception as _e:
    print(f"[TASK QUEUE] Could not start proactive loop: {_e}")

# ================= ⚙️ CONFIG =================

SLEEP_AFTER_SILENCE = 30
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


# ================= 🎙️ GROQ WHISPER TRANSCRIBE =================

def transcribe(audio: sr.AudioData) -> str:
    """Send audio to Groq Whisper API — fast, accurate, no local GPU needed."""
    try:
        wav_bytes = audio.get_wav_data()

        response = requests.post(
            GROQ_STT_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav")},
            data={
                "model":    GROQ_WHISPER_MODEL,
                "language": "en",
            },
            timeout=15,
        )

        if response.status_code == 200:
            text = response.json().get("text", "").strip().lower()
            return text
        else:
            print(f"[STT] Groq error {response.status_code}: {response.text}")
            return ""

    except Exception as e:
        print(f"[STT] Transcription error: {e}")
        return ""


# ================= 🚀 STARTUP =================

def startup_tasks():
    time.sleep(2)
    speak("FRIDAY online.")
    start_watcher()
    start_gmail_monitor()
    run_startup_interview()


# ================= 👂 LISTEN LOOP =================

def listen():

    r           = sr.Recognizer()
    ACTIVE      = False
    last_active = None

    # ── Mic calibration ──
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=1)
        r.energy_threshold      = 960   # low — Groq Whisper handles noise
        r.pause_threshold       = 2.0   # wait 2.0s silence before cutting off
        r.phrase_threshold      = 0.1
        r.non_speaking_duration = 0.8

    print("FRIDAY listening...")

    threading.Thread(target=startup_tasks, daemon=True).start()
    text_input.start()

    # ================= 🔁 MAIN LOOP =================

    while True:

        try:

            with sr.Microphone() as source:
                audio = r.listen(source, timeout=30, phrase_time_limit=10)

            command = transcribe(audio)
            if not command:
                continue

            print("Heard:", command)

            # ================= 🎤 WAKE WORD =================

            if (
                "hey friday" in command
                or "a friday"    in command
                or "play friday" in command
                or "he friday"   in command
                or "day friday"  in command
            ):
                ACTIVE      = True
                last_active = time.time()
                speak("Yes")
                continue

            # ================= 🛑 INTERRUPT =================

            if "stop" in command or "be quiet" in command:
                process_command(command)
                continue

            # ================= 🔴 SHUTDOWN =================

            if "shutdown friday" in command:
                process_command(command)
                continue

            # ================= 📴 SLEEP CHECK =================

            if ACTIVE and last_active:
                silence = time.time() - last_active
                if silence > SLEEP_AFTER_SILENCE:
                    ACTIVE = False
                    print(f"[MAIN] {int(silence)}s of silence — going back to sleep.")
                    speak("Going to sleep. Say hey FRIDAY to wake me up.")

            # ================= 📴 IGNORE IF NOT ACTIVE =================

            if not ACTIVE:
                continue

            # ================= 🧠 SMART TYPE MODE =================

            if command.startswith("type "):
                process_command(command, smart_type=True)
                last_active = time.time()
                continue

            # ================= ✍️ TYPING MODE START =================

            if "start typing" in command:
                typing_mode.start()
                speak("Typing mode activated")
                last_active = time.time()
                continue

            # ================= ✍️ TYPING MODE =================

            if typing_mode.handle(command):
                last_active = time.time()
                if not typing_mode.active:
                    speak("Typing mode stopped")
                    ACTIVE      = False
                    last_active = None
                continue

            # ================= 🧠 NORMAL COMMAND =================

            process_command(command)
            last_active = time.time()

        except sr.WaitTimeoutError:

            if ACTIVE and last_active:
                silence = time.time() - last_active
                if silence > SLEEP_AFTER_SILENCE:
                    ACTIVE      = False
                    last_active = None
                    print("[MAIN] Silence timeout — sleeping.")
                    speak("Going to sleep. Say hey FRIDAY to wake me up.")

        except sr.UnknownValueError:
            pass

        except Exception as e:
            print("Error:", e)
            traceback.print_exc()


# ================= ⌨️ KEYBOARD INPUT OVERRIDE =================
try:
    from FRIDAYV3_output.text_input import patched_listen_loop
    listen = patched_listen_loop(listen)
except ImportError:
    pass
# ================= END OVERRIDE =================

listen()