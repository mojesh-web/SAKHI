import json
import pytest
from unittest.mock import patch, MagicMock

from backend import config
from backend.groq_client import GroqKeyManager, GroqClient
from backend.exceptions import ConfigurationError, GroqAPIError

def test_key_rotation_success():
    mgr = GroqKeyManager("key1,key2")
    assert mgr.get_current_key() == "key1"
    mgr.rotate_key()
    assert mgr.get_current_key() == "key2"
    mgr.rotate_key()
    assert mgr.get_current_key() == "key1"

def test_key_manager_filters_placeholders():
    mgr = GroqKeyManager("key1,your_groq_api_key,key2")
    assert mgr.keys == ["key1", "key2"]

def test_key_manager_empty_raises():
    with pytest.raises(ConfigurationError):
        GroqKeyManager("your_key_here")

@patch("requests.Session.post")
def test_groq_client_recovers_429(mock_post):
    config.GROQ_API_KEYS = "key1,key2"
    client = GroqClient()
    client.key_manager = GroqKeyManager("key1,key2")
    
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.text = "rate limit"
    
    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {"text": "hello", "language": "te"}
    
    mock_post.side_effect = [resp_429, resp_200]
    
    txt, lang = client.transcribe_audio(b"audio", "test.webm", "audio/webm", "te")
    assert txt == "hello"
    assert lang == "te"
    assert mock_post.call_count == 2
    assert client.key_manager.get_current_key() == "key2" # Rotated to key2 and stayed there (or rotated after?) wait, if it rotated it's now on key2

@patch("requests.Session.post")
def test_groq_client_exhausts_keys(mock_post):
    config.GROQ_API_KEYS = "key1"
    client = GroqClient()
    client.key_manager = GroqKeyManager("key1")
    
    resp_429 = MagicMock()
    resp_429.status_code = 429
    mock_post.return_value = resp_429
    
    with pytest.raises(GroqAPIError) as exc:
        client.chat_completion([{"role": "user", "content": "hi"}])
    assert "exhausted" in str(exc.value)
