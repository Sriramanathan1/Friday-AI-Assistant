"""
find_threshold.py — FRIDAY Mic Threshold Calibrator
Run this script, follow the prompts, and it will tell you
the exact energy_threshold value to use in main.py
"""

import speech_recognition as sr
import time

r = sr.Recognizer()

print("=" * 50)
print("  FRIDAY Mic Threshold Calibrator")
print("=" * 50)

# ── Step 1: Measure silence / room noise ──
print("\nStep 1: Stay SILENT for 5 seconds (measuring background noise)...")
time.sleep(2)

silence_levels = []
with sr.Microphone() as source:
    r.adjust_for_ambient_noise(source, duration=1)
    start = time.time()
    while time.time() - start < 5:
        try:
            audio = r.listen(source, timeout=1, phrase_time_limit=1)
            silence_levels.append(r.energy_threshold)
        except:
            silence_levels.append(r.energy_threshold)

avg_silence = sum(silence_levels) / len(silence_levels)
print(f"  Background noise level : {avg_silence:.0f}")

# ── Step 2: Measure AI speaker output ──
print("\nStep 2: Play something on your speakers at normal volume for 5 seconds.")
print("        (Play a YouTube video, music, anything — simulate AI talking)")
input("        Press Enter when audio is playing...")

speaker_levels = []
with sr.Microphone() as source:
    start = time.time()
    while time.time() - start < 5:
        try:
            audio = r.listen(source, timeout=1, phrase_time_limit=1)
            speaker_levels.append(r.energy_threshold)
        except:
            speaker_levels.append(r.energy_threshold)

avg_speaker = sum(speaker_levels) / len(speaker_levels)
print(f"  Speaker/AI audio level : {avg_speaker:.0f}")

# ── Step 3: Measure your voice ──
print("\nStep 3: SPEAK naturally for 5 seconds.")
print("        Say something like: 'Hey Friday open chrome and search YouTube'")
input("        Press Enter then start speaking...")

voice_levels = []
with sr.Microphone() as source:
    start = time.time()
    while time.time() - start < 5:
        try:
            audio = r.listen(source, timeout=1, phrase_time_limit=1)
            voice_levels.append(r.energy_threshold)
        except:
            voice_levels.append(r.energy_threshold)

avg_voice = sum(voice_levels) / len(voice_levels)
print(f"  Your voice level       : {avg_voice:.0f}")

# ── Calculate ideal threshold ──
# Midpoint between speaker output and your voice, biased toward speaker
# to give a comfortable margin
margin    = (avg_voice - avg_speaker) * 0.6
threshold = int(avg_speaker + margin)

print("\n" + "=" * 50)
print("  RESULTS")
print("=" * 50)
print(f"  Background noise : {avg_silence:.0f}")
print(f"  AI speaker level : {avg_speaker:.0f}")
print(f"  Your voice level : {avg_voice:.0f}")
print(f"\n  ✅ Recommended threshold : {threshold}")
print("\n  Set this in main.py:")
print(f"  r.energy_threshold = {threshold}")

if avg_voice < avg_speaker:
    print("\n  ⚠️  WARNING: Your voice is quieter than the speaker output.")
    print("     Move your mic closer to your mouth, or lower your speaker volume.")
elif avg_voice - avg_speaker < 500:
    print("\n  ⚠️  WARNING: Small gap between speaker and voice levels.")
    print("     Consider lowering speaker volume slightly for best results.")
else:
    print("\n  ✅ Good gap between speaker and voice — threshold should work well.")

print("=" * 50)