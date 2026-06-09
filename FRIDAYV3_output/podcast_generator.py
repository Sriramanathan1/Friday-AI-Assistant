"""
podcast_generator.py — FRIDAY PDF-to-Podcast

Triggered by: "make a podcast from this PDF", "convert to podcast",
              "audio version of my notes", "read this to me as a podcast"

Flow:
  1. Find the PDF in D:/Documents or D:/Downloads
  2. Read full text with pypdf
  3. Send to Groq — generates a two-host podcast script (JSON array of dialogue lines)
  4. Render each line with edge_tts using two different neural voices
  5. Concatenate all audio segments into one MP3 using pydub
  6. Save to D:/Documents/FRIDAY Podcasts/
  7. Play it back immediately, then open the folder
"""

import os
import re
import json
import time
import asyncio
import tempfile
import subprocess
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
    print("[PODCAST] pypdf not installed — run: pip install pypdf")

# ── Audio merging ──
# Pure byte concatenation is used — no pydub or ffmpeg required.

# ── edge_tts ──
try:
    import edge_tts
    EDGETTS_OK = True
except ImportError:
    EDGETTS_OK = False
    print("[PODCAST] edge_tts not installed — run: pip install edge-tts")

# ================= ⚙️ CONFIG =================

GROQ_API_KEY    = _CONFIG_GROQ_KEY or "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"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"

SEARCH_PATHS = [
    "D:/Documents",
    "D:/Downloads",
    "D:/Desktop",
]

PODCAST_OUTPUT_DIR = "D:/Documents/FRIDAY Podcasts"

# Two distinct voices — Host 1 is the explainer, Host 2 is the curious student
HOST_1_VOICE = "en-GB-RyanNeural"      # British male — the "teacher" host
HOST_2_VOICE = "en-US-JennyNeural"     # American female — the "curious" host

HOST_1_NAME = "Ryan"
HOST_2_NAME = "Jenny"

# Silence gap between lines (milliseconds)
LINE_GAP_MS = 400

# Max characters of PDF text sent to Groq
CHUNK_SIZE = 7000

try:
    _groq = Groq(api_key=GROQ_API_KEY)
    print("[PODCAST] Groq client ready.")
except Exception as e:
    _groq = None
    print(f"[PODCAST] Groq init failed: {e}")

# ================= 🔍 COMMAND DETECTION =================

_PODCAST_TRIGGERS = [
    "podcast", "make a podcast", "create a podcast",
    "audio version", "read to me", "listen to my notes",
    "notebook lm", "audio podcast", "turn my notes into",
    "read this to me", "make audio",
]

def is_podcast_command(command: str) -> bool:
    cmd = command.lower().strip()
    return any(t in cmd for t in _PODCAST_TRIGGERS)

# ================= 📂 FILE FINDER =================

def _find_recent_pdf(hint: str = "") -> str | None:
    hint_words = set(hint.lower().split()) - {
        "the", "a", "an", "my", "this", "that", "pdf",
        "file", "document", "notes", "from"
    }
    candidates = []

    for base in SEARCH_PATHS:
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if not f.lower().endswith(".pdf"):
                    continue
                full = os.path.join(root, f)
                try:
                    mtime = os.path.getmtime(full)
                except OSError:
                    continue
                score = mtime
                if hint_words:
                    name_words = set(
                        os.path.splitext(f)[0].lower()
                        .replace("_", " ").replace("-", " ").split()
                    )
                    score += len(hint_words & name_words) * 1_000_000
                candidates.append((score, full, f))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, path, name = candidates[0]
    print(f"[PODCAST] Selected file: {name}")
    return path

# ================= 📖 PDF READER =================

def _read_pdf(path: str) -> str:
    if not PYPDF_OK:
        return ""
    try:
        reader = PdfReader(path)
        parts = []
        for i, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            if txt.strip():
                parts.append(txt.strip())
        full = "\n\n".join(parts)
        print(f"[PODCAST] Read {len(reader.pages)} pages, {len(full)} chars")
        return full
    except Exception as e:
        print(f"[PODCAST] PDF read error: {e}")
        return ""

# ================= 🎙️ SCRIPT GENERATOR =================

