# ================= IMPORTS =================

import requests
import subprocess
import sounddevice as sd
import numpy as np
import os
import pygame
import threading
import pyautogui
import pyperclip
import time
import re
import datetime

from geopy.geocoders import Nominatim          # pip install geopy
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from nlp_router import classify as nlp_classify

from memory import remember, recall, log_usage, recall_preference
from learning import is_learning_command, check_shortcut, handle, last_command
from homework_tracker import is_homework_command, handle as hw_handle
from download_watcher import is_watcher_command, handle as watcher_handle, start_watcher
from notes_summarizer import handle as notes_handle, is_notes_command
from podcast_generator import handle as podcast_handle, is_podcast_command
from coding_mode import handle as coding_handle, is_coding_command
from plugins.modes import is_coding_active   # already in modes.py

# ── NEW: Smart AI routing + autonomous memory ──
from ai_router import ask_ai as routed_ask_ai
from smart_memory import (
    extract_and_save_facts,
    build_facts_context,
    summarise_facts_for_user,
    forget_fact,
)

from plugins import (
    apps,
    timer,
    system,
    web,
    files,
    automation,
    messaging,
    browser_control,
    modes,
    search_files,
    study_mode,
)

from voice import speak

pygame.mixer.init()
pyautogui.FAILSAFE = True

conversation_history = []

# ================= 🧠 NLP MODEL =================

model = SentenceTransformer("all-MiniLM-L6-v2")

# ================= 🧠 INTENT EXAMPLES =================

INTENTS = {

    "app_control": [
        "open chrome", "launch browser", "start calculator",
        "open notepad", "launch vscode", "open spotify", "start an application"
    ],

    "web_search": [
        "search google", "look something up", "find information online",
        "search formula 1 standings", "tell me about black holes",
        "who is elon musk", "look up spacex", "watch interstellar",
        "play music on youtube", "open quantum physics in youtube", "launch youtube"
    ],

    "file_search": [
        "find my files", "search presentations", "show documents",
        "find robotics ppt", "search powerpoint files", "find my pdfs",
        "search files from january"
    ],

    "system_control": [
        "increase volume", "mute computer", "take screenshot",
        "restart pc", "shutdown pc"
    ],

    "typing": [
        "write an email", "type a formal letter", "draft a message",
        "write a paragraph", "compose a mail"
    ],

    "timer": [
        "set a timer", "start countdown", "set alarm"
    ],

    "messaging": [
        "send whatsapp message", "text dad", "send a message",
        "tell dad hello", "whatsapp mom", "message dad saying hello"
    ],

    "automation": [
        "organize downloads", "sort my files", "clean my desktop",
        "arrange downloads", "organize desktop"
    ],

    "mode": [
        "activate study mode", "enable coding mode", "switch to movie mode",
        "open study mode", "exit study mode"
    ],

    "study": [
        "explain integration", "what is newtons law", "quiz me on thermodynamics",
        "solve my homework", "simulate projectile motion", "plot a graph of velocity",
        "solve this equation", "teach me about organic chemistry", "differentiate sin x",
        "give me practice questions on waves", "solve this puzzle",
        "draw a graph of acceleration", "what is the derivative of",
        "how does photoelectric effect work", "crack this equation",
        "test me on integration"
    ],
}

# ================= 🧠 CREATE EMBEDDINGS =================

intent_embeddings = {}
for intent, examples in INTENTS.items():
    intent_embeddings[intent] = model.encode(examples)

# ================= 🧠 DETECT INTENT =================

def detect_intent(command):
    intent, score, _ = nlp_classify(command, "brain", threshold=0.32)
    print(f"[NLP] {intent} ({score:.2f})")
    return intent if intent else "general_ai"

# ================= 🧹 NORMALISE COMMAND =================

def normalise_command(command):

    cmd = command.lower().strip()

    cmd = re.sub(
        r"\b(i) (dark|light|chrome|firefox|spotify|vscode|loud|silent|quiet)\b",
        r"\1 like \2", cmd
    )
    cmd = re.sub(
        r"\bremember (dark|light|chrome|firefox|spotify|vscode|notepad|edge)\b",
        r"remember that i like \1", cmd
    )
    cmd = re.sub(
        r"\bmy name ([a-z]+)\b",
        lambda m: "my name is " + m.group(1) if m.group(1) != "is" else m.group(0),
        cmd
    )

    separators = ["saying", "that says", "saying that", "with message", "message", "says", "that"]
    has_separator = any(sep in cmd for sep in separators)
    if not has_separator:
        msg_match = re.match(r"^(tell|message|text|whatsapp) ([a-z]+) (.+)$", cmd)
        if msg_match:
            cmd = f"{msg_match.group(1)} {msg_match.group(2)} saying {msg_match.group(3)}"

    cmd = re.sub(r"\bsend ([a-z]+) a message\b", r"send a message to \1", cmd)

    wa_match = re.match(r"^whatsapp ([a-z]+) (.+)$", cmd)
    if wa_match:
        cmd = f"send whatsapp message to {wa_match.group(1)} saying {wa_match.group(2)}"

    cmd = re.sub(r"^find (?!my )(.+)$", r"find my \1", cmd)

    if "when i say" in cmd or "whenever i say" in cmd:
        cmd = re.sub(r"\bon\b", "and", cmd)

    print(f"[NORMALISED] {cmd}")
    return cmd

