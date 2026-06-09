import pyautogui
from voice import speak
def handle(command):

    command = command.lower()

    if "next tab" in command:
        pyautogui.hotkey("ctrl", "tab")
        return True

    elif "previous tab" in command:
        pyautogui.hotkey("ctrl", "shift", "tab")
        return True

    elif "close tab" in command:
        pyautogui.hotkey("ctrl", "w")
        return True

    elif "refresh page" in command:
        pyautogui.press("f5")
        return True

    return False