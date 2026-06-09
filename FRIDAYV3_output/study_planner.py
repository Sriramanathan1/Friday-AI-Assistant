import os
import re
import json
import webbrowser
import tempfile
import speech_recognition as sr
from datetime import datetime, date, timedelta
from groq import Groq

from voice import speak
from memory import load_memory, save_memory
from config import GROQ_API_KEY as _CONFIG_GROQ_KEY
from ai_router import ask_ai as _routed_ask_ai

# ================= ⚙️ CONFIG =================

GROQ_API_KEY    = _CONFIG_GROQ_KEY or "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"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"
OUTPUT_DIR      = os.path.join(tempfile.gettempdir(), "FRIDAY_STUDY")
PLANNER_KEY     = "study_planner"

os.makedirs(OUTPUT_DIR, exist_ok=True)

try:
    groq_client = Groq(api_key=GROQ_API_KEY)
except Exception as e:
    groq_client = None
    print(f"[PLANNER] Groq init failed: {e}")

# ================= 🔑 NOTION SETUP =================

NOTION_TOKEN   = "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"
NOTION_PAGE_ID = "14b6070624e780d98d37c53dd44b7009"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# ================= 🎤 VOICE INPUT =================

def listen_response(timeout=10):
    """Listen for a short voice response."""
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.listen(source, timeout=timeout, phrase_time_limit=20)
        text = r.recognize_google(audio).lower().strip()
        print(f"[PLANNER] Heard: '{text}'")
        return text
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print(f"[PLANNER] Listen error: {e}")
        return ""

# ================= 🤖 AI =================

def ask_ai(prompt):
    """Routes through ai_router — Ollama for simple tasks, Groq for complex ones."""
    return _routed_ask_ai(prompt, command=prompt, has_live_data=False)

# ================= 💾 MEMORY HELPERS =================

def load_planner():
    """Load planner data from memory.json."""
    memory = load_memory()
    if PLANNER_KEY not in memory:
        memory[PLANNER_KEY] = {
            "exams":         [],     # list of {subject, date, portions, weak_topics}
            "last_asked":    None,   # date string when we last asked
            "daily_plan":    {},     # date -> list of study tasks
            "weak_subjects": [],     # subjects user struggles with
            "completed":     [],     # completed tasks
        }
        save_memory(memory)
    return memory[PLANNER_KEY]

def save_planner(planner_data):
    """Save planner data back into memory.json."""
    memory = load_memory()
    memory[PLANNER_KEY] = planner_data
    save_memory(memory)

# ================= 📅 DATE PARSER =================

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
}

def parse_date(text):
    """
    Parse a spoken date like:
    'fifteenth january', '15 january', 'january 15', '15th of january'
    Returns a date object or None.
    """
    text = text.lower().strip()

    # normalize ordinals
    text = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text)
    text = text.replace(" of ", " ")

    # find month
    month = None
    for name, num in MONTH_MAP.items():
        if name in text:
            month = num
            break

    # find day number
    numbers = re.findall(r"\b(\d{1,2})\b", text)
    day = int(numbers[0]) if numbers else None

    # find year
    year_match = re.findall(r"\b(202\d)\b", text)
    year = int(year_match[0]) if year_match else datetime.now().year

    if month and day:
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None

def days_until(exam_date_str):
    """Return days until exam from today."""
    try:
        exam_date = date.fromisoformat(exam_date_str)
        return (exam_date - date.today()).days
    except Exception:
        return 999

# ================= 🗣️ DAILY STARTUP INTERVIEW =================