# ================= 📍 LIVE CONTEXT =================

_location_cache = None


def _reverse_geocode(lat, lon):
    try:
        url = (
            f"https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat}&lon={lon}&format=json"
        )
        resp = requests.get(
            url,
            headers={"User-Agent": "FRIDAY-assistant/1.0"},
            timeout=5
        )
        if resp.status_code == 200:
            addr = resp.json().get("address", {})
            city    = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("county")
                or ""
            )
            state   = addr.get("state", "")
            country = addr.get("country", "")
            parts   = [p for p in [city, state, country] if p]
            return ", ".join(parts)
    except Exception as e:
        print(f"[LOCATION] Reverse geocode failed: {e}")
    return ""


def _get_location_geocoder():
    try:
        import geocoder
        g = geocoder.ip('me')
        if g.ok:
            if g.latlng:
                lat, lon = g.latlng
                print(f"[LOCATION] geocoder lat/lon: {lat:.4f}, {lon:.4f}")
                result = _reverse_geocode(lat, lon)
                if result:
                    return result
            parts = [p for p in [g.city, g.state, g.country] if p]
            result = ", ".join(parts)
            print(f"[LOCATION] geocoder.ip result: {result}")
            return result
    except Exception as e:
        print(f"[LOCATION] geocoder failed: {e}")
    return ""


def _get_location_ip():
    try:
        resp = requests.get("http://ip-api.com/json/", timeout=4)
        if resp.status_code == 200:
            data    = resp.json()
            city    = data.get("city", "")
            region  = data.get("regionName", "")
            country = data.get("country", "")
            parts   = [p for p in [city, region, country] if p]
            return ", ".join(parts) if parts else ""
    except Exception as e:
        print(f"[LOCATION] IP lookup failed: {e}")
    return ""


def get_location():
    global _location_cache
    if _location_cache:
        return _location_cache
    location = _get_location_geocoder()
    if not location:
        print("[LOCATION] Falling back to ip-api.com")
        location = _get_location_ip()
    if not location:
        location = "your location"
    _location_cache = location
    print(f"[LOCATION] Resolved: {location}")
    return location


def get_live_context():
    now = datetime.datetime.now()
    date_str = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%H:%M")
    try:
        tz_abbr = datetime.datetime.now(datetime.timezone.utc).astimezone().tzname() or "local time"
    except Exception:
        tz_abbr = "local time"
    location = get_location()
    return f"[Context: {date_str} | {time_str} {tz_abbr} | {location}]"


# ================= 🔎 LIVE DATA KEYWORDS =================

WEATHER_TRIGGERS = [
    "weather", "temperature", "forecast", "rain", "raining",
    "sunny", "humidity", "hot outside", "cold outside", "how hot",
    "how cold", "will it rain", "should i carry umbrella",
]

LIVE_DATA_TRIGGERS = [
    "news", "latest", "current", "today", "tonight", "tomorrow",
    "score", "match", "standings", "results", "live score",
    "price", "stock", "crypto", "bitcoin", "rate", "exchange rate",
    "war", "conflict", "attack", "election", "protest",
    "traffic", "trending", "breaking", "just happened",
    "who won", "what happened", "update on",
]

def is_weather_query(command):
    cmd = command.lower()
    return any(trigger in cmd for trigger in WEATHER_TRIGGERS)

def needs_live_data(command):
    cmd = command.lower()
    return is_weather_query(cmd) or any(trigger in cmd for trigger in LIVE_DATA_TRIGGERS)


def build_search_query(command, location=""):
    remove = [
        "hey friday", "friday", "what is", "what's", "whats",
        "tell me", "give me", "can you", "please", "the current",
        "right now", "today", "tonight", "what are", "how is",
        "how are", "is there", "any", "the latest",
    ]
    q = command.lower()
    for w in remove:
        q = q.replace(w, "")
    q = q.strip()

    LOCAL_TOPICS = [
        "weather", "temperature", "forecast", "rain", "traffic",
        "news", "election", "protest", "flood",
    ]
    if location and any(t in q for t in LOCAL_TOPICS):
        if location.lower() not in q:
            q = q + " " + location.split(",")[0]

    return q.strip()

