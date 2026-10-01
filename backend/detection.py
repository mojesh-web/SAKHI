from typing import Optional

from .languages import LANGS


def detect_lang(text: str, whisper_lang: str) -> Optional[str]:
    """
    Detects language based on keywords, prioritizing user spoken intent over Whisper guess.
    Ignores purely empty text.
    """
    text_lower = text.lower().strip()
    if not text_lower:
        return None

    te_keywords = [
        "నమస్కారం",
        "నమస్కారము",
        "నమస్తే",
        "namaskaram",
        "namaskaaram",
        "namasakaram",
        "namaskar",
    ]
    ta_keywords = ["வணக்கம்", "vanakkam", "vanakam", "vanakkamunga"]

    for kw in te_keywords:
        if kw in text_lower:
            return "te"
    for kw in ta_keywords:
        if kw in text_lower:
            return "ta"

    if whisper_lang in ["te", "ta"] and len(text_lower) > 1:
        return whisper_lang

    return None


def is_script_pure(text: str, lang: str) -> bool:
    """
    Checks if all alphabetical characters in the text fall strictly within
    the Unicode block of the target language.
    """
    config = LANGS.get(lang)
    if not config:
        return True

    start, end = config["unicode_range"]
    for char in text:
        if char.isalpha():
            if not (start <= ord(char) <= end):
                return False
    return True
