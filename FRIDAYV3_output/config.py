import os

# ── Groq ──
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "openai/gpt-oss-120b"   # llama-3.3-70b-versatile was deprecated 2026-06-17

# ── Groq Whisper (STT) ──
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"  # fastest + most accurate on Groq

# ── Ollama ──
OLLAMA_MODEL = "phi3"
OLLAMA_URL   = "http://localhost:11434/api/generate"

# ── SerpApi ──
SERPAPI_KEY  = os.getenv("SERPAPI_KEY", "")