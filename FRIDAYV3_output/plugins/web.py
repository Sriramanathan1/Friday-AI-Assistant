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



# ================= 🔍 RICH SEARCH (summarised + links) =================

def fetch_rich_search(query: str, num_results: int = 6) -> dict:
    """
    Full SerpAPI search that returns structured results:
      {
        "answer_box":  str | None,   # direct answer if available
        "results": [
            {"title": str, "snippet": str, "link": str},
            ...
        ]
      }
    Used by search_and_summarise() to build a Groq-summarised reply with links.
    """
    try:
        params = {
            "q":       query,
            "api_key": SERPAPI_KEY,
            "engine":  "google",
            "num":     num_results,
            "hl":      "en",
            "gl":      "in",
        }
        resp = requests.get(
            "https://serpapi.com/search",
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[SERPAPI RICH] HTTP {resp.status_code}")
            return {"answer_box": None, "results": []}

        data = resp.json()
        out  = {"answer_box": None, "results": []}

        # ── Answer box ──
        ab = data.get("answer_box", {})
        if ab:
            for field in ["answer", "result", "snippet", "contents"]:
                val = ab.get(field)
                if val and isinstance(val, str):
                    out["answer_box"] = val.strip()
                    break

        # ── Shopping results (product searches like "find a pull up bar") ──
        shopping = data.get("shopping_results", [])
        for item in shopping[:4]:
            title   = item.get("title", "")
            price   = item.get("price", "")
            source  = item.get("source", "")
            link    = item.get("link") or item.get("product_link", "")
            snippet = f"{price} — {source}" if price else source
            if title:
                out["results"].append({
                    "title":   title,
                    "snippet": snippet,
                    "link":    link,
                })

        # ── Organic results ──
        for r in data.get("organic_results", [])[:num_results]:
            title   = r.get("title", "")
            snippet = r.get("snippet", "")
            link    = r.get("link", "")
            if title or snippet:
                out["results"].append({
                    "title":   title,
                    "snippet": snippet,
                    "link":    link,
                })

        # Deduplicate by link
        seen  = set()
        dedup = []
        for r in out["results"]:
            key = r["link"] or r["title"]
            if key not in seen:
                seen.add(key)
                dedup.append(r)
        out["results"] = dedup[:6]

        print(f"[SERPAPI RICH] {len(out['results'])} results for: {query!r}")
        return out

    except Exception as e:
        print(f"[SERPAPI RICH] Error: {e}")
        return {"answer_box": None, "results": []}


def search_and_summarise(query: str) -> dict:
    """
    Search the web for `query`, then ask Groq to summarise the results
    into a concise spoken answer.

    Returns:
        {
            "spoken":  str,          # 2-3 sentence spoken summary (no URLs)
            "links":   [             # up to 4 relevant links
                {"title": str, "url": str},
                ...
            ],
            "raw_answer_box": str | None,
        }
    """
    from config import GROQ_API_KEY, GROQ_MODEL

    data = fetch_rich_search(query)

    answer_box = data.get("answer_box")
    results    = data.get("results", [])

    # ── Build a context block for Groq ──
    context_lines = []
    if answer_box:
        context_lines.append(f"Direct answer: {answer_box}")
    for i, r in enumerate(results, 1):
        parts = []
        if r["title"]:   parts.append(r["title"])
        if r["snippet"]: parts.append(r["snippet"])
        context_lines.append(f"{i}. {' — '.join(parts)}")

    context = "\n".join(context_lines) if context_lines else "No results found."

    # ── Ask Groq to summarise ──
    system_prompt = (
        "You are FRIDAY, a smart voice assistant. "
        "The user asked a real-time question. You have web search results below. "
        "Write a concise, natural spoken summary in 2-3 sentences. "
        "Do NOT include URLs, bullet points, or markdown. "
        "Do NOT say things like \'according to search results\'. "
        "Just answer naturally as if you already know, and mention prices, "
        "dates, or specifics when available. "
        "Never use apostrophes (say \'do not\' not \'don\'t\')."
    )

    user_prompt = (
        f"User question: {query}\n\n"
        f"Search results:\n{context}\n\n"
        "Give me a short spoken answer (2-3 sentences, no URLs, no bullets):"
    )

    spoken = ""
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "model":       GROQ_MODEL,
                "messages":    [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                "max_tokens":  256,
                "temperature": 0.4,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            spoken = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[SEARCH SUMMARISE] Groq error: {e}")

    # Fallback: use raw answer box or first snippet if Groq failed
    if not spoken:
        if answer_box:
            spoken = answer_box
        elif results:
            spoken = results[0].get("snippet") or results[0].get("title", "")
        else:
            spoken = "I could not find a clear answer online."

    # ── Collect links (only results that have a real URL) ──
    links = [
        {"title": r["title"] or r["snippet"][:60], "url": r["link"]}
        for r in results
        if r.get("link")
    ][:4]

    return {
        "spoken":          spoken,
        "links":           links,
        "raw_answer_box":  answer_box,
    }

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