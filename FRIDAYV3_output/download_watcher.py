import os
import re
import json
import time
import base64
import shutil
import requests
import threading
import tempfile
from pathlib import Path
from datetime import date, datetime
from groq import Groq

from voice import speak
from memory import load_memory, save_memory

# ================= ⚙️ CONFIG =================

GROQ_API_KEY      = "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"
GROQ_TEXT_MODEL   = "llama-3.3-70b-versatile"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
NOTION_TOKEN      = "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"
NOTION_DB_ID      = "14b6070624e78131946ae4f14e188c1a"
NOTION_HEADERS    = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# Watch folder — WhatsApp Web downloads go here
WATCH_FOLDER  = os.path.expanduser("D:/Downloads")

# Where to copy classified academic files
ACADEMIC_FOLDER = os.path.join(tempfile.gettempdir(), "FRIDAY_ACADEMIC_FILES")

# How often to scan (seconds)
SCAN_INTERVAL = 15

# Memory key for tracking already-processed files
WATCHER_KEY = "download_watcher"

SUBJECTS = ["Math", "Physics", "Chemistry", "English", "CS"]

SUPPORTED_EXTENSIONS = [
    ".pdf", ".doc", ".docx", ".png", ".jpg",
    ".jpeg", ".txt", ".pptx", ".xlsx", ".webp"
]

os.makedirs(ACADEMIC_FOLDER, exist_ok=True)

try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    print("[WATCHER] Groq client ready.")
except Exception as e:
    groq_client = None
    print(f"[WATCHER] Groq init failed: {e}")

# ================= 💾 MEMORY =================

def load_watcher():
    memory = load_memory()
    if WATCHER_KEY not in memory:
        memory[WATCHER_KEY] = {
            "processed": [],    # list of already-processed file paths
            "enabled":   True,  # whether watcher is active
        }
        save_memory(memory)
    return memory[WATCHER_KEY]

def save_watcher(data):
    memory = load_memory()
    memory[WATCHER_KEY] = data
    save_memory(memory)

def mark_processed(file_path):
    data = load_watcher()
    if file_path not in data["processed"]:
        data["processed"].append(file_path)
        # keep only last 200 entries to avoid bloat
        data["processed"] = data["processed"][-200:]
    save_watcher(data)

def is_processed(file_path):
    data = load_watcher()
    return file_path in data["processed"]

# ================= 🤖 AI =================

def ask_ai(prompt):
    if not groq_client:
        return ""
    try:
        r = groq_client.chat.completions.create(
            model=GROQ_TEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        print(f"[WATCHER] Text AI error: {e}")
        return ""

def ask_vision(prompt, image_path):
    if not groq_client or not os.path.exists(image_path):
        return ""
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        ext  = Path(image_path).suffix.lower()
        mime = {".png":"image/png",".jpg":"image/jpeg",
                ".jpeg":"image/jpeg",".webp":"image/webp"}.get(ext,"image/png")
        r = groq_client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type":"image_url","image_url":{"url":f"data:{mime};base64,{b64}"}},
                    {"type":"text","text":prompt}
                ]
            }],
            max_tokens=500,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        print(f"[WATCHER] Vision AI error: {e}")
        return ""

def read_pdf_text(file_path):
    """Extract text from PDF using PyMuPDF if available."""
    try:
        import fitz  # PyMuPDF
        doc  = fitz.open(file_path)
        text = ""
        for page in doc[:3]:  # read first 3 pages only
            text += page.get_text()
        doc.close()
        return text[:3000]
    except ImportError:
        print("[WATCHER] PyMuPDF not installed. pip install pymupdf")
        return ""
    except Exception as e:
        print(f"[WATCHER] PDF read error: {e}")
        return ""

def read_docx_text(file_path):
    """Extract text from Word document."""
    try:
        import docx
        doc  = docx.Document(file_path)
        text = "\n".join([p.text for p in doc.paragraphs[:50]])
        return text[:3000]
    except ImportError:
        print("[WATCHER] python-docx not installed. pip install python-docx")
        return ""
    except Exception as e:
        print(f"[WATCHER] DOCX read error: {e}")
        return ""

