import speech_recognition as sr
import traceback
import pyautogui
import time
import threading
from dotenv import load_dotenv
load_dotenv()

from brain import process_command
from voice import speak
from study_planner import run_startup_interview
from download_watcher import start_watcher
# ================= ⚙️ CONFIG =================

# How long of silence (seconds) before FRIDAY goes back to sleep
SLEEP_AFTER_SILENCE = 30

def startup_tasks():
    time.sleep(2)
    speak("FRIDAY online.")
    start_watcher()        # ← add this
    run_startup_interview()

def listen():

    r           = sr.Recognizer()
    ACTIVE      = False
    TYPING_MODE = False
    last_active = None  # timestamp of last command

    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source)
        r.energy_threshold = 4000

    print("FRIDAY listening...")

    # ================= 🗓️ STARTUP INTERVIEW =================
    # Run study planner interview once per day on startup

    def startup_tasks():
        time.sleep(2)  # brief pause before speaking
        speak("FRIDAY online.")
        run_startup_interview()

    threading.Thread(target=startup_tasks, daemon=True).start()

    # ================= 🔁 MAIN LOOP =================

    while True:

        try:

            with sr.Microphone() as source:
                audio = r.listen(source, timeout=30)

            command = r.recognize_google(audio).lower()
            print("Heard:", command)

            # ================= 🎤 WAKE WORD =================

            if (
                "hey friday" in command
                or "a friday"  in command
                or "play friday" in command
                or "he friday"  in command
                or "day friday" in command
            ):
                ACTIVE      = True
                last_active = time.time()
                speak("Yes")
                continue

            # ================= 🛑 INTERRUPT =================
            # Always handled regardless of ACTIVE state

            if "stop" in command or "be quiet" in command:
                process_command(command)
                continue

            # ================= 🔴 SHUTDOWN — no wake word needed =================

            if "shutdown friday" in command:
                process_command(command)
                continue

            # ================= 📴 SLEEP CHECK =================
            # If ACTIVE and too much silence has passed, go back to sleep

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
                TYPING_MODE = True
                speak("Typing mode activated")
                last_active = time.time()
                continue

            # ================= ✍️ TYPING MODE STOP =================

            if "pause typing" in command:
                TYPING_MODE = False
                speak("Typing mode stopped")
                ACTIVE      = False
                last_active = None
                continue

            # ================= ✍️ TYPING MODE =================

            if TYPING_MODE:

                cmd = command.lower()
                last_active = time.time()

                if "stop typing" in cmd:
                    TYPING_MODE = False
                    ACTIVE      = False
                    last_active = None
                    speak("Typing mode stopped")

                elif "new line" in cmd:
                    pyautogui.press("enter")

                elif "delete" in cmd:
                    pyautogui.press("backspace")

                else:
                    pyautogui.write(command + " ", interval=0.01)

                continue

            # ================= 🧠 NORMAL COMMAND =================

            process_command(command)
            last_active = time.time()   # ✅ stay active after each command
            # ACTIVE stays True — no longer reset here

        except sr.WaitTimeoutError:

            # ── silence timeout — check if we should sleep ──
            if ACTIVE and last_active:
                silence = time.time() - last_active
                if silence > SLEEP_AFTER_SILENCE:
                    ACTIVE      = False
                    last_active = None
                    print(f"[MAIN] Silence timeout — sleeping.")
                    speak("Going to sleep. Say hey FRIDAY to wake me up.")

        except sr.UnknownValueError:
            pass

        except Exception as e:
            print("Error:", e)
            traceback.print_exc()


# ================= ⌨️ KEYBOARD INPUT OVERRIDE =================
# To use keyboard input instead of mic: keep text_input.py in this folder
# To switch back to voice: delete or rename text_input.py
try:
    from FRIDAYV3_output.text_input import patched_listen_loop
    listen = patched_listen_loop(listen)
except ImportError:
    pass
# ================= END OVERRIDE =================

listen()