"""
notes_summarizer.py — FRIDAY Notes Summarizer

Triggered by: "make notes from this PDF", "summarize my notes",
              "create flashcards", "generate bullet notes", etc.

Flow:
  1. Find the PDF (most recent in D:/Documents or D:/Downloads)
     OR ask FRIDAY to listen for a specific file name/location
  2. Read full text with pypdf (page-by-page, chunked for long docs)
  3. Send to Groq llama-3.3-70b for structured summarization
  4. Save output as a clean, well-formatted PDF using reportlab
  5. Open the saved PDF + speak confirmation
"""

import os
import re
import time
import textwrap
from datetime import datetime
from pathlib import Path

from groq import Groq
from voice import speak
from config import GROQ_API_KEY as _CONFIG_GROQ_KEY

# ── PDF reading ──
try:
    from pypdf import PdfReader
    PYPDF_OK = True
except ImportError:
    PYPDF_OK = False
    print("[NOTES] pypdf not installed — run: pip install pypdf")

# ── PDF writing ──
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer,
        HRFlowable, PageBreak, ListFlowable, ListItem,
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False
    print("[NOTES] reportlab not installed — run: pip install reportlab")

# ================= ⚙️ CONFIG =================

GROQ_API_KEY    = _CONFIG_GROQ_KEY or "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"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"

# Where to look for PDFs
SEARCH_PATHS = [
    "D:/Documents",
    "D:/Downloads",
    "D:/Desktop",
]

# Where to save the output notes PDFs
NOTES_OUTPUT_DIR = "D:/Documents/FRIDAY Notes"

# Max characters sent to Groq per chunk (stays within token limits)
CHUNK_SIZE = 6000

try:
    _groq = Groq(api_key=GROQ_API_KEY)
    print("[NOTES] Groq client ready.")
except Exception as e:
    _groq = None
    print(f"[NOTES] Groq init failed: {e}")

# ================= 🔍 COMMAND DETECTION =================

_NOTES_TRIGGERS = [
    "make notes", "create notes", "generate notes", "take notes",
    "summarize", "summarise",
    "create flashcards", "make flashcards", "generate flashcards",
    "bullet notes", "bullet point", "condense",
    "make study notes", "study notes",
    "notes from", "notes of",
]

_PODCAST_EXCLUSIONS = ["podcast", "audio", "read to me", "listen"]


def is_notes_command(command: str) -> bool:
    cmd = command.lower().strip()
    if any(ex in cmd for ex in _PODCAST_EXCLUSIONS):
        return False
    return any(t in cmd for t in _NOTES_TRIGGERS)


def _wants_flashcards(command: str) -> bool:
    cmd = command.lower()
    return "flashcard" in cmd or "flash card" in cmd or "card" in cmd


# ================= 📂 FILE FINDER =================

def _find_recent_pdf(hint: str = "") -> str | None:
    """
    Finds the most relevant PDF in SEARCH_PATHS.
    If hint is given (e.g. 'physics notes'), scores files by keyword match.
    Otherwise returns the most recently modified PDF.
    """
    hint_words = set(hint.lower().split()) - {"the", "a", "an", "my", "this", "that", "pdf", "file", "document"}
    candidates = []

    for base in SEARCH_PATHS:
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            # skip hidden / system folders
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if not f.lower().endswith(".pdf"):
                    continue
                full = os.path.join(root, f)
                try:
                    mtime = os.path.getmtime(full)
                except OSError:
                    continue

                score = mtime  # base score = recency
                if hint_words:
                    name_words = set(os.path.splitext(f)[0].lower().replace("_", " ").replace("-", " ").split())
                    overlap = len(hint_words & name_words)
                    score += overlap * 1_000_000  # keyword match beats recency

                candidates.append((score, full, f))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    _, path, name = candidates[0]
    print(f"[NOTES] Selected file: {name} ({path})")
    return path


# ================= 📖 PDF READER =================

def _read_pdf(path: str) -> str:
    """Extract full text from a PDF, page by page."""
    if not PYPDF_OK:
        return ""
    try:
        reader = PdfReader(path)
        pages_text = []
        for i, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(f"[Page {i+1}]\n{txt.strip()}")
        full = "\n\n".join(pages_text)
        print(f"[NOTES] Read {len(reader.pages)} pages, {len(full)} chars")
        return full
    except Exception as e:
        print(f"[NOTES] PDF read error: {e}")
        return ""


# ================= 🤖 GROQ SUMMARIZER =================

