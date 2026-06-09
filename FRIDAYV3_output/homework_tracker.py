import os
import json
import re
import requests
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, date
from groq import Groq

from voice import speak
from memory import load_memory, save_memory
from nlp_router import classify

# ================= ⚙️ CONFIG =================

GROQ_API_KEY    = "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"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"
NOTION_TOKEN    = "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"

# Assessment Tracker database ID (from URL)
NOTION_DB_ID    = "14b6070624e78131946ae4f14e188c1a"

NOTION_HEADERS  = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

HOMEWORK_KEY = "homework_tracker"
SUBJECTS     = ["Math", "Physics", "Chemistry", "English", "CS"]

# subject emoji map for UI
SUBJECT_EMOJIS = {
    "Math":      "🔢",
    "Physics":   "⚛️",
    "Chemistry": "🧪",
    "English":   "📖",
    "CS":        "💻",
}

try:
    groq_client = Groq(api_key=GROQ_API_KEY)
except Exception as e:
    groq_client = None
    print(f"[HW] Groq init failed: {e}")

# ================= 💾 MEMORY =================

def load_hw():
    memory = load_memory()
    if HOMEWORK_KEY not in memory:
        memory[HOMEWORK_KEY] = {"entries": {}, "last_asked": None}
        save_memory(memory)
    return memory[HOMEWORK_KEY]

def save_hw(hw_data):
    memory = load_memory()
    memory[HOMEWORK_KEY] = hw_data
    save_memory(memory)

# ================= 🤖 AI =================

