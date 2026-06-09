import os, time, base64, json, re
from pathlib import Path
from groq import Groq

GROQ_API_KEY      = "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"
GROQ_TEXT_MODEL   = "llama-3.3-70b-versatile"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
WATCH_FOLDER      = os.path.expanduser("~/Downloads")
SUPPORTED_EXTENSIONS = [".pdf",".doc",".docx",".png",".jpg",".jpeg",".txt",".pptx",".xlsx",".webp"]

groq_client = Groq(api_key=GROQ_API_KEY)

print(f"\n[DEBUG] Scanning: {WATCH_FOLDER}")
print("-" * 60)

all_files = list(Path(WATCH_FOLDER).iterdir())
print(f"Total items in Downloads: {len(all_files)}\n")

for f in sorted(all_files, key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
    if not f.is_file(): continue
    age = time.time() - f.stat().st_mtime
    print(f"  {f.name} | age: {int(age)}s | ext: '{f.suffix.lower()}' | supported: {f.suffix.lower() in SUPPORTED_EXTENSIONS}")