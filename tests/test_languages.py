import os
import pytest
from unittest.mock import patch, MagicMock

from backend.languages import init_languages, get_system_prompt, get_tts_audio, _scheme_cache, _tts_cache

def test_init_languages(tmp_path):
    # Create fake scheme files
    (tmp_path / "scheme_info_te.txt").write_text("Telugu Scheme", encoding="utf-8")
    (tmp_path / "scheme_info_ta.txt").write_text("Tamil Scheme", encoding="utf-8")
    
    init_languages(str(tmp_path))
    assert _scheme_cache["te"] == "Telugu Scheme"
    assert _scheme_cache["ta"] == "Tamil Scheme"

def test_get_system_prompt():
    _scheme_cache["te"] = "Telugu Scheme Content"
    prompt = get_system_prompt("te")
    assert "You are Sakhi" in prompt
    assert "Telugu Scheme Content" in prompt

def test_get_system_prompt_invalid():
    assert get_system_prompt("unknown") == ""

@patch("backend.languages.gTTS")
def test_get_tts_audio_cache(mock_gtts):
    mock_instance = MagicMock()
    mock_instance.write_to_fp.side_effect = lambda fp: fp.write(b"tts_audio")
    mock_gtts.return_value = mock_instance
    
    # First call
    audio1 = get_tts_audio("Hello", "te")
    assert audio1 == b"tts_audio"
    assert mock_gtts.call_count == 1
    
    # Second call uses cache
    audio2 = get_tts_audio("Hello", "te")
    assert audio2 == b"tts_audio"
    assert mock_gtts.call_count == 1
