# ==================VOICE====================
import edge_tts
import asyncio
import pygame
import os
import uuid
import time
import aiofiles

VOICE = "en-GB-RyanNeural"


async def _speak_async(text, audio_file):

    communicate = edge_tts.Communicate(text=text, voice=VOICE)

    async for chunk in communicate.stream():

        if chunk["type"] == "audio":

            async with aiofiles.open(audio_file, "ab") as f:
                await f.write(chunk["data"])


def speak(text):

    text = str(text)
    print("FRIDAY:", text)   # log the real, unmangled text

    # Sanitize ONLY the copy sent to TTS — apostrophes/quotes can trip up
    # edge_tts in some cases. Stripping them from `text` itself (as before)
    # also corrupted anything printed to the terminal and any code/HTML
    # content being spoken, e.g. <html lang= en > instead of lang="en".
    tts_text = text.replace("'", " ").replace('"', " ")

    audio_file = f"voice_{uuid.uuid4().hex}.mp3"

    try:

        asyncio.run(_speak_async(tts_text, audio_file))

        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.music.unload()

        if os.path.exists(audio_file):
            os.remove(audio_file)

    except Exception as e:

        import traceback
        print("Voice error:", e)
        traceback.print_exc()