def _generate_script_for_chunk(
    chunk: str,
    source_name: str,
    chunk_num: int,
    total_chunks: int,
    is_first: bool,
    is_last: bool,
) -> list[dict]:
    """
    Generate podcast dialogue for one chunk of PDF content.
    is_first / is_last control intro and outro inclusion.
    """

    if is_first and is_last:
        structure_note = (
            f"Start with a natural intro where both hosts greet listeners and introduce the topic. "
            f"Cover everything in the material thoroughly. "
            f"End with {HOST_2_NAME} summarizing the key takeaways and both hosts signing off."
        )
    elif is_first:
        structure_note = (
            f"Start with a natural intro where both hosts greet listeners and introduce the topic. "
            f"Then cover the content below. Do NOT end the episode — more content follows."
        )
    elif is_last:
        structure_note = (
            f"Continue naturally from the previous section. Cover the remaining content. "
            f"End with {HOST_2_NAME} summarizing ALL the key takeaways from the full episode, "
            f"and both hosts signing off warmly."
        )
    else:
        structure_note = (
            f"Continue naturally from the previous section (this is part {chunk_num} of {total_chunks}). "
            f"Cover the content below thoroughly. Do NOT start an intro or end the episode."
        )

    prompt = f"""You are a podcast scriptwriter. Write a natural, engaging two-host educational podcast dialogue
based on the following study material from "{source_name}" (part {chunk_num} of {total_chunks}).

Hosts:
- {HOST_1_NAME}: the knowledgeable explainer. Clear, enthusiastic, gives detailed explanations with real-world examples.
- {HOST_2_NAME}: the curious student. Asks insightful questions, makes relatable comparisons, occasionally adds humor.

Structure:
{structure_note}

Rules:
- Write AS MANY exchanges as needed to cover the material properly. Do not cut short.
- Every important concept in the material must be discussed — do not skip anything.
- Each individual line should be natural spoken length (under 80 words). Do not cram multiple ideas into one line.
- Break complex explanations into multiple back-and-forth exchanges rather than one long monologue.
- Do NOT use bullet points, headers, or markdown inside the lines.
- Do NOT use LaTeX or math symbols. Write equations in plain English (e.g. "F equals m times a", "v squared equals u squared plus 2as").
- Make it feel like a real podcast — natural transitions, occasional humor, genuine curiosity, real-world analogies.
- No apostrophes anywhere (write "do not" not "don't", "it is" not "it's", "we are" not "we're").

Output STRICT JSON only — a flat list of objects. No markdown fences, no preamble, no trailing text:
[
  {{"speaker": "{HOST_1_NAME}", "line": "..."}},
  {{"speaker": "{HOST_2_NAME}", "line": "..."}},
  ...
]

Study material:
{chunk}
"""

    if not _groq:
        return []

    try:
        t0 = time.time()
        resp = _groq.chat.completions.create(
            model=GROQ_TEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8000,
            temperature=0.65,
        )
        raw = resp.choices[0].message.content.strip()
        print(f"[PODCAST] Chunk {chunk_num}/{total_chunks} script in {int(time.time()-t0)}s | {len(raw)} chars")
    except Exception as e:
        print(f"[PODCAST] Groq error on chunk {chunk_num}: {e}")
        return []

    # Strip markdown fences if model added them anyway
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    raw = re.sub(r"\n?```$", "", raw.strip())

    # Handle truncated JSON — if the model ran out of tokens mid-array,
    # salvage every complete object that was written
    try:
        return _parse_script_json(raw)
    except Exception as e:
        print(f"[PODCAST] JSON parse error on chunk {chunk_num}: {e}")
        return []


def _parse_script_json(raw: str) -> list[dict]:
    """
    Parse the script JSON, tolerating truncation.
    Extracts all complete {"speaker": ..., "line": ...} objects
    even if the outer array was cut off mid-way.
    """
    # First try clean parse
    try:
        items = json.loads(raw)
        cleaned = []
        for item in items:
            speaker = item.get("speaker", "").strip()
            line    = item.get("line", "").strip()
            if speaker in (HOST_1_NAME, HOST_2_NAME) and line:
                cleaned.append({"speaker": speaker, "line": line})
        return cleaned
    except json.JSONDecodeError:
        pass

    # Fallback: regex-extract all complete objects
    pattern = r'\{\s*"speaker"\s*:\s*"([^"]+)"\s*,\s*"line"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}'
    matches = re.findall(pattern, raw, re.DOTALL)
    cleaned = []
    for speaker, line in matches:
        speaker = speaker.strip()
        line    = line.replace('\\"', '"').replace("\\n", " ").strip()
        if speaker in (HOST_1_NAME, HOST_2_NAME) and line:
            cleaned.append({"speaker": speaker, "line": line})
    return cleaned


