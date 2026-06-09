import os
import pyautogui

from voice import speak


def handle(command):

    command = command.lower().strip()

    # ================= 🔊 VOLUME =================

    if any(x in command for x in [
        "volume up",
        "increase volume",
        "turn volume up",
        "raise volume"
    ]):

        pyautogui.press(
            "volumeup",
            presses=5
        )

        speak("Volume increased")

        return True

    elif any(x in command for x in [
        "volume down",
        "decrease volume",
        "lower volume",
        "turn volume down"
    ]):

        pyautogui.press(
            "volumedown",
            presses=5
        )

        speak("Volume decreased")

        return True

    elif any(x in command for x in [
        "mute",
        "mute volume",
        "silence computer"
    ]):

        pyautogui.press(
            "volumemute"
        )

        speak("Volume muted")

        return True

    # ================= 💻 POWER =================

    elif any(x in command for x in [
        "shutdown pc",
        "turn off computer",
        "shutdown computer"
    ]):

        speak("Shutting down computer")

        os.system(
            "shutdown /s /t 1"
        )

        return True

    elif any(x in command for x in [
        "restart pc",
        "restart computer",
        "reboot system"
    ]):

        speak("Restarting computer")

        os.system(
            "shutdown /r /t 1"
        )

        return True

    # ================= 📸 SCREENSHOT =================

    elif any(x in command for x in [
        "take screenshot",
        "capture screen",
        "screenshot"
    ]):

        screenshot = pyautogui.screenshot()

        screenshot.save(
            "screenshot.png"
        )

        speak("Screenshot saved")

        return True

    return False