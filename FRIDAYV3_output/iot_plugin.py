# ================================================================
#  iot_plugin.py — FRIDAY IoT / Alexa Integration
#
#  alexapy is unmaintained and broken on modern Python (3.13).
#  Instead, this talks HTTP to `alexa_bridge.js`, a tiny Node.js
#  server (in the project root) built on `alexa-remote2`, which
#  IS actively maintained and needs no AWS / Alexa Skill setup.
#
#  Start it once with:  node alexa_bridge.js
#  (see alexa_bridge.js header for the one-time login step)
# ================================================================

import os
import re
import requests
from difflib import SequenceMatcher
from dotenv import load_dotenv

from voice import speak

load_dotenv()

BRIDGE_URL = os.getenv("ALEXA_BRIDGE_URL", "http://localhost:3050")

# ── Device type alias map ─────────────────────────────────────────
DEVICE_ALIASES = {
    "light":           ["bulb", "light", "lamp", "led", "strip", "tube"],
    "lights":          ["bulb", "light", "lamp", "led", "strip", "tube"],
    "bulb":            ["bulb", "light", "lamp"],
    "lamp":            ["lamp", "light", "bulb"],
    "plug":            ["plug", "switch", "socket", "outlet"],
    "switch":          ["switch", "plug", "socket"],
    "fan":             ["fan", "ceiling fan", "exhaust"],
    "ac":              ["ac", "air conditioner", "aircon", "conditioner", "cooler"],
    "air conditioner": ["ac", "air conditioner", "aircon"],
    "tv":              ["tv", "television", "fire", "firetv"],
    "television":      ["tv", "television"],
}

# Words that describe *where* a device is, used to boost matches like
# "bedroom ac" -> "Master Bedroom AC"
LOCATION_WORDS = [
    "bedroom", "master", "guest", "living", "hall", "kitchen", "bathroom",
    "office", "study", "balcony", "dining", "kids", "garage", "hallway",
]


# ================================================================
#  BRIDGE COMMUNICATION
# ================================================================

_devices_cache = []


def _bridge_get(path, **params):
    try:
        r = requests.get(f"{BRIDGE_URL}{path}", params=params, timeout=10)
        if r.status_code != 200:
            raise Exception(r.json().get("error", f"HTTP {r.status_code}"))
        return r.json()
    except requests.exceptions.ConnectionError:
        raise Exception(
            "Alexa bridge isn't running. Start it with 'node alexa_bridge.js'."
        )


def _bridge_post(path, payload):
    try:
        r = requests.post(f"{BRIDGE_URL}{path}", json=payload, timeout=15)
        if r.status_code != 200:
            raise Exception(r.json().get("error", f"HTTP {r.status_code}"))
        return r.json()
    except requests.exceptions.ConnectionError:
        raise Exception(
            "Alexa bridge isn't running. Start it with 'node alexa_bridge.js'."
        )


def _get_devices(force_refresh=False) -> list:
    global _devices_cache
    if _devices_cache and not force_refresh:
        return _devices_cache

    data = _bridge_get("/devices", refresh="1" if force_refresh else "0")
    _devices_cache = data.get("devices", [])
    print(f"[IOT] {len(_devices_cache)} devices: "
          f"{[d.get('friendlyName') for d in _devices_cache]}")
    return _devices_cache


# ================================================================
#  DEVICE MATCHING
#  Handles cases like the user saying "bedroom AC" while the
#  device is actually registered as "Master Bedroom AC".
# ================================================================

def _similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _find_best_device(query: str, devices: list) -> dict | None:
    query_words = query.lower().split()

    # Expand type words (e.g. "ac" -> also matches "air conditioner")
    hint_keywords = []
    for word in query_words:
        if word in DEVICE_ALIASES:
            hint_keywords.extend(DEVICE_ALIASES[word])

    location_words = [w for w in query_words if w in LOCATION_WORDS]

    best, best_score = None, 0.0

    for device in devices:
        name = device.get("friendlyName", "").lower()
        score = 0.0

        # device-type hint match (ac/aircon/etc.)
        for hint in hint_keywords:
            if hint in name:
                score += 0.5
                break

        # any other significant query word found verbatim in the name
        for word in query_words:
            if len(word) > 2 and word in name:
                score += 0.25

        # location words count extra — this is what lets "bedroom ac"
        # match "Master Bedroom AC" even though the user never said
        # "master"
        for word in location_words:
            if word in name:
                score += 0.3

        # overall string similarity as a tiebreaker
        score += _similarity(query, name) * 0.15

        if score > best_score:
            best_score = score
            best = device

    if best_score >= 0.4:
        return best

    # pure similarity fallback
    if devices:
        best = max(devices, key=lambda d: _similarity(query, d.get("friendlyName", "")))
        if _similarity(query, best.get("friendlyName", "")) > 0.35:
            return best

    return None