def _call_groq(prompt: str) -> str:
    if not _groq:
        return ""
    try:
        t0 = time.time()
        resp = _groq.chat.completions.create(
            model=GROQ_TEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
        )
        result = resp.choices[0].message.content.strip()
        print(f"[NOTES GROQ] Response in {int(time.time()-t0)}s | {len(result)} chars")
        return result
    except Exception as e:
        print(f"[NOTES GROQ] Error: {e}")
        return ""


def _summarize_chunk(chunk: str, chunk_num: int, total_chunks: int, source_name: str, want_flashcards: bool) -> dict:
    """Send one chunk to Groq, get structured JSON back."""

    style = "flashcards" if want_flashcards else "bullet notes"

    prompt = f"""You are a CBSE Grade 11 study notes assistant.
Summarize the following content extracted from "{source_name}" (chunk {chunk_num}/{total_chunks}).

Output STRICT JSON only. No markdown fences, no preamble. Format:
{{
  "title": "short section title (max 8 words)",
  "key_points": ["point 1", "point 2", ...],
  "important_terms": [{{"term": "...", "definition": "..."}}],
  "flashcards": [{{"question": "...", "answer": "..."}}],
  "quick_summary": "2-3 sentence summary of this section"
}}

Rules:
- key_points: 5-10 concise bullet points. Each starts with a verb or noun, max 20 words.
- important_terms: up to 8 key terms with clear one-line definitions.
- flashcards: 5 Q&A pairs good for revision. Questions should test understanding, not just recall.
- quick_summary: plain English, no LaTeX.
- For math/physics: write equations as plain text e.g. F = ma, not LaTeX dollar signs.
- Focus on what matters for CBSE exams.

Content:
{chunk}
"""
    raw = _call_groq(prompt)
    if not raw:
        return {}

    # strip markdown fences if model added them anyway
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    raw = re.sub(r"\n?```$", "", raw.strip())

    try:
        return __import__("json").loads(raw)
    except Exception as e:
        print(f"[NOTES] JSON parse error on chunk {chunk_num}: {e}")
        # return at least a fallback
        return {"title": f"Section {chunk_num}", "quick_summary": raw[:500], "key_points": [], "important_terms": [], "flashcards": []}


def _generate_overview(all_sections: list, source_name: str) -> str:
    """Ask Groq for a one-page overview after all chunks are processed."""
    titles = [s.get("title", "") for s in all_sections if s.get("title")]
    summaries = [s.get("quick_summary", "") for s in all_sections if s.get("quick_summary")]
    combined = "\n".join(f"- {t}: {s}" for t, s in zip(titles, summaries))

    prompt = f"""Write a concise overall summary (4-6 sentences) of "{source_name}" based on these section summaries:

{combined}

Write in plain English, suitable for a CBSE Grade 11 student. No bullet points, no LaTeX. Just clear flowing text."""
    return _call_groq(prompt)


# ================= 📄 PDF WRITER =================

# Colour palette
_DARK_BG    = colors.HexColor("#1a1a2e")
_ACCENT     = colors.HexColor("#e94560")
_HEADING    = colors.HexColor("#0f3460")
_CARD_BG    = colors.HexColor("#16213e")
_BODY_TEXT  = colors.HexColor("#2c2c2c")
_WHITE      = colors.white
_LIGHT_GRAY = colors.HexColor("#f5f5f5")