def ask_ai(prompt):
    if not groq_client:
        return ""
    try:
        r = groq_client.chat.completions.create(
            model=GROQ_TEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        print(f"[HW] AI error: {e}")
        return ""

# ================= 📤 NOTION FILE UPLOAD =================

def upload_file_to_notion(file_path):
    """
    File Upload API requires a paid Notion plan.
    Instead we store the local file path in Notes.
    Returns None so the caller skips the Attachments property.
    """
    print(f"[NOTION UPLOAD] File upload API not available on free plan.")
    print(f"[NOTION UPLOAD] File will be noted in Notes column: {file_path}")
    return None

# ================= 📓 NOTION DB ROW =================

def create_notion_assignment(subject, assignment, due_date_str, file_paths=None):
    """
    Create a new row in the Assessment Tracker database.

    Columns:
      Course      — select (Maths, Physics, etc.)
      Assignment  — title
      DueDate     — date
      DaysLeft    — formula (auto-calculated by Notion)
      Attachments — files
    """
    print(f"[NOTION] Creating assignment | {subject}: {assignment} | due: {due_date_str}")

    # ── parse due date ──
    due_date_obj = None
    if due_date_str and due_date_str.strip():
        # try ISO format first
        try:
            due_date_obj = date.fromisoformat(due_date_str)
        except ValueError:
            # try natural language parsing
            from study_planner import parse_date
            due_date_obj = parse_date(due_date_str)

    # File upload noted in Notes instead (free plan limitation)
    file_upload_ids = []

    # ── build properties ──
    properties = {
        "Name": {
            "title": [{"type": "text", "text": {"content": assignment}}]
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
    }

    if due_date_obj:
        properties["Due Date"] = {
            "date": {"start": due_date_obj.isoformat()}
        }

    # File upload API not available on free plan
    # Store file paths in Notes column instead
    if file_paths:
        notes_text = "Attachments: " + ", ".join(file_paths)
        if "Notes" in properties:
            properties["Notes"]["rich_text"][0]["text"]["content"] += "\n" + notes_text
        else:
            properties["Notes"] = {
                "rich_text": [{"type": "text", "text": {"content": notes_text}}]
            }

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
        page_id = r.json().get("id", "")
        print(f"[NOTION] Assignment created: {page_id}")
        return page_id
    else:
        print(f"[NOTION] Failed: {r.status_code} | {r.text[:300]}")
        return None

# ================= 🖥️ HOMEWORK FORM =================

def show_homework_form():
    """
    Dark-theme Tkinter form.
    Each subject row has:
      [Subject label] → [Assignment text entry] [📎 File button] [file name label]
    Returns list of dicts or None if cancelled.
    """

    results    = []
    file_paths = {}   # subject -> list of file paths

    today = date.today().strftime("%A, %d %B %Y")

    # load existing for today
    hw      = load_hw()
    today_k = date.today().isoformat()
    existing = hw.get("entries", {}).get(today_k, {})

    # ── window ──
    root = tk.Tk()
    root.title("FRIDAY — Homework Tracker")
    root.configure(bg="#0f0f1a")
    root.resizable(False, False)

    w, h = 680, 580
    root.update_idletasks()
    x = (root.winfo_screenwidth()  // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    BG       = "#0f0f1a"
    FG       = "#e0e0ff"
    ACCENT   = "#7eb8ff"
    ENTRY_BG = "#1a1a2e"
    BTN_BG   = "#2a2a4e"
    FONT_H   = ("Segoe UI", 12, "bold")
    FONT_L   = ("Segoe UI", 11)
    FONT_S   = ("Segoe UI", 9)

    # ── header ──
    tk.Label(root, text="📚 FRIDAY — Homework Tracker",
             bg=BG, fg=ACCENT, font=("Segoe UI", 15, "bold")).pack(pady=(18, 3))
    tk.Label(root, text=today,
             bg=BG, fg="#666688", font=FONT_S).pack()
    tk.Frame(root, bg=ACCENT, height=1).pack(fill="x", padx=20, pady=10)

    # ── subject rows ──
    entries     = {}
    file_labels = {}

    frame = tk.Frame(root, bg=BG)
    frame.pack(padx=25, pady=5, fill="both", expand=True)

    for subject in SUBJECTS:
        emoji = SUBJECT_EMOJIS.get(subject, "📌")

        row = tk.Frame(frame, bg=BG)
        row.pack(fill="x", pady=7)

        # subject label
        tk.Label(row, text=f"{emoji} {subject}",
                 bg=BG, fg=ACCENT, font=FONT_H, width=13, anchor="w").pack(side="left")
        tk.Label(row, text="→",
                 bg=BG, fg="#444466", font=FONT_L).pack(side="left", padx=4)

        # assignment entry
        e = tk.Entry(row, bg=ENTRY_BG, fg=FG, font=FONT_L,
                     insertbackground=ACCENT, relief="flat",
                     highlightthickness=1, highlightbackground="#2a2a4e",
                     highlightcolor=ACCENT, width=28)
        e.pack(side="left", ipady=6, padx=(0, 8))

        # prefill if exists
        existing_task = existing.get(subject, {}).get("task", "")
        if existing_task and existing_task != "none":
            e.insert(0, existing_task)

        entries[subject] = e
        file_paths[subject] = []

        # file name label (shows selected file names)
        file_lbl = tk.Label(row, text="No file",
                            bg=BG, fg="#444466", font=FONT_S, width=14, anchor="w")

        # file picker button
        def make_file_picker(subj, lbl):
            def pick():
                paths = filedialog.askopenfilenames(
                    title=f"Attach file for {subj}",
                    filetypes=[
                        ("All supported", "*.pdf *.doc *.docx *.png *.jpg *.jpeg *.txt *.pptx *.xlsx"),
                        ("PDF files",     "*.pdf"),
                        ("Word docs",     "*.doc *.docx"),
                        ("Images",        "*.png *.jpg *.jpeg"),
                        ("All files",     "*.*"),
                    ]
                )
                if paths:
                    file_paths[subj] = list(paths)
                    names = ", ".join(os.path.basename(p) for p in paths)
                    # truncate display
                    display = names if len(names) <= 18 else names[:15] + "..."
                    lbl.config(text=display, fg="#7eff7e")
                else:
                    file_paths[subj] = []
                    lbl.config(text="No file", fg="#444466")
            return pick

        btn = tk.Button(row, text="📎 File",
                        bg=BTN_BG, fg=ACCENT, font=FONT_S,
                        relief="flat", padx=8, pady=4,
                        cursor="hand2",
                        command=make_file_picker(subject, file_lbl))
        btn.pack(side="left", padx=(0, 6))
        file_lbl.pack(side="left")
        file_labels[subject] = file_lbl

    # ── due date row ──
    tk.Frame(root, bg="#2a2a4e", height=1).pack(fill="x", padx=20, pady=8)
    due_row = tk.Frame(root, bg=BG)
    due_row.pack(padx=25, fill="x")
    tk.Label(due_row, text="📅 Due date:",
             bg=BG, fg="#888", font=FONT_L).pack(side="left")
    due_entry = tk.Entry(due_row, bg=ENTRY_BG, fg=FG, font=FONT_L,
                         insertbackground=ACCENT, relief="flat",
                         highlightthickness=1, highlightbackground="#2a2a4e",
                         width=22, highlightcolor=ACCENT)
    due_entry.pack(side="left", padx=10, ipady=5)
    due_entry.insert(0, "e.g. tomorrow, 15 June, 2025-06-15")
    due_entry.bind("<FocusIn>",
                   lambda e: due_entry.delete(0, "end")
                   if "e.g." in due_entry.get() else None)

    # ── buttons ──
    tk.Frame(root, bg="#2a2a4e", height=1).pack(fill="x", padx=20, pady=10)
    btn_row = tk.Frame(root, bg=BG)
    btn_row.pack(pady=5)

    def on_save():
        due = due_entry.get().strip()
        if "e.g." in due:
            due = ""
        for subj in SUBJECTS:
            task = entries[subj].get().strip()
            if task:
                results.append({
                    "subject":    subj,
                    "assignment": task,
                    "due":        due,
                    "files":      file_paths.get(subj, [])
                })
        if not results:
            messagebox.showinfo("No homework",
                                "No assignments entered. Add at least one.")
            return
        root.destroy()

    def on_cancel():
        root.destroy()

    tk.Button(btn_row, text="✅  Save to Notion",
              bg=ACCENT, fg="#0f0f1a", font=FONT_H,
              relief="flat", padx=20, pady=9,
              cursor="hand2", command=on_save).pack(side="left", padx=10)

    tk.Button(btn_row, text="Cancel",
              bg=BTN_BG, fg=FG, font=FONT_L,
              relief="flat", padx=15, pady=9,
              cursor="hand2", command=on_cancel).pack(side="left")

    tk.Label(root, text="Leave blank for subjects with no homework",
             bg=BG, fg="#333355", font=FONT_S).pack(pady=(4, 12))

    root.mainloop()
    return results if results else None

# ================= 💾 SAVE + PUSH =================

def save_and_push(hw_entries):
    """Save locally and push each assignment to Notion DB."""
    hw      = load_hw()
    today_k = date.today().isoformat()

    if today_k not in hw["entries"]:
        hw["entries"][today_k] = {}

    success_count = 0
    fail_count    = 0

    for entry in hw_entries:
        subject    = entry["subject"]
        assignment = entry["assignment"]
        due        = entry["due"]
        files      = entry["files"]

        # save locally
        hw["entries"][today_k][subject] = {
            "task":  assignment,
            "done":  False,
            "due":   due,
            "files": files,
        }

        # push to Notion
        page_id = create_notion_assignment(subject, assignment, due, files if files else None)
        if page_id:
            success_count += 1
        else:
            fail_count += 1

    hw["last_asked"] = today_k
    save_hw(hw)

    if fail_count == 0:
        speak(f"{success_count} assignment{'s' if success_count > 1 else ''} saved to Notion.")
    else:
        speak(f"{success_count} saved, {fail_count} failed. Check the terminal for details.")

# ================= ✅ MARK DONE =================

def mark_done(command):
    cmd     = command.lower()
    hw      = load_hw()
    today_k = date.today().isoformat()

    if today_k not in hw["entries"]:
        speak("No homework recorded for today.")
        return True

    matched = None
    for subject in SUBJECTS:
        if subject.lower() in cmd:
            matched = subject
            break

    if not matched:
        speak("Which subject did you finish?")
        return True

    if matched not in hw["entries"][today_k]:
        speak(f"No {matched} homework recorded for today.")
        return True

    hw["entries"][today_k][matched]["done"] = True
    save_hw(hw)

    remaining = [
        s for s in SUBJECTS
        if s in hw["entries"][today_k]
        and not hw["entries"][today_k][s].get("done", False)
        and hw["entries"][today_k][s].get("task", "none") != "none"
    ]

    if remaining:
        speak(f"{matched} done. Still left: {', '.join(remaining)}.")
    else:
        speak("All homework done for today. Great work!")

    return True

def show_remaining(command=None):
    hw      = load_hw()
    today_k = date.today().isoformat()

    if today_k not in hw["entries"]:
        speak("No homework recorded for today. Say enter my homework to add it.")
        return True

    pending = []
    done    = []

    for subject in SUBJECTS:
        entry = hw["entries"][today_k].get(subject, {})
        task  = entry.get("task", "none")
        if task and task != "none":
            if entry.get("done"):
                done.append(subject)
            else:
                pending.append(f"{subject}: {task}")

    if not pending and not done:
        speak("No homework recorded for today.")
    elif not pending:
        speak("All homework is done. Great work!")
    else:
        speak(f"Still pending: {'. '.join(pending)}.")
        if done:
            speak(f"Already completed: {', '.join(done)}.")

    return True

# ================= 🎯 TRIGGER DETECTION =================

HW_TRIGGERS = [
    "enter my homework", "add homework", "homework time",
    "update homework", "new homework", "homework tracker",
    "what is my homework", "show my homework", "pending homework",
    "remaining homework", "what homework", "my homework",
    "finished math", "finished physics", "finished chemistry",
    "finished english", "finished cs", "done with math",
    "done with physics", "done with chemistry", "done with english",
    "done with cs", "completed math", "completed physics",
    "mark math done", "mark physics done", "mark chemistry done",
]

_HW_TRACKER_EXCLUSIONS = [
    "summarize", "summarise", "make notes", "create flashcards",
    "create notes", "bullet notes", "study notes", "from my screen",
    "from this pdf", "scan my screen", "podcast", "explain",
    "simulate", "quiz", "plot", "graph", "solve my homework",
    "what do i use most", "show my preferences", "study plan",
    "study schedule", "what should i study",
]

# Hard trigger phrases that ALWAYS mean homework tracker (skip NLP)
_HW_HARD_TRIGGERS = [
    "enter my homework",
    "add homework",
    "open homework tracker",
    "homework tracker",
    "add today's homework",
    "record my homework",
    "remaining homework",
    "homework status",
    "pending homework",
    "what homework is due",
    "what homework is left",
    "mark homework as done",
    "mark physics as done",
    "mark math as done",
    "mark chemistry as done",
    "mark english as done",
    "mark cs as done",
    "finished my math homework",
    "finished my physics homework",
    "finished my chemistry homework",
    "done with physics",
    "done with math",
    "done with chemistry",
]

def is_homework_command(command):
    """
    Detects homework tracker commands.
    Uses hard triggers first, then NLP with a HIGH threshold (0.52)
    to prevent study/notes commands from being intercepted.
    """
    cmd = command.lower().strip()

    # Exclusions always win
    for excl in _HW_TRACKER_EXCLUSIONS:
        if excl in cmd:
            return False

    # Hard triggers always fire
    for trigger in _HW_HARD_TRIGGERS:
        if trigger in cmd:
            print(f"[HW TRACKER] Hard trigger matched: '{trigger}'")
            return True

    # NLP fallback — high threshold only
    intent, score, _ = classify(command, "homework_tracker", threshold=0.52)
    if intent:
        print(f"[HW TRACKER NLP] intent={intent} score={score:.3f}")
        return True
    return False

def handle(command):
    """NLP-routed homework tracker handler."""
    intent, score, _ = classify(command, "homework_tracker", threshold=0.30)
    print(f"[HW TRACKER] intent={intent} score={score:.3f}")

    if intent == "mark_done":
        return mark_done(command)

    if intent == "show":
        return show_remaining(command)

    # default — enter homework
    speak("Opening homework tracker.")
    hw_entries = show_homework_form()

    if hw_entries:
        save_and_push(hw_entries)
    else:
        speak("Homework entry cancelled.")

    return True