# ================================================================
#  COMMAND PARSING (legacy — single combined command string)
# ================================================================

_PATTERNS = [
    (r"turn (on|off)\s+(?:the\s+)?(.+)",                          "toggle"),
    (r"switch (on|off)\s+(?:the\s+)?(.+)",                        "toggle"),
    (r"set brightness\s+(?:of\s+)?(.+?)\s+to\s+(\d+)",           "brightness"),
    (r"dim\s+(?:the\s+)?(.+?)\s+to\s+(\d+)",                     "brightness"),
    (r"dim\s+(?:the\s+)?(.+)",                                    "dim_default"),
    (r"set\s+(?:the\s+)?(.+?)\s+to\s+(\d+)\s*(?:degrees?|°)?",   "temperature"),
    (r"set\s+(?:the\s+)?(.+?)\s+volume\s+to\s+(\d+)",            "volume"),
    (r"(?:change|set)\s+(?:color of\s+)?(.+?)\s+(?:color )?to\s+([a-z\s]+)", "color"),
    (r"(?:status|state)\s+of\s+(?:the\s+)?(.+)",                  "status"),
]


def _parse_command(command: str) -> dict | None:
    cmd = command.lower().strip()
    cmd = re.sub(r"\b(please|hey|friday|can you|could you|i want to)\b", "", cmd).strip()

    for pattern, action in _PATTERNS:
        m = re.search(pattern, cmd)
        if not m:
            continue
        if action == "toggle":
            return {"action": f"turn_{m.group(1)}", "device_query": m.group(2).strip(), "value": None}
        elif action == "brightness":
            return {"action": "set_brightness", "device_query": m.group(1).strip(), "value": m.group(2)}
        elif action == "dim_default":
            return {"action": "set_brightness", "device_query": m.group(1).strip(), "value": "30"}
        elif action == "temperature":
            return {"action": "set_temperature", "device_query": m.group(1).strip(), "value": m.group(2)}
        elif action == "volume":
            return {"action": "set_volume", "device_query": m.group(1).strip(), "value": m.group(2)}
        elif action == "color":
            return {"action": "set_color", "device_query": m.group(1).strip(), "value": m.group(2).strip()}
        elif action == "status":
            return {"action": "status", "device_query": m.group(1).strip(), "value": None}
    return None


# ================================================================
#  ACTION PARSING (structured — action text WITHOUT the device,
#  used by the LLM tool-calling path via handle_structured())
# ================================================================

def _parse_action_text(action_text: str):
    """
    Parse a short natural-language action phrase (no device name in it),
    e.g. 'turn on', 'set brightness to 50', 'dim to 30', 'set to 24 degrees',
    'set volume to 30', 'set color to blue', 'status'.

    Returns (action, value) where value is a string or None,
    or (None, None) if not understood.
    """
    a = action_text.lower().strip()
    a = re.sub(r"\b(please|the device|it)\b", "", a).strip()

    # ── On / Off ──
    if re.search(r"\b(turn|switch|power)\s+on\b", a) or a in ("on", "power on"):
        return "turn_on", None
    if re.search(r"\b(turn|switch|power)\s+off\b", a) or a in ("off", "power off"):
        return "turn_off", None

    # ── Volume ──
    m = re.search(r"volume.*?(\d+)", a)
    if m:
        return "set_volume", m.group(1)

    # ── Brightness / Dim ──
    m = re.search(r"brightness.*?(\d+)", a)
    if m:
        return "set_brightness", m.group(1)
    if re.search(r"\bdim\b", a):
        num = re.search(r"(\d+)", a)
        return "set_brightness", num.group(1) if num else "30"

    # ── Color ──
    m = re.search(r"colou?r.*?to\s+([a-z\s]+)", a)
    if m:
        return "set_color", m.group(1).strip()
    m = re.search(r"^(?:set|change|make)\s+(?:it\s+)?([a-z]+)$", a)
    if m and m.group(1) not in ("on", "off"):
        return "set_color", m.group(1).strip()

    # ── Temperature (AC set point) ──
    if "temperature" in a or "degree" in a or "°" in a:
        m = re.search(r"(\d+)", a)
        if m:
            return "set_temperature", m.group(1)
    m = re.match(r"^(?:set\s+)?to\s+(\d+)$", a)
    if m:
        return "set_temperature", m.group(1)

    # ── Status ──
    if "status" in a or "state" in a:
        return "status", None

    return None, None