# ================= ⚡ PLUGIN MAP =================

PLUGIN_MAP = {
    "app_control":    apps.handle,
    "web_search":     web.handle,
    "file_search":    search_files.handle,
    "system_control": system.handle,
    "messaging":      messaging.handle,
    "automation":     files.handle,
    "timer":          timer.handle,
    "mode":           modes.handle,
    "study":          study_mode.handle,
    "notes":          notes_handle,
    "podcast":        podcast_handle,
}

# ================= ⚡ FAST EXECUTION =================

def fast_path(command):
 
    print("FAST PATH RUNNING")
 
    if is_watcher_command(command):
        watcher_handle(command)
        log_usage(command)
        return True
 
    if is_notes_command(command):
        notes_handle(command)
        log_usage(command)
        return True
 
    if is_podcast_command(command):
        podcast_handle(command)
        log_usage(command)
        return True
 
    # ── CODING MODE (new) ──
    if modes.is_coding_active():
        if is_coding_command(command):
            handled = coding_handle(command)
            if handled:
                log_usage(command)
                last_command["text"]   = command
                last_command["intent"] = "coding"
                return True
        else:
            speak("I am in coding mode. I do not understand that command.")
            return True
        # If not a coding command, fall through to normal AI
 
    if modes.is_study_active():
        mode_switch_words = [
            "coding mode", "movie mode", "writing mode",
            "exit study mode", "stop study mode", "disable study mode"
        ]
        if not any(w in command for w in mode_switch_words):
            print("[STUDY MODE] Routing to study plugin")
            handled = study_mode.handle(command)
            if handled:
                log_usage(command)
                last_command["text"]   = command
                last_command["intent"] = "study"
            return handled
 
    intent  = detect_intent(command)
    handler = PLUGIN_MAP.get(intent)
 
    print("DETECTED:", intent)
    print("HANDLER:", handler)
 
    if handler:
        try:
            handled = handler(command)
            print("HANDLED:", handled)
            if handled:
                log_usage(command)
                last_command["text"]   = command
                last_command["intent"] = intent
                return True
        except Exception as e:
            print("Plugin error:", e)
 
    if is_homework_command(command):
        hw_handle(command)
        log_usage(command)
        return True
 
    return False

# ================= 🧠 LEGACY ask_ai (kept for compatibility) =================

def ask_ai(prompt):
    """Legacy wrapper — now routes through ai_router."""
    return routed_ask_ai(prompt, command=prompt, has_live_data=False)

# ================= 🎯 MAIN PROCESSOR =================

