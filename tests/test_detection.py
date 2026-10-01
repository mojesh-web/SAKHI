import pytest
from backend.detection import detect_lang, is_script_pure
from backend.languages import LANGS

def test_detect_lang_keywords():
    assert detect_lang("నమస్కారం అమ్మా", "en") == "te"
    assert detect_lang("Hello namaskaram", "en") == "te"
    assert detect_lang("வணக்கம்", "en") == "ta"
    assert detect_lang("Vanakam amma", "en") == "ta"

def test_detect_lang_whisper_fallback():
    assert detect_lang("అవును", "te") == "te"
    assert detect_lang("ஆமாம்", "ta") == "ta"
    assert detect_lang("Hello", "en") is None

def test_detect_lang_empty():
    assert detect_lang("", "te") is None
    assert detect_lang("   ", "ta") is None

def test_script_purity_te():
    assert is_script_pure("నమస్కారం అమ్మా. ఎలా ఉన్నారు?", "te") is True
    assert is_script_pure("నమస్కారం అమ్మా. Hello?", "te") is False
    assert is_script_pure("నమస్కారం வணக்கம்", "te") is False

def test_script_purity_ta():
    assert is_script_pure("வணக்கம் அம்மா, நான் சகி.", "ta") is True
    assert is_script_pure("வணக்கம் Hello", "ta") is False
    assert is_script_pure("வணக்கம் నమస్కారం", "ta") is False

def test_script_purity_unknown_lang():
    # If lang not configured, default to true
    assert is_script_pure("Hello", "unknown") is True
