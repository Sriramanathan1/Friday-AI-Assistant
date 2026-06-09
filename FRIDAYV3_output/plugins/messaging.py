import pywhatkit
import pyautogui
import time

from voice import speak

# ================= 📱 CONTACTS =================

CONTACTS = {

    "dad": "+919880393384",

    "mom": "",

    "me": "",

    "that": "+919880393384"
}

# ================= 🧠 MESSAGE PREFIXES =================

MESSAGE_PREFIXES = [

    "send whatsapp message to",
    "send a message to",
    "send message to",
    "whatsapp",
    "message",
    "tell",
    "text",
]

# ================= 🧹 CLEAN NAME =================

def clean_name(name):
    """Strip filler words STT adds around contact names."""

    name = name.strip()

    for filler in ["my ", "to ", "the "]:
        if name.startswith(filler):
            name = name[len(filler):].strip()

    return name

# ================= 📩 HANDLER =================

def handle(command):

    command = command.lower().strip()

    print("[MESSAGING] Raw command:", command)

    # ================= 🧠 PREFIX DETECTION =================

    matched_prefix = None

    for prefix in MESSAGE_PREFIXES:

        if command.startswith(prefix):
            matched_prefix = prefix
            break

    if not matched_prefix:
        return False

    # ================= 🧠 REMOVE PREFIX =================

    content = command[len(matched_prefix):].strip()

    # strip leading "my" — STT often adds it
    if content.startswith("my "):
        content = content[3:].strip()

    print("[MESSAGING] Content after prefix removal:", content)

    # ================= 🧠 SEPARATOR PARSER =================

    separators = [
        "saying that",
        "saying",
        "that says",
        "with message",
        "the message",
        "message",
        "says",
        "that",
    ]

    name = None
    msg  = None

    for sep in separators:

        if sep in content:

            parts = content.split(sep, 1)
            name  = clean_name(parts[0])
            msg   = parts[1].strip()
            print(f"[MESSAGING] Separator '{sep}' matched -> name='{name}', msg='{msg}'")
            break

    # ================= 🧠 FALLBACK PARSER =================

    if not name or not msg:

        parts = content.split(" ", 1)

        if len(parts) < 2:
            speak("Message content missing")
            return True

        name = clean_name(parts[0])
        msg  = parts[1].strip()
        print(f"[MESSAGING] Fallback parser -> name='{name}', msg='{msg}'")

    # ================= 📱 CONTACT CHECK =================

    if name not in CONTACTS:
        speak("Contact not found. I do not have " + name + " in my contacts.")
        return True

    phone = CONTACTS[name]

    if not phone:
        speak("No phone number saved for " + name + ".")
        return True

    print("[MESSAGING] Sending to:", phone, "| Message:", msg)

    # ================= 📩 SEND =================

    try:

        pywhatkit.sendwhatmsg_instantly(
            phone,
            msg,
            wait_time=15,
            tab_close=False
        )

        time.sleep(5)
        pyautogui.press("enter")

        print("[MESSAGING] Message sent")
        speak("Message sent to " + name + ".")

        return True

    except Exception as e:

        print("[MESSAGING] Error:", e)
        speak("Message failed. Please try again.")
        return False