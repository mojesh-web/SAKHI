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

LANGS = {
    "te": {
        "whisper_code": "te",
        "gtts_code": "te",
        "unicode_range": (0x0C00, 0x0C7F),
        "scheme_file": "scheme_info_te.txt",
        "welcome_text": "నమస్కారం అమ్మా, నేను సఖిని. మీకు సహాయం చేస్తాను. ముందుగా చెప్పండి, మీ భర్త చనిపోయారా?",
        "ui_strings": {
            "idle": "నమస్కారం",
            "repeat": "మళ్ళీ చెప్పండి",
            "didnt_hear": "మీరు చెప్పింది వినపడలేదు.",
            "error": "ఏదో తప్పు జరిగింది."
        },
        "doc_labels": {
            "aadhaar": "ఆధార్ కార్డు",
            "deathcert": "మరణ ధృవీకరణ పత్రం",
            "ration": "రేషన్ కార్డు",
            "passbook": "బ్యాంకు పాస్ బుక్",
            "photo": "పాస్ పోర్ట్ ఫోటో"
        },
        "system_instruction": "You are Sakhi (సఖి), a kind elder sister helping a Telugu-speaking woman who cannot read, write English or use technology. She may be a widow in distress. Reply ONLY in simple spoken Telugu, warm and respectful (use 'అమ్మా'). Maximum 2 short sentences in \"reply\". Flow: 1) which state (Andhra Pradesh or Telangana) 2) is her husband deceased 3) does she have a ration card / bank account. Ask only ONE question per turn. Never ask for Aadhaar number, bank details, OTP or money. Warn her if anyone asks her for money to apply. Use ONLY the facts in SCHEME_INFO. If you don't know, say so and tell her to ask the Secretariat staff or Anganwadi teacher. When she qualifies, \"reply\" must name the pension and the monthly benefit in plain words and tell her to take the documents shown; put the office in \"place\". If she is confused, slow down and rephrase simply."
    },
    "ta": {
        "whisper_code": "ta",
        "gtts_code": "ta",
        "unicode_range": (0x0B80, 0x0BFF),
        "scheme_file": "scheme_info_ta.txt",
        "welcome_text": "வணக்கம் அம்மா, நான் சகி. உங்களுக்கு உதவுகிறேன். முதலில் சொல்லுங்கள், உங்கள் கணவர் இறந்துவிட்டாரா?",
        "ui_strings": {
            "idle": "வணக்கம்",
            "repeat": "மீண்டும் சொல்லுங்கள்",
            "didnt_hear": "நீங்கள் சொல்வது கேட்கவில்லை.",
            "error": "ஏதோ தவறு நடந்துவிட்டது."
        },
        "doc_labels": {
            "aadhaar": "ஆதார் அட்டை",
            "deathcert": "இறப்பு சான்றிதழ்",
            "ration": "ரேஷன் அட்டை",
            "passbook": "வங்கி புத்தகம்",
            "photo": "பாஸ்போர்ட் புகைப்படம்"
        },
        "system_instruction": "You are Sakhi (சகி), a kind elder sister helping a Tamil-speaking woman who cannot read, write English or use technology. She may be a widow in distress. Reply ONLY in simple spoken Tamil, warm and respectful (use 'அம்மா'). Maximum 2 short sentences in \"reply\". Flow: 1) is her husband deceased 2) does she have a ration card / bank account. Ask only ONE question per turn. Never ask for Aadhaar number, bank details, OTP or money. Warn her if anyone asks her for money to apply. Use ONLY the facts in SCHEME_INFO. If you don't know, say so and tell her to ask the local VAO or Taluk office. When she qualifies, \"reply\" must name the pension and the monthly benefit in plain words and tell her to take the documents shown; put the office in \"place\". If she is confused, slow down and rephrase simply."
    }
}

class GroqKeyManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.current_idx = 0
        self.keys = self._load_keys()

    def _load_keys(self):
        keys_str = os.environ.get("GROQ_API_KEYS", "").strip()
        if not keys_str:
            keys_str = os.environ.get("GROQ_API_KEY", "").strip()
        raw_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        valid_keys = [
            k for k in raw_keys
            if not any(ph in k.lower() for ph in ["your_first", "your_second", "your_groq", "your_key", "your_api"])
        ]
        return valid_keys

    def get_current_key(self):
        with self.lock:
            if not self.keys:
                self.keys = self._load_keys()
            if not self.keys:
                raise ValueError("GROQ_API_KEYS or GROQ_API_KEY is not set (or contains placeholder text).")
            return self.keys[self.current_idx % len(self.keys)]

    def rotate_key(self):
        with self.lock:
            if not self.keys:
                self.keys = self._load_keys()
            if len(self.keys) > 1:
                prev_idx = self.current_idx
                self.current_idx = (self.current_idx + 1) % len(self.keys)
                logging.warning(f"Rotated Groq API key from index {prev_idx} to {self.current_idx}")

key_manager = GroqKeyManager()

def call_groq_api(endpoint, method="POST", json_data=None, files=None, data=None):
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

            if resp.status_code in (401, 403, 429):
                key_manager.rotate_key()
                last_error = f"HTTP {resp.status_code}: {resp.text}"
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None and e.response.status_code in (401, 403, 429):
                key_manager.rotate_key()
                last_error = str(e)
                continue
            raise e

    raise RuntimeError(f"All Groq API keys exhausted. Last error: {last_error}")

def get_system_prompt(lang):
    config = LANGS.get(lang)
    if not config:
        return ""
    base_prompt = config["system_instruction"]
    scheme_info_content = ""
    scheme_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config["scheme_file"])
    if os.path.exists(scheme_path):
        try:
            with open(scheme_path, "r", encoding="utf-8") as f:
                scheme_info_content = f.read()
        except Exception as e:
            logging.error(f"Error reading {config['scheme_file']}: {e}")
            
    base_prompt += "\nReturn ONLY JSON: {\"reply\": \"<Text in chosen language>\", \"docs\": [], \"place\": \"\"}. \"docs\" is empty until she qualifies; then any of: \"aadhaar\",\"deathcert\",\"ration\",\"passbook\",\"photo\". \"place\" is a short line in chosen language on where to go and what to say, or ''."
    return f"{base_prompt}\n\n[SCHEME_INFO]\n{scheme_info_content}"

@app.route("/")
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "index.html")

def detect_lang(text, whisper_lang):
    text_lower = text.lower()
    te_keywords = ["నమస్కారం", "నమస్కారము", "నమస్తే", "namaskaram", "namaskaaram", "namasakaram", "namaskar"]
    ta_keywords = ["வணக்கம்", "vanakkam", "vanakam", "vanakkamunga"]
    
    for kw in te_keywords:
        if kw in text_lower:
            return "te"
    for kw in ta_keywords:
        if kw in text_lower:
            return "ta"
            
    if whisper_lang in ["te", "ta"] and len(text.strip()) > 1:
        return whisper_lang
        
    return None

@app.route("/api/detect", methods=["POST"])
def detect():
    if "audio" not in request.files and "file" not in request.files:
        return jsonify({"error": "No audio file"}), 400

    audio_file = request.files.get("audio") or request.files.get("file")
    filename = audio_file.filename or "recording.webm"
    audio_bytes = audio_file.read()

    if not audio_bytes or len(audio_bytes) < 500:
        return jsonify({"lang": None, "text": ""})

    files = {"file": (filename, audio_bytes, audio_file.mimetype or "audio/webm")}
    data = {
        "model": "whisper-large-v3",
        "temperature": "0",
        "prompt": "నమస్కారం, வணக்கம்"
    }

    try:
        result = call_groq_api("/audio/transcriptions", method="POST", files=files, data=data)
        transcript = result.get("text", "").strip()
        whisper_lang = result.get("language", "")
        
        # Don't hallucinate on silence
        if not transcript:
             return jsonify({"lang": None, "text": ""})
             
        detected = detect_lang(transcript, whisper_lang)
        
        return jsonify({
            "lang": detected,
            "text": transcript
        })
    except Exception as e:
        logging.error(f"Detect Error: {e}")
        return jsonify({"error": str(e), "lang": None, "text": ""}), 500

