import io
import json
import logging
import os
import threading
from flask import Flask, jsonify, request, send_file, send_from_directory
import requests
from gtts import gTTS

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Load environment variables from .env file if it exists
def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            logging.warning(f"Could not load .env file: {e}")

load_env_file()

app = Flask(__name__)

# Key rotation manager for Groq API
class GroqKeyManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.current_idx = 0
        self.keys = self._load_keys()

    def _load_keys(self):
        # Look for GROQ_API_KEYS (comma-separated list), then fall back to GROQ_API_KEY
        keys_str = os.environ.get("GROQ_API_KEYS", "").strip()
        if not keys_str:
            keys_str = os.environ.get("GROQ_API_KEY", "").strip()
        raw_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        # Filter out placeholder keys from .env.example
        valid_keys = [
            k for k in raw_keys
            if not any(ph in k.lower() for ph in ["your_first", "your_second", "your_groq", "your_key", "your_api"])
        ]
        return valid_keys

    def get_current_key(self):
        with self.lock:
            # Re-read if empty in case environment variables were set after init
            if not self.keys:
                self.keys = self._load_keys()
            if not self.keys:
                raise ValueError(
                    "GROQ_API_KEYS or GROQ_API_KEY is not set (or contains placeholder text). "
                    "Please replace the placeholder in your .env file with your real Groq API key (starts with 'gsk_')."
                )
            return self.keys[self.current_idx % len(self.keys)]

    def rotate_key(self):
        with self.lock:
            if not self.keys:
                self.keys = self._load_keys()
            if len(self.keys) > 1:
                prev_idx = self.current_idx
                self.current_idx = (self.current_idx + 1) % len(self.keys)
                masked_key = f"...{self.keys[self.current_idx][-6:]}" if len(self.keys[self.current_idx]) > 6 else "***"
                logging.warning(f"Rotated Groq API key from index {prev_idx} to {self.current_idx} ({masked_key})")
            else:
                logging.warning("Only 1 Groq API key configured; cannot rotate to a different key.")

key_manager = GroqKeyManager()

def call_groq_api(endpoint, method="POST", json_data=None, files=None, data=None):
    """
    Calls Groq REST API with automatic key rotation on HTTP 401, 403, and 429.
    Does NOT use Groq SDK; calls Groq REST API directly via requests.
    """
    total_keys = max(len(key_manager._load_keys()), 1)
    last_error = None

    for attempt in range(total_keys):
        try:
            api_key = key_manager.get_current_key()
        except ValueError as err:
            raise err

        headers = {"Authorization": f"Bearer {api_key}"}
        url = f"https://api.groq.com/openai/v1{endpoint}"

        try:
            if files:
                resp = requests.post(url, headers=headers, files=files, data=data, timeout=40)
            else:
                resp = requests.post(url, headers=headers, json=json_data, timeout=40)

            # Check if rate-limited or key authentication failed
            if resp.status_code in (401, 403, 429):
                logging.warning(f"Groq API returned HTTP {resp.status_code}: {resp.text}. Rotating key...")
                key_manager.rotate_key()
                last_error = f"HTTP {resp.status_code}: {resp.text}"
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None and e.response.status_code in (401, 403, 429):
                logging.warning(f"Groq API HTTP error {e.response.status_code}. Rotating key...")
                key_manager.rotate_key()
                last_error = str(e)
                continue
            raise e

    raise RuntimeError(f"All Groq API keys exhausted or rate-limited. Last error: {last_error}")

# System prompt builder
SCHEME_INFO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheme_info.txt")

def get_system_prompt():
    base_prompt = (
        "You are Sakhi (సఖి), a kind elder sister helping a Telugu-speaking woman who cannot read, "
        "write English or use technology. She may be a widow in distress. Reply ONLY in simple spoken Telugu, "
        "warm and respectful (use 'అమ్మా'). Maximum 2 short sentences in \"reply\". "
        "Flow: 1) which state (Andhra Pradesh or Telangana) 2) is her husband deceased "
        "3) does she have a ration card / bank account. Ask only ONE question per turn. "
        "Never ask for Aadhaar number, bank details, OTP or money. Warn her if anyone asks her for money to apply. "
        "Use ONLY the facts in SCHEME_INFO. If you don't know, say so and tell her to ask the Secretariat staff or "
        "Anganwadi teacher. When she qualifies, \"reply\" must name the pension and the monthly benefit in plain words "
        "and tell her to take the documents shown; put the office in \"place\". If she is confused, slow down and rephrase simply. "
        "Return ONLY JSON: {\"reply\": \"<Telugu>\", \"docs\": [], \"place\": \"\"}. "
        "\"docs\" is empty until she qualifies; then any of: \"aadhaar\",\"deathcert\",\"ration\",\"passbook\",\"photo\". "
        "\"place\" is a short Telugu line on where to go and what to say, or ''."
    )
    scheme_info_content = ""
    if os.path.exists(SCHEME_INFO_PATH):
        try:
            with open(SCHEME_INFO_PATH, "r", encoding="utf-8") as f:
                scheme_info_content = f.read()
        except Exception as e:
            logging.error(f"Error reading scheme_info.txt: {e}")
    return f"{base_prompt}\n\n[SCHEME_INFO]\n{scheme_info_content}"

