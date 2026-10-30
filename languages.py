"""Languages offered for summaries and voice input.

One list feeds the backend (prompt wording, font choice) and the frontend
(dropdowns, speech-recognition codes), so they cannot drift apart.
"""
import re

LANGUAGES = [
    {"name": "English",   "native": "English",    "script": "latin",      "speech": "en-IN"},
    {"name": "Hindi",     "native": "हिन्दी",       "script": "devanagari", "speech": "hi-IN"},
    {"name": "Tamil",     "native": "தமிழ்",        "script": "tamil",      "speech": "ta-IN"},
    {"name": "Telugu",    "native": "తెలుగు",       "script": "telugu",     "speech": "te-IN"},
    {"name": "Kannada",   "native": "ಕನ್ನಡ",        "script": "kannada",    "speech": "kn-IN"},
    {"name": "Malayalam", "native": "മലയാളം",     "script": "malayalam",  "speech": "ml-IN"},
    {"name": "Marathi",   "native": "मराठी",       "script": "devanagari", "speech": "mr-IN"},
    {"name": "Bengali",   "native": "বাংলা",        "script": "bengali",    "speech": "bn-IN"},
    {"name": "Gujarati",  "native": "ગુજરાતી",      "script": "gujarati",   "speech": "gu-IN"},
    {"name": "Spanish",   "native": "Español",    "script": "latin",      "speech": "es-ES"},
    {"name": "French",    "native": "Français",   "script": "latin",      "speech": "fr-FR"},
    {"name": "German",    "native": "Deutsch",    "script": "latin",      "speech": "de-DE"},
]

_BY_NAME = {item["name"].lower(): item for item in LANGUAGES}
_CUSTOM_NAME = re.compile(r"^[A-Za-z][A-Za-z \-()]{1,38}$")


def find_language(name):
    """Return the language entry for `name`.

    Listed languages come back as-is. Any other plain-letter name (for example
    "Odia") is accepted as a custom language with an unknown script. Anything
    else raises ValueError, so free text can never be pasted into a prompt.
    """
    clean = (name or "").strip()
    known = _BY_NAME.get(clean.lower())
    if known:
        return known
    if _CUSTOM_NAME.match(clean):
        return {"name": clean, "native": clean, "script": "unknown", "speech": ""}
    raise ValueError("Choose a language from the list, or type a language name using letters only.")