def _generate_script(full_text: str, source_name: str) -> list[dict]:
    """
    Split the full PDF text into chunks, generate a script for each,
    and return one continuous list of dialogue lines.
    """
    # Split into chunks — each chunk is a self-contained section
    chunks = [full_text[i:i+CHUNK_SIZE] for i in range(0, len(full_text), CHUNK_SIZE)]
    total  = len(chunks)
    print(f"[PODCAST] Generating script for {total} chunk(s) of content")

    all_lines = []
    for i, chunk in enumerate(chunks):
        chunk_num  = i + 1
        is_first   = (i == 0)
        is_last    = (i == total - 1)

        speak(f"Writing script section {chunk_num} of {total}.") if total > 1 else None

        lines = _generate_script_for_chunk(
            chunk, source_name, chunk_num, total, is_first, is_last
        )
        all_lines.extend(lines)
        print(f"[PODCAST] Running total: {len(all_lines)} lines after chunk {chunk_num}")

    print(f"[PODCAST] Final script: {len(all_lines)} total dialogue lines")
    return all_lines

# ================= 🔊 TTS RENDERER =================

def _render_line(text: str, voice: str, out_path: str):
    """
    Render one line to MP3 using edge_tts.
    Runs in a brand-new thread with its own event loop to avoid
    conflicts with any existing asyncio loop (pygame, etc.).
    Blocks until the file is fully written.
    """
    import threading

    success = threading.Event()
    error_holder = [None]

    def _worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_render_line_inner(text, voice, out_path))
            success.set()
        except Exception as e:
            error_holder[0] = e
        finally:
            loop.close()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=30)   # wait up to 30s per line

    if error_holder[0]:
        raise error_holder[0]
    if not success.is_set():
        raise TimeoutError(f"TTS timed out for: {text[:40]}")

async def _render_line_inner(text: str, voice: str, out_path: str):
    """Async core — streams edge_tts audio directly to file."""
    communicate = edge_tts.Communicate(text=text, voice=voice)
    audio_bytes = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes.extend(chunk["data"])
    # Write synchronously after streaming completes
    with open(out_path, "wb") as f:
        f.write(audio_bytes)


# MP3 silence frame at 128kbps (44100Hz stereo) — 400ms worth
# This is a valid minimal MP3 frame filled with silence bytes.
# Used for gaps between speakers without needing ffmpeg.
_SILENCE_FRAME = bytes([
    0xFF, 0xFB, 0x90, 0x00,   # MP3 frame header (MPEG1, Layer3, 128kbps, 44100Hz, stereo)
]) + bytes(413)               # frame data filled with zeros = silence