@app.route("/api/stt", methods=["POST"])
def stt():
    if "audio" not in request.files and "file" not in request.files:
        return jsonify({"error": "No audio file"}), 400

    lang = request.form.get("lang", "te")
    whisper_lang = LANGS.get(lang, {}).get("whisper_code", "te")

    audio_file = request.files.get("audio") or request.files.get("file")
    filename = audio_file.filename or "recording.webm"
    audio_bytes = audio_file.read()

    if not audio_bytes or len(audio_bytes) < 500:
        return jsonify({"text": ""})

    files = {"file": (filename, audio_bytes, audio_file.mimetype or "audio/webm")}
    data = {
        "model": "whisper-large-v3",
        "language": whisper_lang,
        "temperature": "0"
    }

    try:
        result = call_groq_api("/audio/transcriptions", method="POST", files=files, data=data)
        transcript = result.get("text", "").strip()
        return jsonify({"text": transcript})
    except Exception as e:
        logging.error(f"STT Error: {e}")
        return jsonify({"error": str(e), "text": ""}), 500

ACTIVE_CHAT_MODEL = None
CANDIDATE_CHAT_MODELS = [
    os.environ.get("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile"),
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b"
]

def is_script_pure(text, lang):
    config = LANGS.get(lang)
    if not config:
        return True
    start, end = config["unicode_range"]
    for char in text:
        if char.isalpha():
            if not (start <= ord(char) <= end):
                return False
    return True

@app.route("/api/chat", methods=["POST"])
def chat():
    global ACTIVE_CHAT_MODEL
    body = request.get_json(silent=True) or {}
    incoming_messages = body.get("messages", [])
    lang = body.get("lang", "te")
    lang_name = "Telugu" if lang == "te" else "Tamil"

    recent_messages = []
    for msg in incoming_messages[-12:]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            recent_messages.append({"role": msg["role"], "content": str(msg["content"])})

    def run_chat(messages):
        global ACTIVE_CHAT_MODEL
        models_to_try = [ACTIVE_CHAT_MODEL] if ACTIVE_CHAT_MODEL else CANDIDATE_CHAT_MODELS
        for model_name in models_to_try:
            if not model_name: continue
            payload = {
                "model": model_name,
                "temperature": 0.3,
                "max_tokens": 400,
                "response_format": {"type": "json_object"},
                "messages": messages
            }
            try:
                res = call_groq_api("/chat/completions", method="POST", json_data=payload)
                ACTIVE_CHAT_MODEL = model_name
                return res
            except Exception as e:
                logging.warning(f"Chat model '{model_name}' failed: {e}")
                continue
        return None

    messages_payload = [{"role": "system", "content": get_system_prompt(lang)}] + recent_messages
    
    result = run_chat(messages_payload)
    if not result:
        return jsonify({"error": "All models failed"}), 500

    def extract_json(res):
        try:
            raw = res.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                if lines[0].startswith("```"): lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"): lines = lines[:-1]
                raw = "\n".join(lines).strip()
            parsed = json.loads(raw)
            return parsed.get("reply", ""), parsed.get("docs", []), parsed.get("place", "")
        except:
            return raw, [], ""

    reply, docs, place = extract_json(result)

    if not is_script_pure(reply, lang) or not is_script_pure(place, lang):
        logging.warning("Script purity failed! Retrying once...")
        messages_payload.append({"role": "assistant", "content": json.dumps({"reply": reply, "docs": docs, "place": place})})
        messages_payload.append({"role": "user", "content": f"Your last answer used the wrong language. Answer ONLY in {lang_name}."})
        result2 = run_chat(messages_payload)
        if result2:
            reply, docs, place = extract_json(result2)

    return jsonify({"reply": reply, "docs": docs, "place": place})

@app.route("/api/tts", methods=["POST"])
def tts():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    lang = body.get("lang", "te")
    gtts_code = LANGS.get(lang, {}).get("gtts_code", "te")
    
    if not text:
        return jsonify({"error": "Text is required"}), 400

    try:
        tts_obj = gTTS(text=text, lang=gtts_code)
        fp = io.BytesIO()
        tts_obj.write_to_fp(fp)
        fp.seek(0)
        return send_file(fp, mimetype="audio/mpeg", as_attachment=False)
    except Exception as e:
        logging.error(f"TTS Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/config", methods=["GET"])
def get_config():
    lang = request.args.get("lang", "te")
    return jsonify(LANGS.get(lang, LANGS["te"]))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
