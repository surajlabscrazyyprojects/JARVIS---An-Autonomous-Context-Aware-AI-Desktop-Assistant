from __future__ import annotations

import sys
from pathlib import Path

import requests


# ============================================================
# PUT YOUR VALUES HERE
# ============================================================

API_KEY = "PASTE_YOUR_FISH_API_KEY_HERE"

# Put the exact Fish voice/model ID here.
# Example:
VOICE_ID = "14129c3e320149449d6bada6862f7338"

# Current free model announced by Fish:
MODEL = "s2.1-pro-free"

TEXT = (
    "Hey, this is JARVIS. "
    "I'm testing my voice right now. "
    "Let's see how natural this sounds."
)

OUTPUT = Path("fish_test_output.mp3")


# ============================================================
# VALIDATION
# ============================================================

if API_KEY == "PASTE_YOUR_FISH_API_KEY_HERE":
    print("ERROR: Paste your Fish API key into API_KEY.")
    sys.exit(1)

if VOICE_ID == "PASTE_YOUR_VOICE_ID_HERE":
    print("ERROR: Paste your Fish voice/model ID into VOICE_ID.")
    sys.exit(1)


# ============================================================
# REQUEST
# ============================================================

url = "https://api.fish.audio/v1/tts"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "model": MODEL,
}

payload = {
    "text": TEXT,
    "reference_id": VOICE_ID,
    "format": "mp3",
    "prosody": {
        "speed": 1.0,
        "volume": 0,
        "normalize_loudness": True,
    },
    "normalize": True,
    "latency": "normal",
}


print("Sending request to Fish Audio...")
print(f"Model: {MODEL}")
print(f"Voice ID: {VOICE_ID}")

try:
    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=60,
    )

except requests.RequestException as exc:
    print("\nNETWORK ERROR")
    print(exc)
    sys.exit(1)


# ============================================================
# ERROR HANDLING
# ============================================================

if response.status_code != 200:
    print("\nFISH AUDIO REQUEST FAILED")
    print(f"HTTP status: {response.status_code}")
    print("Response:")
    print(response.text)
    sys.exit(1)


# ============================================================
# SAVE AUDIO
# ============================================================

if not response.content:
    print("\nERROR: Fish returned an empty audio response.")
    sys.exit(1)

OUTPUT.write_bytes(response.content)

print("\nSUCCESS")
print(f"Audio saved to: {OUTPUT.resolve()}")
print(f"Bytes received: {len(response.content):,}")


# ============================================================
# WINDOWS PLAYBACK
# ============================================================

try:
    import os
    os.startfile(str(OUTPUT.resolve()))
    print("Opening audio...")
except Exception as exc:
    print(f"Audio was generated, but automatic playback failed: {exc}")