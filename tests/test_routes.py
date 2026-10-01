import io
import json
import pytest
from unittest.mock import patch, MagicMock

from backend.routes import app
from backend import config

@pytest.fixture
def client():
    app.config["TESTING"] = True
    # Bypass rate limiting for tests
    app.config["RATELIMIT_ENABLED"] = False
    with app.test_client() as client:
        yield client

def test_index_route(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Sakhi" in res.data
    assert "nosniff" in res.headers.get("X-Content-Type-Options")

@patch("backend.routes.groq_client.transcribe_audio")
def test_api_detect_success(mock_transcribe, client):
    mock_transcribe.return_value = ("నమస్కారం", "te")
    data = {"audio": (io.BytesIO(b"dummy audio data min 500 bytes" * 20), "test.webm")}
    res = client.post("/api/detect", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["lang"] == "te"
    assert json_data["text"] == "నమస్కారం"

def test_api_detect_invalid_audio_size(client):
    # Too small
    data = {"audio": (io.BytesIO(b"tiny"), "test.webm")}
    res = client.post("/api/detect", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    assert res.get_json()["lang"] is None

@patch("backend.routes.groq_client.transcribe_audio")
def test_api_stt_success(mock_transcribe, client):
    mock_transcribe.return_value = ("అవును", "te")
    data = {
        "audio": (io.BytesIO(b"dummy audio data min 500 bytes" * 20), "test.webm"),
        "lang": "te"
    }
    res = client.post("/api/stt", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    assert res.get_json()["text"] == "అవును"

@patch("backend.routes.groq_client.chat_completion")
def test_api_chat_success(mock_chat, client):
    mock_chat.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({"reply": "నమస్కారం", "docs": ["photo"], "place": ""})
            }
        }]
    }
    res = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}], "lang": "te"})
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["reply"] == "నమస్కారం"
    assert "photo" in json_data["docs"]

@patch("backend.routes.groq_client.chat_completion")
def test_api_chat_purity_retry(mock_chat, client):
    # First call returns impure English text, second returns pure Telugu
    resp_impure = {"choices": [{"message": {"content": json.dumps({"reply": "Hello నమస్కారం"})}}]}
    resp_pure = {"choices": [{"message": {"content": json.dumps({"reply": "నమస్కారం"})}}]}
    mock_chat.side_effect = [resp_impure, resp_pure]
    
    res = client.post("/api/chat", json={"messages": [], "lang": "te"})
    assert res.status_code == 200
    assert res.get_json()["reply"] == "నమస్కారం"
    assert mock_chat.call_count == 2

def test_api_chat_input_too_long(client):
    long_msg = "a" * 1500
    res = client.post("/api/chat", json={"messages": [{"role": "user", "content": long_msg}]})
    assert res.status_code == 400

@patch("backend.routes.get_tts_audio")
def test_api_tts_success(mock_tts, client):
    mock_tts.return_value = b"mp3data"
    res = client.post("/api/tts", json={"text": "నమస్కారం", "lang": "te"})
    assert res.status_code == 200
    assert res.mimetype == "audio/mpeg"

def test_api_tts_missing_text(client):
    res = client.post("/api/tts", json={"lang": "te"})
    assert res.status_code == 400

def test_api_tts_too_long(client):
    res = client.post("/api/tts", json={"text": "a" * 1500})
    assert res.status_code == 400
