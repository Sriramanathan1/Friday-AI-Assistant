import os

# ── Groq ──
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama3-70b-8192"

# ── Ollama ──
OLLAMA_MODEL = "phi3"
OLLAMA_URL   = "http://localhost:11434/api/generate"

# ── SerpApi ──
SERPAPI_KEY  = os.getenv("SERPAPI_KEY", "")