"""
brain_v4.py — FRIDAY Brain (V4)

WHAT CHANGED FROM PREVIOUS brain_v4.py:
  ✓ Agentic tool loop — up to 5 Groq rounds per command (supports multi-tool chaining)
  ✓ DB-backed conversation history — survives restarts (via memory_db.log_episode)
  ✓ Session summary injected into system prompt on startup
  ✓ search_memory / plan_task / workflow tools wired in via new tools.py
  ✓ No more in-process conversation_history list (replaced by SQLite episodes)
  ✓ Study mode gate — mirrors coding mode gate (routes to study_mode.handle())
"""

import os
import json
import time
import datetime
import threading
import requests

import pygame
import pyautogui

from voice import speak
from config import GROQ_API_KEY, GROQ_MODEL
from tools import TOOLS
from tool_executor import execute_tool

pygame.mixer.init()
pyautogui.FAILSAFE = True

GROQ_URL    = "https://api.groq.com/openai/v1/chat/completions"
MAX_ROUNDS  = 5          # max Groq tool-call rounds per command
MAX_HISTORY = 10         # conversation turns to include from DB

NEEDS_SYNTHESIS_TOOLS = {
    "search_memory",
    "query_documents",
    "web_search",
    "live_search",     # search_and_summarise result — needs natural phrasing
    "get_weather",
    "recall_memory",
    "find_files",
}

SELF_SPEAKING_TOOLS = {
    "coding_assist", "control_volume", "create_workflow",
    "ingest_document", "open_app", "open_website", "organise_files",
    "plan_task", "power_control", "send_whatsapp", "set_mode", "set_timer",
    "smart_type", "speak_response", "study_assist", "take_screenshot",
    "youtube_search",
}


# ================= LIVE CONTEXT =================

def get_live_context() -> str:
    now      = datetime.datetime.now()
    date_str = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%H:%M")
    try:
        tz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzname() or "local time"
    except Exception:
        tz = "local time"
    return f"[{date_str} | {time_str} {tz}]"


def get_location() -> str:
    """Quick IP-based location lookup."""
    try:
        resp = requests.get("http://ip-api.com/json/", timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            parts = [p for p in [data.get("city"), data.get("regionName"), data.get("country")] if p]
            return ", ".join(parts)
    except Exception:
        pass
    return "your location"


# ================= SYSTEM PROMPT =================

def build_system_prompt() -> str:
    try:
        from memory_db import get_fact, get_all_facts, get_session_summary_text
        user_name = get_fact("name") or "there"
        facts     = get_all_facts()
        session   = get_session_summary_text(n=20)
    except Exception:
        user_name = "there"
        facts     = {}
        session   = ""

    live_context = get_live_context()

    if facts:
        fact_parts = []
        for k, v in list(facts.items())[:12]:
            if isinstance(v, list):
                fact_parts.append(f"{k}={', '.join(str(x) for x in v)}")
            else:
                fact_parts.append(f"{k}={v}")
        facts_line = "[User facts: " + " | ".join(fact_parts) + "]"
    else:
        facts_line = ""

    parts = [
        "You are FRIDAY, a calm and intelligent AI assistant running on the user's computer.",
        f"Current time and date: {live_context}",
        f"User name: {user_name}",
    ]
    if facts_line:
        parts.append(facts_line)
    if session:
        parts.append(session)

    parts += [
        "Rules:",
        "- Always use a tool when one fits — never describe what you would do, just do it.",
        "- For multi-step goals (e.g. 'set up my study session'), use plan_task.",
        "- For greetings, questions, jokes or anything that is just a spoken reply, use speak_response.",
        "- For memory-related commands (remember, forget, recall, 'do you remember'), use the memory tools.",
        "- For questions about the user's files or notes, try query_documents first.",
        "- For smart home / device commands, use iot_control and include any location or",
        "  descriptor words the user said (e.g. 'bedroom', 'master', 'living room') in `device`.",
        "- For real-time web searches needing a spoken answer, use live_search.",
        "- Be concise and natural. Sound futuristic, not robotic.",
        "- Never use apostrophes in spoken text (say 'do not' not 'don't').",
        "- Reference user facts naturally when they are relevant.",
    ]

    return "\n".join(parts)


# ================= GROQ CALLERS =================

def call_groq_with_tools(messages: list) -> dict:
    """One round-trip to Groq with tools enabled. Returns the raw message dict."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in .env")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    body = {
        "model":       GROQ_MODEL,
        "messages":    messages,
        "tools":       TOOLS,
        "tool_choice": "auto",
        "max_tokens":  1024,
        "temperature": 0.5,
    }
    resp = requests.post(GROQ_URL, headers=headers, json=body, timeout=20)
    if not resp.ok:
        try:
            detail = resp.json().get("error", resp.json())
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"Groq API error {resp.status_code}: {detail}")
    return resp.json()["choices"][0]["message"]


def call_groq_plain(messages: list) -> str:
    """Plain text follow-up after tool results (no tools offered)."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    body = {
        "model":       GROQ_MODEL,
        "messages":    messages,
        "max_tokens":  512,
        "temperature": 0.6,
    }
    resp = requests.post(GROQ_URL, headers=headers, json=body, timeout=20)
    if not resp.ok:
        try:
            detail = resp.json().get("error", resp.json())
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"Groq API error {resp.status_code}: {detail}")
    return resp.json()["choices"][0]["message"]["content"].strip()


