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

    # sanitize anything that breaks edge_tts
    text = str(text).replace("'", " ").replace('"', " ")

    print("FRIDAY:", text)

    audio_file = f"voice_{uuid.uuid4().hex}.mp3"

    try:

        asyncio.run(_speak_async(text, audio_file))

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