def process_command(command, smart_type=False):

    command = normalise_command(command.lower().strip())

    # ================= 🚨 INTERRUPT =================

    if "stop" in command or "be quiet" in command:
        pygame.mixer.music.stop()
        try:
            pygame.mixer.music.unload()
        except:
            pass
        print("FRIDAY: Speech interrupted.")
        return

    # ================= 🔴 SHUTDOWN =================

    if "shutdown friday" in command:
        speak("Shutting down system")
        os._exit(0)

    # ================= 🧠 AUTONOMOUS MEMORY — passive scan =================
    # Extract any personal facts from what the user just said
    extract_and_save_facts(command)

    # ================= 💬 SMART MEMORY RECALL =================
    # "what do you know about me" / "tell me what you remember about me"

    RECALL_PHRASES = [
        "what do you know about me",
        "what have you learned about me",
        "tell me what you remember about me",
        "what do you remember about me",
        "show me what you know",
        "what facts do you have about me",
    ]
    if any(phrase in command for phrase in RECALL_PHRASES):
        response = summarise_facts_for_user()
        print("FRIDAY:", response)
        speak(response)
        return

    # ================= 🗑️ SMART MEMORY FORGET =================

    FORGET_PHRASES = ["forget my", "forget that i", "forget everything about me"]
    if any(phrase in command for phrase in FORGET_PHRASES):
        # parse key after "forget my <key>"
        m = re.search(r"forget (?:my |that i (?:am |have |))([\w\s]+)", command)
        if m:
            key = m.group(1).strip()
            if forget_fact(key):
                speak(f"Done. I have forgotten your {key}.")
            else:
                speak(f"I do not have anything saved for {key}.")
        else:
            speak("I am not sure what you want me to forget. Try saying forget my name or forget my school.")
        return

    # ================= 🧠 LEARNING — CHECK FIRST =================

    learning_type = is_learning_command(command)
    if learning_type:
        handle(command, learning_type, process_fn=process_command)
        return

    # ================= ⚡ SHORTCUTS =================

    if check_shortcut(command, process_fn=process_command):
        return

    # ================= ⚡ FAST NLP =================

    if fast_path(command):
        return

    # ================= 🧠 LEGACY MEMORY =================

    if "remember" in command:
        data = command.replace("remember", "").strip()
        if " is " in data:
            key, value = data.split(" is ", 1)
            remember(key.strip(), value.strip())
            response = "I will remember that " + key.strip() + " is " + value.strip() + "."
            print("FRIDAY:", response)
            speak(response)
            return

    if "what do you remember about" in command:
        key   = command.replace("what do you remember about", "").strip()
        value = recall(key)
        response = "You told me that " + key + " is " + value + "."
        print("FRIDAY:", response)
        speak(response)
        return

    # ================= ✍️ SMART TYPING NLP =================

    intent = detect_intent(command)
    if intent == "typing":
        smart_type = True

    # ================= 📍 LIVE CONTEXT =================

    live_context = get_live_context()

    # ================= 🔎 LIVE DATA FETCH =================

    web_snippet  = ""
    has_live_data = False

    if needs_live_data(command):

        location = get_location()

        if is_weather_query(command):
            print(f"[LIVE] Weather query → wttr.in for {location}")
            web_snippet = web.fetch_weather(location)
            if not web_snippet:
                search_query = build_search_query(command, location)
                web_snippet  = web.fetch_search_snippet(search_query)
        else:
            search_query = build_search_query(command, location)
            print(f"[LIVE] SerpApi query: {search_query}")
            web_snippet = web.fetch_search_snippet(search_query)

        if web_snippet:
            print(f"[LIVE] Got data ({len(web_snippet)} chars)")
            has_live_data = True
        else:
            print("[LIVE] No data returned — AI will answer from context alone")

    # ================= 🧠 SAVE CONVERSATION =================

    conversation_history.append(f"User: {command}")
    recent_context = "\n".join(conversation_history[-6:])

    # ================= 🧠 SMART MEMORY CONTEXT =================

    facts_context = build_facts_context()

    # ================= ✍️ SMART TYPE PROMPT =================

    if smart_type:
        full_prompt = (
            live_context + "\n"
            "Write polished, natural human-like text.\n"
            "User request: " + command + "\n"
            "Rules:\n"
            "- Professional if needed\n"
            "- Well formatted\n"
            "- Ready to paste\n"
            "- No AI wording\n"
        )

    # ================= 🤖 NORMAL AI =================

    else:
        user_name = recall_preference("name") or "there"

        if web_snippet:
            web_section = (
                "\nLive data retrieved right now — use ONLY this, do not add anything not in it:\n"
                + web_snippet + "\n"
                "Summarise the above naturally in 1-2 sentences as FRIDAY. "
                "Do not guess or add extra information.\n"
            )
        else:
            web_section = ""

        # Inject smart memory facts so FRIDAY sounds like it truly knows the user
        facts_line = ("\n" + facts_context + "\n") if facts_context else ""

        full_prompt = (
            "You are FRIDAY, a calm intelligent AI assistant.\n"
            + live_context + "\n"
            "The user's name is " + user_name + ".\n"
            + facts_line
            + "Rules:\n"
            "- Speak naturally\n"
            "- Be concise\n"
            "- Sound futuristic\n"
            "- Avoid robotic wording\n"
            "- Use the user's name occasionally\n"
            "- Never use apostrophes in your response\n"
            "- Reference the user facts above naturally when relevant\n"
            "- For live events, weather, news or scores: use ONLY the live data provided, never guess\n"
            + web_section
            + "\nConversation:\n" + recent_context + "\n\nFRIDAY:"
        )

    # ================= 🧠 AI RESPONSE (smart-routed) =================

    ai_response = routed_ask_ai(
        full_prompt,
        command=command,
        has_live_data=has_live_data,
    ).strip()

    # ================= ✍️ SMART TYPE EXECUTION =================

    if smart_type:
        print("SMART TYPE:", ai_response)
        pyperclip.copy(ai_response)
        speak("Ready to paste.")
        time.sleep(5)
        pyautogui.hotkey("ctrl", "v")
        return

    # ================= 🧠 SAVE RESPONSE =================

    conversation_history.append(f"FRIDAY: {ai_response}")

    print("FRIDAY:", ai_response)

    # ================= 🔊 SPEAK =================

    threading.Thread(
        target=speak,
        args=(ai_response,),
        daemon=True
    ).start()