# ================= AGENTIC TOOL LOOP =================

def run_tool_loop(user_command: str) -> str:
    """
    Full agentic tool-calling loop (up to MAX_ROUNDS):
      1. Build messages from DB history + system prompt
      2. Send to Groq with tools
      3. Execute any tool_calls returned
      4. Feed results back — repeat until no more tool_calls
      5. Get final natural-language reply
      6. Persist to DB and return
    """
    system_prompt = build_system_prompt()

    try:
        from memory_db import get_recent_episodes
        recent = get_recent_episodes(n=MAX_HISTORY)
    except Exception:
        recent = []

    messages = [{"role": "system", "content": system_prompt}]
    messages += recent
    messages.append({"role": "user", "content": user_command})

    reply = ""
    already_spoken = False

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"[BRAIN] Groq round {round_num}")

        try:
            assistant_msg = call_groq_with_tools(messages)
        except Exception as e:
            err = f"Could not reach Groq: {e}"
            speak(err)
            return err

        tool_calls = assistant_msg.get("tool_calls") or []

        if not tool_calls:
            reply = (assistant_msg.get("content") or "").strip()
            break

        messages.append(assistant_msg)

        round_results   = []
        needs_synthesis = False

        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            try:
                arguments = json.loads(tc["function"].get("arguments", "{}"))
            except (json.JSONDecodeError, KeyError):
                arguments = {}

            print(f"[TOOL CALL] {tool_name}({arguments})")
            result = execute_tool(tool_name, arguments)
            print(f"[TOOL RESULT] {result[:120]}")

            messages.append({
                "role":         "tool",
                "tool_call_id": tc["id"],
                "content":      result,
            })

            round_results.append(result)
            if tool_name in NEEDS_SYNTHESIS_TOOLS:
                needs_synthesis = True

        if not needs_synthesis:
            reply = " ".join(r for r in round_results if r).strip()
            fired_tools = {tc["function"]["name"] for tc in tool_calls}
            already_spoken = fired_tools.issubset(SELF_SPEAKING_TOOLS)
            break

    else:
        try:
            reply = call_groq_plain(messages).strip()
        except Exception:
            reply = "Done."

    if reply:
        if already_spoken:
            print(f"FRIDAY: {reply}")
        else:
            _speak_reply(reply)
        try:
            from memory_db import log_episode
            log_episode("assistant", reply)
        except Exception:
            pass

    return reply


def _speak_reply(text: str):
    """Speak the reply in a background thread (voice.speak() does the print)."""
    threading.Thread(target=speak, args=(text,), daemon=True).start()


# ================= CODING MODE GATE =================

CODING_ENTER_TRIGGERS = [
    "activate coding mode", "enable coding mode",
    "start coding mode", "turn on coding mode", "switch to coding mode",
]
CODING_EXIT_TRIGGERS = [
    "exit coding mode", "deactivate coding mode", "stop coding mode",
    "turn off coding mode", "leave coding mode",
]


