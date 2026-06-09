import webbrowser
import urllib.parse
import requests
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SERPAPI_KEY

from voice import speak


# ================= 🔑 SERPAPI KEY =================

SERPAPI_KEY = SERPAPI_KEY  # centralised in config.py


# ================= 🌦️ WEATHER FETCHER (wttr.in) =================

def fetch_weather(location, max_chars=400):
    """
    Fetches current weather for a location using wttr.in.
    Returns a clean string like:
        Madurai, Tamil Nadu, India: Partly Cloudy, +31°C, Humidity: 68%, Wind: 14km/h
    """
    try:
        url = f"https://wttr.in/{urllib.parse.quote(location)}?format=%l:+%C,+%t,+Humidity:+%h,+Wind:+%w"
        resp = requests.get(url, timeout=6)
        if resp.status_code == 200 and resp.text.strip():
            return resp.text.strip()[:max_chars]
    except Exception as e:
        print(f"[WEATHER] wttr.in failed: {e}")
    return ""


# ================= 🔍 SERPAPI LIVE SEARCH =================

def fetch_search_snippet(query, max_chars=800):
    """
    Uses SerpApi to search Google and extract the most relevant
    answer snippet. Tries in order:
        1. Answer box (direct answer)
        2. Knowledge graph description
        3. Top organic result snippets
    Returns a string, or "" on failure.
    """
    try:
        params = {
            "q":      query,
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "num":    5,
            "hl":     "en",
            "gl":     "in",       # country = India for local relevance
        }

        resp = requests.get(
            "https://serpapi.com/search",
            params=params,
            timeout=8
        )

        if resp.status_code != 200:
            print(f"[SERPAPI] HTTP {resp.status_code}")
            return ""

        data = resp.json()
        parts = []

        # ── 1. Answer box (best for weather, sports, direct questions) ──
        answer_box = data.get("answer_box", {})
        if answer_box:
            for field in ["answer", "result", "snippet", "contents"]:
                val = answer_box.get(field)
                if val and isinstance(val, str):
                    parts.append(val.strip())
                    break

        # ── 2. Knowledge graph (people, places, events) ──
        kg = data.get("knowledge_graph", {})
        if kg:
            kg_desc = kg.get("description") or kg.get("snippet", "")
            if kg_desc:
                parts.append(kg_desc.strip())

        # ── 3. Top organic snippets ──
        organic = data.get("organic_results", [])
        for result in organic[:3]:
            snippet = result.get("snippet", "")
            if snippet:
                parts.append(snippet.strip())

        if not parts:
            print("[SERPAPI] No usable results")
            return ""

        combined = " | ".join(parts)
        print(f"[SERPAPI] Got data ({len(combined)} chars)")
        return combined[:max_chars]

    except Exception as e:
        print(f"[SERPAPI] Failed: {e}")
        return ""


def handle(command):

    command = command.lower().strip()

    # ================= 🌐 DIRECT WEBSITE OPEN =================

    DIRECT_OPEN = {
        "open youtube":   "https://youtube.com",
        "launch youtube": "https://youtube.com",
        "open gmail":     "https://mail.google.com",
        "open whatsapp":  "https://web.whatsapp.com",
        "open linkedin":  "https://linkedin.com",
        "open github":    "https://github.com",
        "open chatgpt":   "https://chatgpt.com",
    }

    for trigger, url in DIRECT_OPEN.items():
        if trigger in command:
            webbrowser.open(url)
            speak("Opening website")
            return True

    # ================= ▶️ YOUTUBE SEARCH =================

    YOUTUBE_PHRASES = ["on youtube", "in youtube", "youtube", "watch", "play"]

    if any(phrase in command for phrase in YOUTUBE_PHRASES):

        query = command
        REMOVE = [
            "search", "find", "look up", "watch", "play",
            "on youtube", "in youtube", "youtube",
            "can you", "please", "open"
        ]
        for word in REMOVE:
            query = query.replace(word, "")
        query = query.strip()

        if not query:
            webbrowser.open("https://youtube.com")
            speak("Opening YouTube")
            return True

        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
        webbrowser.open(url)
        speak("Searching YouTube")
        return True

    # ================= 🌐 GOOGLE SEARCH =================

    SEARCH_PHRASES = [
        "search", "look up", "lookup", "find",
        "what is", "who is", "tell me about", "search for"
    ]

    if any(phrase in command for phrase in SEARCH_PHRASES):

        query = command
        for word in SEARCH_PHRASES:
            query = query.replace(word, "")
        query = query.strip()

        if not query:
            return False

        url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
        webbrowser.open(url)
        speak("Searching Google")
        return True

    return False