def _make_silence_bytes(duration_ms: int = 400) -> bytes:
    """
    Build raw MP3 silence of approximately duration_ms.
    Each MP3 frame at 44100Hz = ~26ms.
    No ffmpeg required — just raw valid MP3 frames.
    """
    frames_needed = max(1, duration_ms // 26)
    return _SILENCE_FRAME * frames_needed


def _merge_segments(segment_paths: list[str], output_path: str, gap_ms: int = LINE_GAP_MS):
    """
    Concatenate MP3 segment files with silence gaps — no ffmpeg, no pydub.
    MP3 is a stream format: valid frames from multiple files can be
    concatenated directly and most players handle it perfectly.
    """
    silence = _make_silence_bytes(gap_ms)
    written = 0

    with open(output_path, "wb") as out:
        for i, path in enumerate(segment_paths):
            if not os.path.exists(path):
                print(f"[PODCAST] Missing segment, skipping: {path}")
                continue
            try:
                with open(path, "rb") as seg:
                    data = seg.read()
                out.write(data)
                out.write(silence)
                written += 1
            except Exception as e:
                print(f"[PODCAST] Segment read error ({path}): {e}")

    print(f"[PODCAST] Merged {written}/{len(segment_paths)} segments → {output_path}")

# ================= 🎙️ LISTEN HELPER =================

def _listen_once(timeout: int = 8) -> str:
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
    """Entry point called from brain.py PLUGIN_MAP."""
    cmd = command.lower().strip()

    # Extract file hint from command
    hint = ""
    for kw in ["from the", "from my", "from this", "of my", "of the", "called", "named", "about"]:
        if kw in cmd:
            after = cmd.split(kw, 1)[1].strip()
            after = re.sub(r"\b(pdf|file|document|doc|notes|podcast|audio)\b", "", after).strip()
            if after:
                hint = after
            break

    # ── Step 1: find PDF ──
    speak("Looking for your PDF.")
    file_path = _find_recent_pdf(hint)

    if not file_path:
        speak("I could not find a PDF. Which file should I use? Say the name or subject.")
        response = _listen_once()
        if response:
            file_path = _find_recent_pdf(response)

    if not file_path:
        speak("Sorry, I could not find any PDF in your Documents or Downloads folder.")
        return True

    source_name = os.path.splitext(os.path.basename(file_path))[0]
    speak(f"Found {source_name}. Writing the podcast script now. Give me about 30 seconds.")

    # ── Step 2: read PDF ──
    if not PYPDF_OK:
        speak("The pypdf library is missing. Run pip install pypdf and try again.")
        return True

    full_text = _read_pdf(file_path)
    if not full_text.strip():
        speak("This PDF appears to be scanned. I cannot read the text from it.")
        return True

    # ── Step 3: generate script ──
    script = _generate_script(full_text, source_name)
    if not script:
        speak("I could not generate a podcast script. Check the terminal for details.")
        return True

    speak(f"Script ready. Rendering {len(script)} lines of audio. This will take about a minute.")

    # ── Step 4: render each line to a temp MP3 ──
    if not EDGETTS_OK:
        speak("edge-tts is not installed. Run pip install edge-tts aiofiles and try again.")
        return True

    tmp_dir = tempfile.mkdtemp(prefix="friday_podcast_")
    segment_paths = []

    for i, item in enumerate(script):
        speaker = item["speaker"]
        line    = item["line"]
        voice   = HOST_1_VOICE if speaker == HOST_1_NAME else HOST_2_VOICE
        seg_path = os.path.join(tmp_dir, f"seg_{i:03d}.mp3")

        try:
            _render_line(line, voice, seg_path)
            if not os.path.exists(seg_path) or os.path.getsize(seg_path) == 0:
                print(f"[PODCAST] Rendered file empty or missing for line {i+1}, skipping")
                continue
            segment_paths.append(seg_path)
            print(f"[PODCAST] Rendered line {i+1}/{len(script)}: {speaker} ({os.path.getsize(seg_path)} bytes)")
        except Exception as e:
            print(f"[PODCAST] Render error on line {i+1}: {e}")
            continue

    if not segment_paths:
        speak("Audio rendering failed. Check the terminal.")
        return True

    # ── Step 5: merge all segments ──
    os.makedirs(PODCAST_OUTPUT_DIR, exist_ok=True)
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name   = f"{source_name}_Podcast_{timestamp}.mp3"
    out_path   = os.path.join(PODCAST_OUTPUT_DIR, out_name)

    speak("Merging audio segments.")
    _merge_segments(segment_paths, out_path)

    # Clean up temp segments
    for p in segment_paths:
        try:
            os.remove(p)
        except Exception:
            pass
    try:
        os.rmdir(tmp_dir)
    except Exception:
        pass

    if not os.path.exists(out_path):
        speak("Something went wrong saving the podcast file.")
        return True

    # ── Step 6: play it ──
    speak(f"Podcast for {source_name} is ready. Playing now.")
    try:
        import pygame
        pygame.mixer.music.load(out_path)
        pygame.mixer.music.play()
        # Don't block — let it play in background
    except Exception:
        # Fallback: open with Windows media player
        os.startfile(out_path)

    # Open the folder so the user can find the file later
    try:
        subprocess.Popen(f'explorer "{PODCAST_OUTPUT_DIR}"')
    except Exception:
        pass

    speak(f"The MP3 has been saved to your Documents under FRIDAY Podcasts.")
    return True