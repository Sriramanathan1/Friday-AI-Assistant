import webbrowser
import subprocess
import threading

from voice import speak

# ================= 🧠 STUDY MODE STATE =================

STUDY_MODE_ACTIVE  = False
CODING_MODE_ACTIVE = False

_autocomplete_thread = None


def is_study_active():
    return STUDY_MODE_ACTIVE

def is_coding_active():
    return CODING_MODE_ACTIVE


# ================= 🎯 HANDLER =================

def handle(command):

    global STUDY_MODE_ACTIVE, CODING_MODE_ACTIVE, _autocomplete_thread

    command = command.lower().strip()

    # ================= 📚 STUDY MODE =================

    if any(x in command for x in [
        "study mode", "focus mode", "study session",
        "time to study", "enable studying", "learning mode"
    ]):
        STUDY_MODE_ACTIVE  = True
        CODING_MODE_ACTIVE = False
        speak("Study mode activated. I am ready to help with your Maths, Physics, and Chemistry. What do you need?")
        try:
            subprocess.Popen("spotify.exe")
        except:
            pass
        return True

    # ================= 📚 STUDY MODE OFF =================

    if any(x in command for x in [
        "exit study mode", "stop study mode",
        "disable study mode", "end study session", "leave study mode"
    ]):
        STUDY_MODE_ACTIVE = False
        speak("Study mode deactivated. Back to normal.")
        return True

    # ================= 💻 CODING MODE =================

    if any(x in command for x in [
        "coding mode", "programming mode", "developer mode",
        "start coding", "code mode"
    ]):
        STUDY_MODE_ACTIVE  = False
        CODING_MODE_ACTIVE = True

        speak("Coding mode activated. I have access to your VS Code. What do you need?")

        # Open VS Code
        try:
            subprocess.Popen(["code", "."], shell=True)
        except:
            try:
                # fallback: full path
                subprocess.Popen(
                    r"C:\Users\%USERNAME%\AppData\Local\Programs\Microsoft VS Code\Code.exe",
                    shell=True
                )
            except:
                speak("VS Code was not found")

        # Write active flag so the extension knows FRIDAY is in coding mode
        import os, tempfile
        flag = os.path.join(tempfile.gettempdir(), "friday_coding_active.flag")
        open(flag, "w").close()

        # Start autocomplete watcher in background (only one thread ever)
        if _autocomplete_thread is None or not _autocomplete_thread.is_alive():
            from coding_mode import start_autocomplete_watcher
            _autocomplete_thread = threading.Thread(
                target=start_autocomplete_watcher,
                daemon=True
            )
            _autocomplete_thread.start()

        return True

    # ================= 💻 CODING MODE OFF =================

    if any(x in command for x in [
        "exit coding mode", "stop coding mode", "disable coding mode"
    ]):
        CODING_MODE_ACTIVE = False

        import os, tempfile
        flag = os.path.join(tempfile.gettempdir(), "friday_coding_active.flag")
        if os.path.exists(flag):
            os.remove(flag)

        speak("Coding mode deactivated.")
        return True

    # ================= 🎬 MOVIE MODE =================

    if any(x in command for x in [
        "movie mode", "cinema mode", "watch mode", "entertainment mode"
    ]):
        STUDY_MODE_ACTIVE  = False
        CODING_MODE_ACTIVE = False
        speak("Activating movie mode")
        webbrowser.open("https://youtube.com")
        return True

    # ================= ✍️ WRITING MODE =================

    if any(x in command for x in [
        "writing mode", "author mode", "creative writing mode", "journal mode"
    ]):
        STUDY_MODE_ACTIVE  = False
        CODING_MODE_ACTIVE = False
        speak("Activating writing mode")
        try:
            subprocess.Popen("winword")
        except:
            speak("Microsoft Word was not found")
        return True

    return False