def _build_styles():
    base = getSampleStyleSheet()

    styles = {
        "title": ParagraphStyle(
            "NTitle",
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=_DARK_BG,
            spaceAfter=6,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "NSubtitle",
            fontName="Helvetica",
            fontSize=11,
            textColor=colors.HexColor("#555555"),
            spaceAfter=18,
            alignment=TA_CENTER,
        ),
        "section_heading": ParagraphStyle(
            "NSectionHeading",
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=_WHITE,
            backColor=_HEADING,
            spaceBefore=14,
            spaceAfter=6,
            leftIndent=6,
            rightIndent=6,
            borderPadding=(4, 6, 4, 6),
        ),
        "overview_heading": ParagraphStyle(
            "NOverviewHeading",
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=_ACCENT,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "NBody",
            fontName="Helvetica",
            fontSize=10,
            textColor=_BODY_TEXT,
            spaceAfter=4,
            leading=15,
        ),
        "bullet": ParagraphStyle(
            "NBullet",
            fontName="Helvetica",
            fontSize=10,
            textColor=_BODY_TEXT,
            spaceAfter=3,
            leftIndent=14,
            leading=14,
        ),
        "term_name": ParagraphStyle(
            "NTermName",
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=_HEADING,
            spaceAfter=1,
        ),
        "term_def": ParagraphStyle(
            "NTermDef",
            fontName="Helvetica",
            fontSize=10,
            textColor=_BODY_TEXT,
            spaceAfter=5,
            leftIndent=10,
        ),
        "card_q": ParagraphStyle(
            "NCardQ",
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=_WHITE,
            backColor=_HEADING,
            spaceAfter=2,
            borderPadding=(3, 5, 3, 5),
            leading=14,
        ),
        "card_a": ParagraphStyle(
            "NCardA",
            fontName="Helvetica",
            fontSize=10,
            textColor=_BODY_TEXT,
            backColor=_LIGHT_GRAY,
            spaceAfter=8,
            borderPadding=(3, 5, 3, 5),
            leading=14,
        ),
        "small": ParagraphStyle(
            "NSmall",
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=colors.HexColor("#888888"),
            spaceAfter=2,
        ),
    }
    return styles


def _safe(text: str) -> str:
    """Escape special ReportLab XML characters."""
    return (text or "")                 \
        .replace("&", "&amp;")          \
        .replace("<", "&lt;")           \
        .replace(">", "&gt;")           \
        .replace('"', "&quot;")         \
        .replace("'", "&#39;")


def _write_pdf(
    sections: list,
    overview: str,
    source_name: str,
    want_flashcards: bool,
    out_path: str,
):
    """Build and save the notes PDF."""
    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=2*cm,
        rightMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
        title=f"Notes — {source_name}",
        author="FRIDAY AI Assistant",
    )

    S = _build_styles()
    story = []

    # ── Cover / title block ──
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(_safe(f"Notes: {source_name}"), S["title"]))
    story.append(Paragraph(
        _safe(f"Generated by FRIDAY  •  {datetime.now().strftime('%d %b %Y, %I:%M %p')}"),
        S["subtitle"]
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=_ACCENT, spaceAfter=10))

    # ── Overview ──
    if overview.strip():
        story.append(Paragraph("Overview", S["overview_heading"]))
        story.append(Paragraph(_safe(overview), S["body"]))
        story.append(Spacer(1, 0.4*cm))

    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey, spaceAfter=8))

    # ── Per-section content ──
    for sec in sections:
        if not sec:
            continue

        title   = sec.get("title", "Section")
        points  = sec.get("key_points", [])
        terms   = sec.get("important_terms", [])
        cards   = sec.get("flashcards", [])
        summary = sec.get("quick_summary", "")

        # Section heading
        story.append(Paragraph(_safe(title), S["section_heading"]))

        # Quick summary
        if summary:
            story.append(Paragraph(_safe(summary), S["body"]))
            story.append(Spacer(1, 0.2*cm))

        # Key points
        if points:
            story.append(Paragraph("Key Points", S["overview_heading"]))
            items = [
                ListItem(Paragraph(_safe(p), S["bullet"]), bulletColor=_ACCENT, leftIndent=20)
                for p in points if p.strip()
            ]
            if items:
                story.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=10))
            story.append(Spacer(1, 0.2*cm))

        # Important terms
        if terms:
            story.append(Paragraph("Important Terms", S["overview_heading"]))
            for t in terms:
                term = t.get("term", "")
                defn = t.get("definition", "")
                if term:
                    story.append(Paragraph(_safe(term), S["term_name"]))
                if defn:
                    story.append(Paragraph(_safe(defn), S["term_def"]))
            story.append(Spacer(1, 0.2*cm))

        # Flashcards (only if wanted, or always include in a separate section)
        if cards and want_flashcards:
            story.append(Paragraph("Flashcards", S["overview_heading"]))
            for i, card in enumerate(cards, 1):
                q = card.get("question", "")
                a = card.get("answer", "")
                if q:
                    story.append(Paragraph(_safe(f"Q{i}: {q}"), S["card_q"]))
                if a:
                    story.append(Paragraph(_safe(f"A: {a}"), S["card_a"]))
            story.append(Spacer(1, 0.2*cm))

        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=6))

    # ── Flashcard-only appendix (if not shown per section) ──
    if not want_flashcards:
        all_cards = [c for sec in sections for c in sec.get("flashcards", []) if sec]
        if all_cards:
            story.append(PageBreak())
            story.append(Paragraph("Flashcard Revision Appendix", S["title"]))
            story.append(HRFlowable(width="100%", thickness=2, color=_ACCENT, spaceAfter=10))
            for i, card in enumerate(all_cards, 1):
                q = card.get("question", "")
                a = card.get("answer", "")
                if q:
                    story.append(Paragraph(_safe(f"Q{i}: {q}"), S["card_q"]))
                if a:
                    story.append(Paragraph(_safe(f"A: {a}"), S["card_a"]))

    # ── Footer note ──
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        "Generated automatically by FRIDAY AI Assistant. Review before using for exams.",
        S["small"]
    ))

    doc.build(story)
    print(f"[NOTES] PDF saved: {out_path}")