def run_startup_interview():
    """
    Ask the user about their exams on startup.
    Only runs once per day.
    """
    planner = load_planner()
    today   = date.today().isoformat()

    if planner.get("last_asked") == today:
        print("[PLANNER] Already asked today — skipping interview.")
        return

    speak("Good morning! Before we start, let me update your study plan. How many exams do you have coming up?")
    response = listen_response()

    # extract number of exams
    nums = re.findall(r"\b(\d+)\b", response)
    num_exams = int(nums[0]) if nums else 0

    if num_exams == 0:
        # check if they said a word number
        word_nums = {"one":1,"two":2,"three":3,"four":4,"five":5,
                     "six":6,"seven":7,"eight":8,"nine":9,"ten":10}
        for word, n in word_nums.items():
            if word in response:
                num_exams = n
                break

    if num_exams == 0:
        speak("No problem. I will check again tomorrow. Say show my study plan anytime to get started.")
        planner["last_asked"] = today
        save_planner(planner)
        return

    speak(f"Got it, {num_exams} exams. Let me note them down one by one.")

    new_exams = []
    for i in range(num_exams):

        # ── subject ──
        speak(f"Exam {i+1}: what subject is it?")
        subject = listen_response(timeout=8)
        if not subject:
            speak("I did not catch that. Skipping this exam.")
            continue

        # ── date ──
        speak(f"What date is your {subject} exam?")
        date_response = listen_response(timeout=8)
        exam_date = parse_date(date_response)

        if not exam_date:
            speak(f"I could not understand the date. I will set {subject} as upcoming.")
            exam_date_str = ""
        else:
            exam_date_str = exam_date.isoformat()
            days = (exam_date - date.today()).days
            speak(f"{subject} on {exam_date.strftime('%d %B')}. That is {days} days away.")

        # ── portions ──
        speak(f"What chapters or portions are left for {subject}?")
        portions = listen_response(timeout=12)

        # ── weak topics ──
        speak(f"Any specific topics in {subject} you find difficult?")
        weak = listen_response(timeout=10)

        new_exams.append({
            "subject":     subject,
            "date":        exam_date_str,
            "portions":    portions,
            "weak_topics": weak,
        })

        speak(f"Got it. {subject} noted.")

    # merge with existing exams (update if subject already exists)
    existing = {e["subject"].lower(): e for e in planner.get("exams", [])}
    for exam in new_exams:
        existing[exam["subject"].lower()] = exam

    planner["exams"]      = list(existing.values())
    planner["last_asked"] = today

    save_planner(planner)
    speak("All noted. Generating your study plan now.")
    generate_plan()

# ================= 🧠 PLAN GENERATOR =================

def generate_plan():
    """Use Groq to generate a prioritized daily study plan."""
    planner = load_planner()
    exams   = planner.get("exams", [])

    if not exams:
        speak("I do not have any exam data yet. Say update my study plan to add your exams.")
        return False

    today_str = date.today().strftime("%d %B %Y")

    # build exam summary for AI
    exam_lines = []
    for e in exams:
        days = days_until(e.get("date", "")) if e.get("date") else "?"
        exam_lines.append(
            f"- {e['subject']}: exam in {days} days | "
            f"portions left: {e.get('portions','unknown')} | "
            f"weak topics: {e.get('weak_topics','none')}"
        )

    exam_summary = "\n".join(exam_lines)

    prompt = f"""You are a smart academic planner for a Grade 11 CBSE student.

Today is {today_str}.

Upcoming exams:
{exam_summary}

Generate a 7-day study plan starting from today.

Rules:
1. Prioritize subjects with fewer days remaining
2. Spend more time on weak topics
3. Each day should have 3-5 study sessions of 45-60 minutes each
4. Include short breaks (Pomodoro style)
5. Leave the day before each exam for revision only
6. Sunday should be lighter (revision + rest)
7. Be specific — mention exact chapter names and topics from the portions

Return ONLY a JSON object with this structure:
{{
  "summary": "one paragraph overview of the plan strategy",
  "weak_priority": ["subject1", "subject2"],
  "days": [
    {{
      "date": "YYYY-MM-DD",
      "day_name": "Monday",
      "sessions": [
        {{
          "time": "4:00 PM",
          "subject": "Physics",
          "topic": "Specific chapter/topic",
          "duration": 60,
          "type": "study" or "revision" or "practice" or "rest"
        }}
      ]
    }}
  ]
}}

Return ONLY valid JSON, no markdown."""

    result = ask_ai(prompt)

    try:
        clean    = re.sub(r"```json|```", "", result).strip()
        plan     = json.loads(clean)
        planner["daily_plan"] = plan
        save_planner(planner)
        open_planner_browser(plan, exams)
        push_to_notion(plan, exams)
        speak("Your study plan is ready. I have opened it in your browser and added it to Notion.")
        return True
    except Exception as e:
        print(f"[PLANNER] Plan parse failed: {e}")
        speak("I had trouble generating the plan. Please try again.")
        return False

# ================= 🌐 BROWSER PLANNER =================

SESSION_TYPE_COLORS = {
    "study":    "#7eb8ff",
    "revision": "#a0ffa0",
    "practice": "#ffb07e",
    "rest":     "#666688",
}


# ================= 📓 NOTION INTEGRATION =================

SUBJECT_COLORS = {
    "maths":     "blue",
    "physics":   "purple",
    "chemistry": "green",
    "revision":  "yellow",
    "rest":      "gray",
    "practice":  "orange",
}

def _notion_text(content, bold=False, color="default"):
    block = {"type": "text", "text": {"content": content}}
    if bold or color != "default":
        block["annotations"] = {}
        if bold:
            block["annotations"]["bold"] = True
        if color != "default":
            block["annotations"]["color"] = color
    return block