# ================================================================
#  SHARED EXECUTION — match device, run action, speak result
# ================================================================

def _execute_action(device_query: str, action: str, value) -> bool:
    if action == "status":
        speak("Sorry, I can't check device status through Alexa right now.")
        return True

    try:
        devices = _get_devices()
    except Exception as e:
        speak(f"Couldn't connect to Alexa. {e}")
        return True

    if not devices:
        speak("No Alexa devices found. Say 'refresh devices' to try again.")
        return True

    device = _find_best_device(device_query, devices)
    if not device:
        speak(f"I couldn't find a device matching {device_query}.")
        return True

    device_name = device.get("friendlyName", "device")
    entity_id = device.get("entityId", "")
    print(f"[IOT] '{device_query}' -> '{device_name}' | {action} | value={value}")
    speak("On it.")

    try:
        _bridge_post("/command", {
            "entityId": entity_id,
            "action": action,
            "value": value,
        })
        val_str = f" to {value}" if value else ""
        speak(f"Done. {device_name} {action.replace('_', ' ')}{val_str}.")
    except Exception as e:
        print(f"[IOT] Error: {e}")
        speak(f"Sorry, I couldn't control {device_name}. {e}")

    return True


def _handle_list_or_refresh(command: str) -> bool | None:
    """Handle device-listing/refresh phrases. Returns True if handled, else None."""
    if "refresh devices" in command or "update devices" in command:
        speak("Refreshing device list...")
        try:
            devices = _get_devices(force_refresh=True)
        except Exception as e:
            speak(f"Couldn't reach Alexa. {e}")
            return True
        speak(f"Found {len(devices)} devices: "
              f"{', '.join(d.get('friendlyName', '?') for d in devices)}")
        return True

    if "list devices" in command or "what devices" in command or "show devices" in command:
        try:
            devices = _get_devices()
        except Exception as e:
            speak(f"Couldn't reach Alexa. {e}")
            return True
        if not devices:
            speak("No devices found.")
            return True
        speak(f"You have {len(devices)} devices: "
              f"{', '.join(d.get('friendlyName', '?') for d in devices)}")
        return True

    return None


# ================================================================
#  STRUCTURED HANDLER — used by tool_executor.iot_control()
#  device/action come pre-separated by the LLM (tool-calling),
#  so no regex over a combined string is needed.
# ================================================================

def handle_structured(device: str, action_text: str) -> bool:
    device = (device or "").strip()
    action_text = (action_text or "").strip()
    combined = f"{action_text} {device}".lower()

    listed = _handle_list_or_refresh(combined)
    if listed is not None:
        return listed

    action, value = _parse_action_text(action_text)
    if action is None:
        speak(f"I couldn't understand the action '{action_text}'.")
        return False

    if not device:
        speak("Which device did you mean?")
        return False

    return _execute_action(device, action, value)


# ================================================================
#  MAIN HANDLER (legacy — combined command string)
# ================================================================

def handle(command: str) -> bool:
    command = command.lower().strip()

    listed = _handle_list_or_refresh(command)
    if listed is not None:
        return listed

    parsed = _parse_command(command)
    if not parsed:
        speak("I couldn't understand that device command.")
        return False

    return _execute_action(parsed["device_query"], parsed["action"], parsed["value"])