# ================= 🔍 FILE CLASSIFIER =================

def classify_file(file_path):
    """
    Read and classify a file.
    Returns dict with:
      - is_academic: bool
      - is_homework: bool
      - subject: str
      - assignment_name: str
      - due_date: str
      - confidence: str
    Or None if cannot classify.
    """
    ext      = Path(file_path).suffix.lower()
    filename = Path(file_path).stem.lower()

    print(f"[WATCHER] Classifying: {os.path.basename(file_path)}")

    # ── extract content ──
    content = ""

    if ext in [".png", ".jpg", ".jpeg", ".webp"]:
        content = ask_vision(
            "Read all text visible in this image. Return the full text content.",
            file_path
        )

    elif ext == ".pdf":
        content = read_pdf_text(file_path)
        if not content:
            # fallback: convert first page to image and use vision
            content = ask_vision(
                "Read all text visible in this document image. Return the full text.",
                file_path
            )

    elif ext in [".doc", ".docx"]:
        content = read_docx_text(file_path)

    elif ext == ".txt":
        with open(file_path, "r", errors="ignore") as f:
            content = f.read(3000)

    if not content and not filename:
        print(f"[WATCHER] Could not extract content from {file_path}")
        return None

    # ── classify with AI ──
    classify_prompt = f"""You are an academic file classifier for a Grade 11 CBSE student.

Filename: "{os.path.basename(file_path)}"

File content (first 2000 chars):
{content[:2000]}

Classify this file. Return ONLY a JSON object:
{{
  "is_academic": true/false,
  "is_homework": true/false,
  "subject": "Math/Physics/Chemistry/English/CS/Other/Unknown",
  "assignment_name": "short descriptive name for the assignment",
  "due_date": "YYYY-MM-DD or empty string if not mentioned",
  "reason": "one sentence explaining why this is or is not academic homework"
}}

Rules for classification:
- is_academic = true if the file contains study material, notes, questions, assignments, projects, or worksheets
- is_homework = true ONLY if it contains questions to solve, exercises, problems, or a specific assignment/project task
- Promotional content, memes, personal photos, receipts = is_academic: false
- Lecture notes without questions = is_academic: true, is_homework: false
- A worksheet with problems to solve = is_academic: true, is_homework: true

Return ONLY valid JSON, no markdown."""

    result = ask_ai(classify_prompt)

    try:
        clean = re.sub(r"```json|```", "", result).strip()
        data  = json.loads(clean)
        print(f"[WATCHER] Classification: {data}")
        return data
    except Exception as e:
        print(f"[WATCHER] Classification parse failed: {e} | raw: {result[:200]}")
        return None

# ================= 📓 NOTION =================

def create_notion_entry(file_path, classification):
    """Create a Notion DB row for the classified academic file."""

    subject         = classification.get("subject", "Unknown")
    assignment_name = classification.get("assignment_name", os.path.basename(file_path))
    due_date_str    = classification.get("due_date", "")

    # normalize subject to match Notion select options
    subject_map = {
        "mathematics": "Math", "maths": "Math", "math": "Math",
        "physics": "Physics", "chemistry": "Chemistry",
        "english": "English", "cs": "CS",
        "computer science": "CS", "computer": "CS",
    }
    subject = subject_map.get(subject.lower(), subject)
    if subject not in SUBJECTS:
        subject = "Other" if subject != "Unknown" else SUBJECTS[0]

    print(f"[NOTION] Creating entry | {subject}: {assignment_name}")

    properties = {
        "Name": {
            "title": [{"type": "text", "text": {"content": assignment_name}}]
        },
        "Course": {
            "select": {"name": subject}
        },
        "Status": {
            "status": {"name": "Not started"}
        },
        "Completed": {
            "checkbox": False
        },
        "Notes": {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": (
                        f"Auto-detected by FRIDAY\n"
                        f"Source file: {file_path}\n"
                        f"Detected: {datetime.now().strftime('%d %b %Y %H:%M')}"
                    )
                }
            }]
        }
    }

    if due_date_str:
        try:
            date.fromisoformat(due_date_str)  # validate
            properties["Due Date"] = {"date": {"start": due_date_str}}
        except ValueError:
            pass

    payload = {
        "parent":     {"database_id": NOTION_DB_ID},
        "properties": properties
    }

    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS,
        json=payload
    )

    if r.status_code == 200:
        print(f"[NOTION] Entry created: {r.json().get('id')}")
        return True
    else:
        print(f"[NOTION] Failed: {r.status_code} | {r.text[:200]}")
        return False