def _notion_heading(text, level=2):
    tag = f"heading_{level}"
    return {
        "object": "block",
        "type": tag,
        tag: {
            "rich_text": [_notion_text(text)],
            "color": "default"
        }
    }

def _notion_callout(text, emoji="📌", color="blue_background"):
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [_notion_text(text)],
            "icon": {"type": "emoji", "emoji": emoji},
            "color": color
        }
    }

def _notion_divider():
    return {"object": "block", "type": "divider", "divider": {}}

def _notion_todo(text, checked=False, color="default"):
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": [_notion_text(text)],
            "checked": checked,
            "color": color
        }
    }

def _notion_bullet(text, color="default"):
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [_notion_text(text)],
            "color": color
        }
    }

def _notion_paragraph(text):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [_notion_text(text)],
        }
    }

def _create_notion_page(title, parent_page_id, blocks):
    """Create a new child page inside the dashboard."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
        "children": blocks[:100]  # Notion allows max 100 blocks per request
    }
    r = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS,
        json=payload
    )
    if r.status_code == 200:
        page = r.json()
        print(f"[NOTION] Page created: {page.get('id')}")
        return page.get("id")
    else:
        print(f"[NOTION] Failed to create page: {r.status_code} | {r.text[:200]}")
        return None

def _append_blocks(page_id, blocks):
    """Append additional blocks to an existing Notion page."""
    payload = {"children": blocks}
    r = requests.patch(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=NOTION_HEADERS,
        json=payload
    )
    if r.status_code != 200:
        print(f"[NOTION] Append failed: {r.status_code} | {r.text[:200]}")

def push_to_notion(plan, exams):
    """
    Push the full study plan to Notion as a structured page
    inside the user dashboard.
    """
    today     = date.today()
    title     = f"Study Plan — {today.strftime('%d %B %Y')}"
    summary   = plan.get("summary", "")

    print(f"[NOTION] Creating page: {title}")

    blocks = []

    # ── summary callout ──
    blocks.append(_notion_callout(
        f"Strategy: {summary}",
        emoji="💡",
        color="blue_background"
    ))
    blocks.append(_notion_divider())

    # ── exam countdown ──
    blocks.append(_notion_heading("📅 Exam Countdown", level=2))

    sorted_exams = sorted(exams, key=lambda e: days_until(e.get("date", "")))
    for e in sorted_exams:
        days  = days_until(e.get("date", ""))
        d_str = e.get("date", "")
        try:
            date_label = date.fromisoformat(d_str).strftime("%d %B %Y")
        except Exception:
            date_label = "TBD"

        emoji = "🔴" if days <= 3 else "🟠" if days <= 7 else "🔵"
        weak  = e.get("weak_topics", "none")
        portions = e.get("portions", "")

        blocks.append(_notion_bullet(
            f"{emoji} {e['subject'].title()} — {date_label} ({days} days away)"
        ))
        if portions:
            blocks.append(_notion_bullet(f"   📚 Portions: {portions}"))
        if weak and weak != "none":
            blocks.append(_notion_bullet(f"   ⚠️ Weak topics: {weak}"))

    blocks.append(_notion_divider())

    # ── daily sessions ──
    blocks.append(_notion_heading("📆 7-Day Study Schedule", level=2))

    for day_data in plan.get("days", []):
        d_str    = day_data.get("date", "")
        day_name = day_data.get("day_name", "")
        sessions = day_data.get("sessions", [])

        try:
            d        = date.fromisoformat(d_str)
            is_today = (d == today)
            date_disp = d.strftime("%d %B")
        except Exception:
            is_today  = False
            date_disp = d_str

        day_label = f"{'📍 ' if is_today else ''}{day_name} — {date_disp}"
        blocks.append(_notion_heading(day_label, level=3))

        if not sessions:
            blocks.append(_notion_paragraph("No sessions planned."))
            continue

        for s in sessions:
            stype   = s.get("type", "study")
            subject = s.get("subject", "")
            topic   = s.get("topic", "")
            t       = s.get("time", "")
            dur     = s.get("duration", 45)

            emoji_map = {
                "study":    "📖",
                "revision": "🔁",
                "practice": "✏️",
                "rest":     "☕",
            }
            emoji = emoji_map.get(stype, "📖")
            label = f"{emoji} {t} · {subject} — {topic} ({dur} min)"

            blocks.append(_notion_todo(label, checked=False))

        blocks.append(_notion_paragraph(""))  # spacer

    # ── tips ──
    blocks.append(_notion_divider())
    blocks.append(_notion_callout(
        "Say show my study plan to FRIDAY anytime to reopen this. Say update my study plan to refresh with new exam dates.",
        emoji="🤖",
        color="gray_background"
    ))

    # Notion allows max 100 blocks per request — split if needed
    page_id = _create_notion_page(title, NOTION_PAGE_ID, blocks[:100])

    if page_id and len(blocks) > 100:
        # append remaining blocks in chunks of 100
        for i in range(100, len(blocks), 100):
            _append_blocks(page_id, blocks[i:i+100])

    if page_id:
        notion_url = f"https://notion.so/{page_id.replace('-', '')}"
        print(f"[NOTION] Plan published: {notion_url}")
    else:
        print("[NOTION] Failed to publish plan.")

def open_planner_browser(plan, exams):
    """Render a beautiful visual study planner in the browser."""

    today = date.today()

    # ── exam countdown cards ──
    exam_cards = ""
    sorted_exams = sorted(exams, key=lambda e: days_until(e.get("date", "")))
    for e in sorted_exams:
        days = days_until(e.get("date", ""))
        date_str = e.get("date", "")
        date_label = date.fromisoformat(date_str).strftime("%d %B") if date_str else "TBD"
        urgency_color = "#ff7e7e" if days <= 3 else "#ffb07e" if days <= 7 else "#7eb8ff"
        exam_cards += f"""
        <div class="exam-card">
          <div class="exam-subject">{e['subject'].title()}</div>
          <div class="exam-date" style="color:{urgency_color}">{date_label}</div>
          <div class="exam-days" style="color:{urgency_color}">{days} days</div>
          <div class="exam-weak">⚠ {e.get('weak_topics','none')}</div>
        </div>"""

    # ── strategy summary ──
    summary = plan.get("summary", "")

    # ── day columns ──
    days_html = ""
    for day_data in plan.get("days", []):
        date_str  = day_data.get("date", "")
        day_name  = day_data.get("day_name", "")
        sessions  = day_data.get("sessions", [])

        try:
            d         = date.fromisoformat(date_str)
            is_today  = (d == today)
            date_disp = d.strftime("%d %b")
        except Exception:
            is_today  = False
            date_disp = date_str

        sessions_html = ""
        for s in sessions:
            stype  = s.get("type", "study")
            color  = SESSION_TYPE_COLORS.get(stype, "#7eb8ff")
            dur    = s.get("duration", 45)
            sessions_html += f"""
            <div class="session-card" style="border-left-color:{color}">
              <div class="session-time">{s.get('time','')}</div>
              <div class="session-subject" style="color:{color}">{s.get('subject','')}</div>
              <div class="session-topic">{s.get('topic','')}</div>
              <div class="session-dur">{dur} min · {stype}</div>
            </div>"""

        today_class = "day-col today-col" if is_today else "day-col"
        today_badge = '<span class="today-badge">TODAY</span>' if is_today else ""

        days_html += f"""
        <div class="{today_class}">
          <div class="day-header">
            {today_badge}
            <div class="day-name">{day_name}</div>
            <div class="day-date">{date_disp}</div>
          </div>
          <div class="day-sessions">{sessions_html}</div>
        </div>"""

    # ── legend ──
    legend_html = "".join([
        f'<span class="legend-item"><span class="legend-dot" style="background:{c}"></span>{t.title()}</span>'
        for t, c in SESSION_TYPE_COLORS.items()
    ])

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>FRIDAY Study Planner</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', sans-serif;
      background: #0a0a14;
      color: #e0e0ff;
      min-height: 100vh;
      padding: 30px;
    }}
    .header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 25px;
      padding-bottom: 15px;
      border-bottom: 1px solid #2a2a4e;
    }}
    .header h1 {{ color: #7eb8ff; font-size: 24px; }}
    .tag {{
      background: #2a2a4e;
      color: #7eb8ff;
      padding: 4px 14px;
      border-radius: 20px;
      font-size: 12px;
      letter-spacing: 1px;
    }}
    .summary-box {{
      background: #13131f;
      border: 1px solid #2a2a4e;
      border-left: 4px solid #7eb8ff;
      border-radius: 8px;
      padding: 15px 20px;
      margin-bottom: 25px;
      font-size: 14px;
      color: #c0c0e0;
      line-height: 1.7;
    }}
    .exams-row {{
      display: flex;
      gap: 15px;
      margin-bottom: 25px;
      flex-wrap: wrap;
    }}
    .exam-card {{
      background: #13131f;
      border: 1px solid #2a2a4e;
      border-radius: 10px;
      padding: 15px 18px;
      min-width: 140px;
      flex: 1;
    }}
    .exam-subject {{
      font-size: 15px;
      font-weight: bold;
      color: #e0e0ff;
      margin-bottom: 6px;
    }}
    .exam-date {{ font-size: 13px; margin-bottom: 2px; }}
    .exam-days {{ font-size: 22px; font-weight: bold; margin-bottom: 6px; }}
    .exam-weak {{
      font-size: 11px;
      color: #888;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .legend {{
      display: flex;
      gap: 20px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: #888;
    }}
    .legend-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }}
    .planner-grid {{
      display: flex;
      gap: 12px;
      overflow-x: auto;
      padding-bottom: 10px;
    }}
    .day-col {{
      flex: 0 0 180px;
      background: #13131f;
      border: 1px solid #2a2a4e;
      border-radius: 10px;
      overflow: hidden;
    }}
    .today-col {{
      border-color: #7eb8ff;
      box-shadow: 0 0 15px #7eb8ff22;
    }}
    .day-header {{
      background: #1a1a2e;
      padding: 12px 14px;
      border-bottom: 1px solid #2a2a4e;
      position: relative;
    }}
    .today-badge {{
      display: inline-block;
      background: #7eb8ff;
      color: #0a0a14;
      font-size: 9px;
      font-weight: bold;
      padding: 2px 7px;
      border-radius: 10px;
      margin-bottom: 4px;
      letter-spacing: 1px;
    }}
    .day-name {{ font-size: 14px; font-weight: bold; color: #e0e0ff; }}
    .day-date {{ font-size: 12px; color: #888; margin-top: 2px; }}
    .day-sessions {{ padding: 10px; }}
    .session-card {{
      background: #0f0f1a;
      border-left: 3px solid #7eb8ff;
      border-radius: 5px;
      padding: 10px 12px;
      margin-bottom: 8px;
    }}
    .session-time {{ font-size: 11px; color: #666; margin-bottom: 2px; }}
    .session-subject {{ font-size: 13px; font-weight: bold; margin-bottom: 2px; }}
    .session-topic {{ font-size: 12px; color: #c0c0e0; margin-bottom: 4px; line-height: 1.4; }}
    .session-dur {{ font-size: 11px; color: #555; }}
    .footer {{
      margin-top: 25px;
      text-align: center;
      font-size: 12px;
      color: #444;
    }}
  </style>
</head>
<body>
  <div class="header">
    <h1>📚 FRIDAY Study Planner</h1>
    <span class="tag">CBSE Grade 11 · {today.strftime('%d %B %Y')}</span>
  </div>

  <div class="summary-box">💡 {summary}</div>

  <div class="exams-row">{exam_cards}</div>

  <div class="legend">{legend_html}</div>

  <div class="planner-grid">{days_html}</div>

  <div class="footer">Generated by FRIDAY · Say "update my study plan" to refresh</div>
</body>
</html>"""

    filename = os.path.join(OUTPUT_DIR, "study_planner.html")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    webbrowser.open("file:///" + filename.replace("\\", "/"))
    print(f"[PLANNER] Opened: {filename}")

