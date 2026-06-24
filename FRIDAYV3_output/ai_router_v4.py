"""
ai_router_v4.py — FRIDAY Lightweight AI Router

Replaces the old ai_router.py which loaded SentenceTransformer on import
(slow ~2s boot, unnecessary now that Groq handles all routing via tool-calling).

This module is a thin wrapper used by tool_executor.py for:
  - smart_type()    → generate polished text
  - coding_assist() → fallback AI coding help
  - study_assist()  → fallback AI tutor
  - smart_memory.py → LLM-based fact extraction

All calls go to the same Groq endpoint as brain_v4.py.
No embeddings. No local models. No startup delay.
"""

import requests
import os
from config import GROQ_API_KEY, GROQ_MODEL

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ================= CORE CALLER =================

def ask_ai(
    prompt: str,
    system: str = "You are FRIDAY, a helpful AI assistant. Be concise and direct.",
    command: str = "",
    max_tokens: int = 800,
    temperature: float = 0.5,
) -> str:
    """
    Send a single prompt to Groq and return the text response.

    Args:
        prompt:      The user-facing prompt or task description.
        system:      Optional system prompt override.
        command:     Original user command (for logging — unused in request).
        max_tokens:  Max output tokens (default 800).
        temperature: Sampling temperature (default 0.5).

    Returns:
        The model's text response, or an error string.
    """
    if not GROQ_API_KEY:
        return "Error: GROQ_API_KEY not set."

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]

    try:
        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model":       GROQ_MODEL,
                "messages":    messages,
                "max_tokens":  max_tokens,
                "temperature": temperature,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    except requests.exceptions.Timeout:
        return "Error: AI request timed out."
    except requests.exceptions.RequestException as e:
        return f"Error: AI request failed — {e}"
    except (KeyError, IndexError) as e:
        return f"Error: Unexpected API response — {e}"


# ================= SPECIALISED CALLERS =================

def ask_coding(task: str, language: str = "python") -> str:
    """Generate code or explain a coding concept."""
    system = (
        f"You are an expert {language} developer. "
        "Provide working, well-commented code. "
        "Be concise. Output code in plain text with no markdown fences unless asked."
    )
    return ask_ai(task, system=system, max_tokens=1000, temperature=0.3)


def ask_tutor(task: str, subject: str = "") -> str:
    """Answer a study/homework question clearly."""
    subject_note = f"Subject: {subject}. " if subject else ""
    system = (
        f"You are a knowledgeable tutor. {subject_note}"
        "Explain clearly and accurately. "
        "Use examples where helpful. Keep answers concise."
    )
    return ask_ai(task, system=system, max_tokens=900, temperature=0.4)


def ask_compose(request: str, tone: str = "professional") -> str:
    """Compose a piece of text (email, message, essay) in a given tone."""
    system = (
        f"You are a skilled writer. Write text in a {tone} tone. "
        "Output ONLY the final text — no preamble, no explanation, no quotes, no markdown."
    )
    return ask_ai(request, system=system, max_tokens=700, temperature=0.6)


def extract_facts_with_llm(sentence: str) -> dict:
    """
    Use the LLM to extract personal facts from a sentence as JSON.
    Returns a dict like {"name": "Sri", "city": "Chennai"} or {} if nothing found.
    Used as a fallback by smart_memory.py when regex patterns miss.
    """
    prompt = (
        "Extract personal facts about the speaker from this sentence. "
        "Return ONLY a JSON object with keys like: "
        "name, city, school, college, age, interest, hobby, goal, language, nickname, class. "
        "If the sentence contains no personal facts, return exactly: {}\n\n"
        f"Sentence: {sentence}\n\nJSON:"
    )
    system = "You are a fact extraction engine. Output only valid JSON. No markdown, no explanation."
    raw = ask_ai(prompt, system=system, max_tokens=200, temperature=0.1)

    # Strip any accidental markdown fences
    raw = raw.strip().replace("```json", "").replace("```", "").strip()

    try:
        result = __import__("json").loads(raw)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}
