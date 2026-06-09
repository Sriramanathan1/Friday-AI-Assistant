"""
ai_router.py — Smart AI routing for FRIDAY

Routes queries between:
  - Ollama (local, fast): simple queries, typing, local tasks
  - Groq (cloud, live):   tasks requiring real-time/present information

Uses NLP (sentence embeddings) to decide which backend to use.
Falls back to Ollama if Groq is unavailable.
"""

import requests
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# ================= 🔑 CONFIG =================

from config import GROQ_API_KEY, GROQ_MODEL, OLLAMA_MODEL, OLLAMA_URL

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# ================= 🧠 NLP MODEL (reuse same one) =================

print("[AI ROUTER] Loading routing model...")
_model = SentenceTransformer("all-MiniLM-L6-v2")
print("[AI ROUTER] Routing model ready.")

# ================= 📋 ROUTING EXAMPLES =================
# These define what kind of tasks go to each backend

GROQ_EXAMPLES = [
    # Live / real-time information
    "what is the weather today",
    "latest news this morning",
    "current score of the cricket match",
    "who won the election yesterday",
    "what is the stock price of apple",
    "is it going to rain today",
    "breaking news today",
    "what happened in the war today",
    "current bitcoin price",
    "traffic right now",
    "what time does the match start today",
    "recent developments in ai",
    "trending topics today",
    "tell me about today",
    "what is the exchange rate now",
    "live updates",
    # Complex reasoning / research
    "explain quantum entanglement in detail",
    "compare two complex theories",
    "write a detailed analysis of this topic",
    "research this subject deeply",
    "summarize the latest papers on ai",
    "detailed study plan for my exams",
    "advanced mathematical derivation",
    "solve complex multi-step problem",
]

OLLAMA_EXAMPLES = [
    # Simple local queries
    "what is two plus two",
    "tell me a joke",
    "what is the capital of france",
    "define photosynthesis",
    "who is newton",
    "say hello",
    "how are you",
    "what does this word mean",
    # Typing and text generation
    "write an email for me",
    "type this out",
    "draft a message",
    "write a paragraph about",
    "compose a formal letter",
    "help me write this",
    # Local tasks
    "open chrome",
    "set a timer",
    "take a screenshot",
    "increase the volume",
    "remind me in ten minutes",
    "what time is it",
    "play music",
    "organize my files",
    "send a whatsapp message",
    # Conversational
    "what can you do",
    "help me",
    "good morning friday",
    "what is your name",
    "how does this work",
    "can you explain this concept",
    "tell me about history",
    "quiz me on this topic",
]

# Precompute embeddings
_groq_embeddings   = _model.encode(GROQ_EXAMPLES)
_ollama_embeddings = _model.encode(OLLAMA_EXAMPLES)

# ================= 🎯 ROUTER LOGIC =================

def should_use_groq(command: str, has_live_data: bool = False) -> bool:
    """
    Decide whether this query needs Groq (cloud) or Ollama (local).

    Returns True → use Groq
    Returns False → use Ollama (default)
    """
    # If brain.py already fetched live web data, always use Groq to process it
    if has_live_data:
        return True

    cmd_emb = _model.encode([command.lower().strip()])

    groq_score   = float(np.max(cosine_similarity(cmd_emb, _groq_embeddings)[0]))
    ollama_score = float(np.max(cosine_similarity(cmd_emb, _ollama_embeddings)[0]))

    print(f"[AI ROUTER] groq={groq_score:.3f}  ollama={ollama_score:.3f}", end="")

    decision = groq_score > ollama_score
    print(f"  → {'GROQ' if decision else 'OLLAMA'}")

    return decision


# ================= 🤖 OLLAMA CALL =================

def ask_ollama(prompt: str) -> str:
    """Call local Ollama model."""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        data = response.json()
        return data.get("response", "").strip()
    except Exception as e:
        print(f"[OLLAMA] Error: {e}")
        return ""


# ================= ⚡ GROQ CALL =================

def ask_groq(prompt: str) -> str:
    """Call Groq cloud API (OpenAI-compatible)."""
    if GROQ_API_KEY == "YOUR_GROQ_API_KEY_HERE":
        print("[GROQ] No API key set — falling back to Ollama")
        return ask_ollama(prompt)

    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type":  "application/json",
        }
        body = {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 512,
            "temperature": 0.7,
        }
        response = requests.post(GROQ_URL, headers=headers, json=body, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        else:
            print(f"[GROQ] HTTP {response.status_code} — falling back to Ollama")
            return ask_ollama(prompt)
    except Exception as e:
        print(f"[GROQ] Error: {e} — falling back to Ollama")
        return ask_ollama(prompt)


# ================= 🚀 MAIN ENTRY POINT =================

def ask_ai(prompt: str, command: str = "", has_live_data: bool = False) -> str:
    """
    Route the prompt to the right AI backend.

    Args:
        prompt:        The full prompt to send
        command:       The original user command (for routing decision)
        has_live_data: Whether live web data was already fetched
    """
    use_groq = should_use_groq(command or prompt, has_live_data)

    if use_groq:
        result = ask_groq(prompt)
        if not result:
            print("[AI ROUTER] Groq returned empty — falling back to Ollama")
            result = ask_ollama(prompt)
        return result
    else:
        result = ask_ollama(prompt)
        if not result:
            print("[AI ROUTER] Ollama returned empty — trying Groq")
            result = ask_groq(prompt)
        return result
