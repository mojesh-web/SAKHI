import io
import logging
import os
from typing import Any, Dict

from gtts import gTTS

logger = logging.getLogger(__name__)

# Basic definitions
LANGS: Dict[str, Dict[str, Any]] = {
    "te": {
        "whisper_code": "te",
        "gtts_code": "te",
        "unicode_range": (0x0C00, 0x0C7F),
        "scheme_file": "scheme_info_te.txt",
        "welcome_text": "నమస్కారం అమ్మా, నేను సఖిని. మీకు సహాయం చేస్తాను. ముందుగా చెప్పండి, మీ భర్త చనిపోయారా?",
        "system_instruction": 'You are Sakhi (సఖి), a kind elder sister helping a Telugu-speaking woman who cannot read, write English or use technology. She may be a widow in distress. Reply ONLY in simple spoken Telugu, warm and respectful (use \'అమ్మా\'). Maximum 2 short sentences in "reply". Flow: 1) which state (Andhra Pradesh or Telangana) 2) is her husband deceased 3) does she have a ration card / bank account. Ask only ONE question per turn. Never ask for Aadhaar number, bank details, OTP or money. Warn her if anyone asks her for money to apply. Use ONLY the facts in SCHEME_INFO. If you don\'t know, say so and tell her to ask the Secretariat staff or Anganwadi teacher. When she qualifies, "reply" must name the pension and the monthly benefit in plain words and tell her to take the documents shown; put the office in "place". If she is confused, slow down and rephrase simply.',
    },
    "ta": {
        "whisper_code": "ta",
        "gtts_code": "ta",
        "unicode_range": (0x0B80, 0x0BFF),
        "scheme_file": "scheme_info_ta.txt",
        "welcome_text": "வணக்கம் அம்மா, நான் சகி. உங்களுக்கு உதவுகிறேன். முதலில் சொல்லுங்கள், உங்கள் கணவர் இறந்துவிட்டாரா?",
        "system_instruction": 'You are Sakhi (சகி), a kind elder sister helping a Tamil-speaking woman who cannot read, write English or use technology. She may be a widow in distress. Reply ONLY in simple spoken Tamil, warm and respectful (use \'அம்மா\'). Maximum 2 short sentences in "reply". Flow: 1) is her husband deceased 2) does she have a ration card / bank account. Ask only ONE question per turn. Never ask for Aadhaar number, bank details, OTP or money. Warn her if anyone asks her for money to apply. Use ONLY the facts in SCHEME_INFO. If you don\'t know, say so and tell her to ask the local VAO or Taluk office. When she qualifies, "reply" must name the pension and the monthly benefit in plain words and tell her to take the documents shown; put the office in "place". If she is confused, slow down and rephrase simply.',
    },
}

_scheme_cache: Dict[str, str] = {}
_tts_cache: Dict[str, bytes] = {}


def get_system_prompt(lang: str) -> str:
    """Returns the compiled system prompt with scheme info injected."""
    config = LANGS.get(lang)
    if not config:
        return ""

    scheme_content = _scheme_cache.get(lang, "")
    base_prompt = config["system_instruction"]
    base_prompt += '\nReturn ONLY JSON: {"reply": "<Text in chosen language>", "docs": [], "place": ""}. "docs" is empty until she qualifies; then any of: "aadhaar","deathcert","ration","passbook","photo". "place" is a short line in chosen language on where to go and what to say, or \'\'.'

    return f"{base_prompt}\n\n[SCHEME_INFO]\n{scheme_content}"


def init_languages(base_dir: str) -> None:
    """Load scheme files and pre-generate static TTS at startup."""
    for lang_code, config in LANGS.items():
        # Load Scheme Text
        scheme_path = os.path.join(base_dir, config["scheme_file"])
        if os.path.exists(scheme_path):
            with open(scheme_path, "r", encoding="utf-8") as f:
                _scheme_cache[lang_code] = f.read()
        else:
            logger.warning(f"Scheme file not found: {scheme_path}")


def get_tts_audio(text: str, lang: str) -> bytes:
    """Generates TTS audio or returns cached version for static phrases."""
    cache_key = f"{lang}:{text}"
    if cache_key in _tts_cache:
        return _tts_cache[cache_key]

    config = LANGS.get(lang)
    gtts_code = config["gtts_code"] if config else "te"

    tts_obj = gTTS(text=text, lang=gtts_code)
    fp = io.BytesIO()
    tts_obj.write_to_fp(fp)
    audio_bytes = fp.getvalue()

    # Simple in-memory caching (since memory footprint is small for short texts)
    if len(_tts_cache) < 1000:
        _tts_cache[cache_key] = audio_bytes

    return audio_bytes
