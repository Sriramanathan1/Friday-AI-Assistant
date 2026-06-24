"""
text_input.py — Type your prompts to FRIDAY
==============================================
Lets you type commands straight into the terminal instead of speaking
them. Runs alongside the voice loop in a background thread, so both
input methods work at the same time — whichever's more convenient.

Whatever you type goes through the exact same pipeline as a spoken
command (brain_v4.process_command()), so all the same tools, coding
mode, etc. all just work.
"""

import threading

from brain_v4 import process_command


def _loop():
    print("[TEXT INPUT] Type a command and press Enter. (Ctrl+C to stop)")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not text:
            continue

        process_command(text)


def start():
    """Start the text-input loop in a background thread."""
    threading.Thread(target=_loop, daemon=True).start()