def _handle_coding_mode_gate(command: str) -> bool:
    """
    Returns True if this command was fully handled here (skip the normal Groq
    tool loop). Returns False to fall through to run_tool_loop() as usual.
    """
    try:
        from tool_executor import get_mode, set_mode
    except Exception as e:
        print(f"[GATE] could not import get_mode/set_mode from tool_executor: {e}")
        return False

    if any(t in command for t in CODING_ENTER_TRIGGERS):
        print(f"[GATE] matched ENTER coding trigger in: {command!r}")
        set_mode("coding")
        return True

    current_mode = get_mode()

    if current_mode != "coding":
        return False

    if any(t in command for t in CODING_EXIT_TRIGGERS):
        print(f"[GATE] matched EXIT coding trigger in: {command!r}")
        set_mode("normal")
        return True

    try:
        from coding_mode import handle as coding_handle
    except Exception as e:
        print(f"[GATE] coding_mode import failed, falling back to Groq: {e}")
        return False

    acted = coding_handle(command)
    if not acted:
        print(f"[GATE] Ignored (coding mode active, not a coding command): {command!r}")

    return True


# ================= STUDY MODE GATE =================

STUDY_ENTER_TRIGGERS = [
    "activate study mode", "enable study mode", "start study mode",
    "study mode", "focus mode", "study session", "time to study",
    "enable studying", "learning mode",
]
STUDY_EXIT_TRIGGERS = [
    "exit study mode", "stop study mode", "deactivate study mode",
    "disable study mode", "end study session", "leave study mode",
    "normal mode",
]


def _handle_study_mode_gate(command: str) -> bool:
    """
    Returns True if this command was fully handled by the study mode gate.
    Returns False to fall through to run_tool_loop() as usual.
    """
    try:
        from tool_executor import get_mode, set_mode
    except Exception as e:
        print(f"[STUDY GATE] could not import get_mode/set_mode: {e}")
        return False

    # Entering study mode — handle locally (no Groq needed)
    if any(t in command for t in STUDY_ENTER_TRIGGERS):
        current_mode = get_mode()
        if current_mode != "study":
            print(f"[STUDY GATE] ENTER trigger matched: {command!r}")
            set_mode("study")
        return True

    current_mode = get_mode()

    if current_mode != "study":
        return False

    # -- From here on, study mode IS active --

    if any(t in command for t in STUDY_EXIT_TRIGGERS):
        print(f"[STUDY GATE] EXIT trigger matched: {command!r}")
        set_mode("normal")
        return True

    # Route all study commands through study_mode.handle()
    try:
        from plugins.study_mode import handle as study_handle
    except Exception as e:
        print(f"[STUDY GATE] study_mode import failed, falling back to Groq: {e}")
        return False

    print(f"[STUDY GATE] Routing to study_mode.handle(): {command!r}")
    acted = study_handle(command)
    if not acted:
        # study_mode.handle() returned False (shouldn't happen since it defaults
        # to explain), but if it does, fall back to normal Groq tool loop
        print(f"[STUDY GATE] study_mode.handle() returned False, falling back to Groq")
        return False

    return True


# ================= MAIN PROCESSOR =================

def process_command(command: str, smart_type: bool = False):
    command = command.lower().strip()

    # -- Interrupt / silence --
    if "stop" in command or "be quiet" in command:
        pygame.mixer.music.stop()
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
        print("FRIDAY: Stopped.")
        return

    # -- Shutdown FRIDAY itself --
    if "shutdown friday" in command:
        speak("Shutting down.")
        os._exit(0)

    # -- Passive memory extraction --
    try:
        from smart_memory import extract_and_save_facts
        extract_and_save_facts(command)
    except Exception:
        pass

    # -- Log user turn to DB --
    try:
        from memory_db import log_episode, log_usage
        log_episode("user", command)
        log_usage(command)
    except Exception:
        pass

    # -- Study mode gate (check before coding mode) --
    if _handle_study_mode_gate(command):
        return

    # -- Coding mode gate --
    if _handle_coding_mode_gate(command):
        return

    # -- Run the agentic tool loop --
    run_tool_loop(command)