# ================= 🎯 VOICE COMMANDS =================

PLANNER_TRIGGERS = [
    "study plan", "show my plan", "what should i study",
    "study schedule", "show schedule", "update my study plan",
    "regenerate plan", "my exams", "exam schedule",
    "what do i study today", "study today"
]

def is_planner_command(command):
    cmd = command.lower()
    return any(t in cmd for t in PLANNER_TRIGGERS)

def handle(command):
    cmd = command.lower()

    if any(w in cmd for w in ["update", "change", "edit", "add exam", "new exam"]):
        speak("Sure. Let me update your exam details.")
        # reset last_asked to force re-interview
        planner = load_planner()
        planner["last_asked"] = None
        save_planner(planner)
        run_startup_interview()
        return True

    if any(w in cmd for w in ["show", "open", "display", "what should", "today"]):
        planner = load_planner()
        if planner.get("daily_plan"):
            speak("Opening your study plan.")
            open_planner_browser(planner["daily_plan"], planner.get("exams", []))
        else:
            speak("I do not have a plan yet. Let me create one.")
            generate_plan()
        return True

    if any(w in cmd for w in ["regenerate", "new plan", "redo", "remake"]):
        speak("Regenerating your study plan.")
        generate_plan()
        return True

    # default — show plan
    planner = load_planner()
    if planner.get("daily_plan"):
        open_planner_browser(planner["daily_plan"], planner.get("exams", []))
        speak("Study plan is open in your browser.")
    else:
        generate_plan()
    return True