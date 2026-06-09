import os

def handle(command):
    command = command.lower()

    if "chrome" in command or "browser" in command:
        os.system("start chrome")
        return True

    elif "calculator" in command:
        os.system("calc")
        return True

    elif "notepad" in command:
        os.system("notepad")
        return True
    
    return False