# ================= 🔁 WATCHER LOOP =================

_watcher_thread = None
_watcher_active = False

def scan_downloads():
    """
    Scan Downloads folder for new unprocessed files.
    Classify each one and create Notion entries for homework.
    """
    new_homework = []

    for f in Path(WATCH_FOLDER).iterdir():

        if not f.is_file():
            continue

        if f.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        file_path = str(f)

        # skip already processed
        if is_processed(file_path):
            continue

        # skip files older than 24 hours (only check recent downloads)
        file_age = time.time() - f.stat().st_mtime
        if file_age > 86400:  # 24 hours
            mark_processed(file_path)  # mark old files so we skip them next time
            continue

        print(f"[WATCHER] New file detected: {f.name}")

        # classify
        classification = classify_file(file_path)
        mark_processed(file_path)

        if not classification:
            continue

        if not classification.get("is_academic") or not classification.get("is_homework"):
            print(f"[WATCHER] Not homework — skipping: {f.name} | reason: {classification.get('reason','')}")
            continue

        # copy to academic folder
        dest = os.path.join(ACADEMIC_FOLDER, f.name)
        try:
            shutil.copy2(file_path, dest)
        except Exception as e:
            print(f"[WATCHER] Copy error: {e}")

        # create Notion entry
        success = create_notion_entry(file_path, classification)

        if success:
            new_homework.append({
                "name":    classification.get("assignment_name", f.name),
                "subject": classification.get("subject", "Unknown"),
            })

    return new_homework

def watcher_loop():
    """Background thread that continuously watches Downloads."""
    global _watcher_active
    print("[WATCHER] Background watcher started.")

    while _watcher_active:
        try:
            new_hw = scan_downloads()
            if new_hw:
                for hw in new_hw:
                    speak(
                        f"New homework detected: {hw['subject']} — "
                        f"{hw['name']}. Added to Notion."
                    )
        except Exception as e:
            print(f"[WATCHER] Loop error: {e}")

        time.sleep(SCAN_INTERVAL)

    print("[WATCHER] Background watcher stopped.")

def start_watcher():
    """Start the background Downloads watcher."""
    global _watcher_thread, _watcher_active

    if _watcher_active:
        print("[WATCHER] Already running.")
        return

    _watcher_active = True
    _watcher_thread = threading.Thread(target=watcher_loop, daemon=True)
    _watcher_thread.start()
    print("[WATCHER] Started.")

def stop_watcher():
    """Stop the background watcher."""
    global _watcher_active
    _watcher_active = False
    print("[WATCHER] Stopped.")

# ================= 🎯 VOICE COMMANDS =================

WATCHER_TRIGGERS = [
    "check my downloads",
    "check for homework",
    "scan downloads",
    "any new homework",
    "check whatsapp files",
    "new files",
    "start watching downloads",
    "stop watching downloads",
    "check for new assignments",
]

def is_watcher_command(command):
    cmd = command.lower()
    return any(t in cmd for t in WATCHER_TRIGGERS)

def handle(command):
    cmd = command.lower()

    if "stop" in cmd and "watch" in cmd:
        stop_watcher()
        speak("Download watcher stopped.")
        return True

    if "start" in cmd and "watch" in cmd:
        start_watcher()
        speak("Download watcher started. I will notify you when new homework files appear.")
        return True

    # manual scan
    speak("Scanning your downloads for homework files.")
    new_hw = scan_downloads()

    if new_hw:
        subjects = ", ".join(set(h["subject"] for h in new_hw))
        speak(
            f"Found {len(new_hw)} homework file{'s' if len(new_hw)>1 else ''}. "
            f"Subjects: {subjects}. All added to Notion."
        )
    else:
        speak("No new homework files found in your downloads.")

    return True