# Route: Serve index.html
@app.route("/")
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "index.html")

# Route: Speech-to-Text via Groq Whisper
@app.route("/api/stt", methods=["POST"])
def stt():
    if "audio" not in request.files and "file" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files.get("audio") or request.files.get("file")
    filename = audio_file.filename or "recording.webm"
    if "." not in filename:
        filename += ".webm"
    
    audio_bytes = audio_file.read()
    logging.info(f"Received audio upload: {filename} ({len(audio_bytes)} bytes, {audio_file.mimetype})")

    if not audio_bytes or len(audio_bytes) < 500:
        logging.warning("Uploaded audio is empty or too short (< 500 bytes).")
        return jsonify({"text": ""})

    files = {
        "file": (filename, audio_bytes, audio_file.mimetype or "audio/webm")
    }
    data = {
        "model": "whisper-large-v3",
        "language": "te",
        "temperature": "0"
    }

    try:
        result = call_groq_api("/audio/transcriptions", method="POST", files=files, data=data)
        transcript = result.get("text", "").strip()
        logging.info(f"Whisper transcription result: '{transcript}'")
        return jsonify({"text": transcript})
    except ValueError as ve:
        logging.error(f"STT Configuration Error: {ve}")
        return jsonify({"error": str(ve), "text": ""}), 401
    except Exception as e:
        err_msg = str(e)
        logging.error(f"STT Error: {err_msg}")
        if "401" in err_msg or "Invalid API Key" in err_msg:
            return jsonify({
                "error": "Groq API key is invalid or placeholder. Please put your real Groq API key in .env (starts with gsk_)",
                "text": ""
            }), 401
        return jsonify({"error": err_msg, "text": ""}), 500

# Active chat model with automatic fallback
ACTIVE_CHAT_MODEL = None
CANDIDATE_CHAT_MODELS = [
    os.environ.get("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile"),
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b"
]

# Route: Chat reasoning via Groq LLaMA / Qwen
@app.route("/api/chat", methods=["POST"])
def chat():
    global ACTIVE_CHAT_MODEL
    body = request.get_json(silent=True) or {}
    incoming_messages = body.get("messages", [])

    # Keep last 12 messages
    recent_messages = []
    for msg in incoming_messages[-12:]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            recent_messages.append({
                "role": msg["role"],
                "content": str(msg["content"])
            })

    messages_payload = [
        {"role": "system", "content": get_system_prompt()},
        *recent_messages
    ]

    models_to_try = [ACTIVE_CHAT_MODEL] if ACTIVE_CHAT_MODEL else CANDIDATE_CHAT_MODELS
    result = None
    last_chat_error = None

    for model_name in models_to_try:
        if not model_name:
            continue
        payload = {
            "model": model_name,
            "temperature": 0.3,
            "max_tokens": 400,
            "response_format": {"type": "json_object"},
            "messages": messages_payload
        }
        try:
            result = call_groq_api("/chat/completions", method="POST", json_data=payload)
            ACTIVE_CHAT_MODEL = model_name
            logging.info(f"Chat completion succeeded using model: {model_name}")
            break
        except Exception as model_err:
            last_chat_error = model_err
            logging.warning(f"Chat model '{model_name}' failed: {model_err}. Trying fallback...")
            continue

    if result is None:
        logging.error(f"All chat models failed. Last error: {last_chat_error}")
        return jsonify({"error": str(last_chat_error)}), 500

    try:
        choice_msg = result.get("choices", [{}])[0].get("message", {})
        raw_content = choice_msg.get("content", "").strip()

        # Parse JSON safely
        try:
            # Strip markdown code blocks if returned
            clean_content = raw_content
            if clean_content.startswith("```"):
                lines = clean_content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                clean_content = "\n".join(lines).strip()

            parsed = json.loads(clean_content)
            reply = parsed.get("reply", "")
            docs = parsed.get("docs", [])
            place = parsed.get("place", "")

            # Ensure data types are consistent
            if not isinstance(docs, list):
                docs = []
            if not isinstance(place, str):
                place = str(place or "")
            if not isinstance(reply, str):
                reply = str(reply or "")

            return jsonify({
                "reply": reply,
                "docs": docs,
                "place": place
            })
        except Exception as json_err:
            logging.warning(f"Failed to parse LLM JSON response: {json_err}. Raw text: {raw_content}")
            return jsonify({
                "reply": raw_content,
                "docs": [],
                "place": ""
            })

    except Exception as e:
        logging.error(f"Chat Error: {e}")
        return jsonify({"error": str(e)}), 500

# Route: Text-to-Speech via gTTS
@app.route("/api/tts", methods=["POST"])
def tts():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "Text is required"}), 400

    try:
        tts_obj = gTTS(text=text, lang="te")
        fp = io.BytesIO()
        tts_obj.write_to_fp(fp)
        fp.seek(0)
        return send_file(fp, mimetype="audio/mpeg", as_attachment=False)
    except Exception as e:
        logging.error(f"TTS Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