# ================= 🎙️ LISTEN HELPER =================

def _listen_once(timeout: int = 8) -> str:
    """Listen for a short voice response."""
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.Microphone() as src:
            r.adjust_for_ambient_noise(src, duration=0.5)
            audio = r.listen(src, timeout=timeout, phrase_time_limit=10)
        return r.recognize_google(audio).lower().strip()
    except Exception:
        return ""


# ================= 🧠 MAIN HANDLER =================

def handle(command: str) -> bool:
    """
    Main entry point called from brain.py PLUGIN_MAP.
    """
    cmd = command.lower().strip()
    want_flashcards = _wants_flashcards(cmd)

    # ── Step 1: figure out which file to use ──
    # Check if user named a file in the command
    # e.g. "make notes from the physics PDF" → hint = "physics"
    hint = ""
    for kw in ["from the", "from my", "from this", "of my", "of the", "called", "named"]:
        if kw in cmd:
            after = cmd.split(kw, 1)[1].strip()
            # strip trailing filler
            after = re.sub(r"\b(pdf|file|document|doc|notes)\b", "", after).strip()
            if after:
                hint = after
            break

    speak("Looking for your PDF now.")
    file_path = _find_recent_pdf(hint)

    if not file_path:
        # Ask user to specify
        speak("I could not find a PDF. Which file should I use? Say the name or location.")
        response = _listen_once()
        if response:
            file_path = _find_recent_pdf(response)

    if not file_path:
        speak("Sorry, I could not find any PDF on your D drive. Please drop the file in Documents or Downloads and try again.")
        return True

    source_name = os.path.splitext(os.path.basename(file_path))[0]
    speak(f"Found {source_name}. Reading and summarizing now. This might take a minute.")

    # ── Step 2: read PDF ──
    if not PYPDF_OK:
        speak("The pypdf library is missing. Please run pip install pypdf and try again.")
        return True

    full_text = _read_pdf(file_path)
    if not full_text.strip():
        speak("The PDF appears to be scanned or image-based. I cannot extract text from it directly.")
        return True

    # ── Step 3: chunk and summarize ──
    chunks = [full_text[i:i+CHUNK_SIZE] for i in range(0, len(full_text), CHUNK_SIZE)]
    total  = len(chunks)
    print(f"[NOTES] Processing {total} chunk(s)")

    sections = []
    for i, chunk in enumerate(chunks, 1):
        speak(f"Processing section {i} of {total}.") if total > 1 else None
        sec = _summarize_chunk(chunk, i, total, source_name, want_flashcards)
        sections.append(sec)

    # ── Step 4: generate overview ──
    overview = _generate_overview(sections, source_name)

    # ── Step 5: write output PDF ──
    if not REPORTLAB_OK:
        speak("The reportlab library is missing. Please run pip install reportlab and try again.")
        return True

    os.makedirs(NOTES_OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    label     = "Flashcards" if want_flashcards else "Notes"
    out_name  = f"{source_name}_{label}_{timestamp}.pdf"
    out_path  = os.path.join(NOTES_OUTPUT_DIR, out_name)

    try:
        _write_pdf(sections, overview, source_name, want_flashcards, out_path)
    except Exception as e:
        print(f"[NOTES] PDF write error: {e}")
        speak("I ran into a problem saving the PDF. Check the terminal for details.")
        return True

    # ── Step 6: open the PDF ──
    try:
        os.startfile(out_path)   # Windows — opens with default PDF viewer
    except Exception:
        import subprocess
        subprocess.Popen(["start", out_path], shell=True)

    note_type = "flashcards" if want_flashcards else "notes"
    speak(f"Done. Your {note_type} for {source_name} have been saved to your Documents folder under FRIDAY Notes.")
    return True