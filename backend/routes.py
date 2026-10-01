import io
import json
import logging

from flask import Flask, jsonify, make_response, request, send_file, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from . import config
from .detection import detect_lang, is_script_pure
from .exceptions import InvalidAudioError, SakhiBaseException
from .groq_client import groq_client
from .languages import LANGS, get_system_prompt, get_tts_audio

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="../static")
app.config["DEBUG"] = config.DEBUG

limiter = Limiter(
    get_remote_address, app=app, default_limits=[config.RATELIMIT_DEFAULT], storage_uri="memory://"
)


@app.errorhandler(SakhiBaseException)
def handle_sakhi_exception(e):
    logger.error(f"Sakhi Error ({e.status_code}): {str(e)}")
    return jsonify({"error": str(e)}), e.status_code


@app.errorhandler(Exception)
def handle_generic_exception(e):
    logger.exception("Unexpected error occurred")
    return jsonify({"error": "An internal error occurred."}), 500


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; connect-src 'self' https://api.groq.com; font-src 'self' https://fonts.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; media-src 'self' blob:; script-src 'self' 'unsafe-inline';"
    )
    return response


@app.route("/")
def index():
    response = make_response(send_from_directory("..", "index.html"))
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


def _validate_audio(request_obj) -> bytes:
    audio_file = request_obj.files.get("audio") or request_obj.files.get("file")
    if not audio_file:
        raise InvalidAudioError("No audio file provided.")

    audio_bytes = audio_file.read()
    if not audio_bytes or len(audio_bytes) < config.MIN_AUDIO_SIZE_BYTES:
        return b""  # Empty or too short

    if len(audio_bytes) > config.MAX_AUDIO_SIZE_BYTES:
        raise InvalidAudioError("Audio file exceeds maximum allowed size.")

    return audio_bytes


@app.route("/api/detect", methods=["POST"])
@limiter.limit("20 per minute")
def api_detect():
    audio_bytes = _validate_audio(request)
    if not audio_bytes:
        return jsonify({"lang": None, "text": ""})

    audio_file = request.files.get("audio") or request.files.get("file")
    filename = audio_file.filename or "recording.webm"
    mimetype = audio_file.mimetype or "audio/webm"

    transcript, whisper_lang = groq_client.transcribe_audio(
        audio_bytes, filename, mimetype, language="", prompt="నమస్కారం, வணக்கம்"
    )

    detected = detect_lang(transcript, whisper_lang)
    return jsonify({"lang": detected, "text": transcript})


@app.route("/api/stt", methods=["POST"])
def api_stt():
    lang = request.form.get("lang", "te")
    if lang not in LANGS:
        lang = "te"

    whisper_lang = LANGS[lang]["whisper_code"]
    audio_bytes = _validate_audio(request)
    if not audio_bytes:
        return jsonify({"text": ""})

    audio_file = request.files.get("audio") or request.files.get("file")
    filename = audio_file.filename or "recording.webm"
    mimetype = audio_file.mimetype or "audio/webm"

    transcript, _ = groq_client.transcribe_audio(
        audio_bytes, filename, mimetype, language=whisper_lang
    )
    return jsonify({"text": transcript})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    body = request.get_json(silent=True) or {}
    incoming_messages = body.get("messages", [])
    lang = body.get("lang", "te")
    if lang not in LANGS:
        lang = "te"

    # Trim to max history
    recent_messages = incoming_messages[-config.MAX_CHAT_HISTORY :]

    # Re-validate text constraints to prevent prompt injection or abuse
    for msg in recent_messages:
        if len(str(msg.get("content", ""))) > 1000:
            return jsonify({"error": "Input too long"}), 400

    sys_prompt = get_system_prompt(lang)
    messages_payload = [{"role": "system", "content": sys_prompt}] + recent_messages

    result = groq_client.chat_completion(messages_payload)

    def extract_json(res):
        try:
            raw = res.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                raw = "\n".join(lines).strip()
            parsed = json.loads(raw)
            return parsed.get("reply", ""), parsed.get("docs", []), parsed.get("place", "")
        except Exception:
            return raw, [], ""

    reply, docs, place = extract_json(result)

    # Purity check
    if not is_script_pure(reply, lang) or not is_script_pure(place, lang):
        logger.warning(f"Script purity failed for lang {lang}. Retrying once...")
        messages_payload.append(
            {
                "role": "assistant",
                "content": json.dumps({"reply": reply, "docs": docs, "place": place}),
            }
        )
        lang_name = "Telugu" if lang == "te" else "Tamil"
        messages_payload.append(
            {
                "role": "user",
                "content": f"Your last answer used the wrong language or English characters. Answer ONLY in pure {lang_name}.",
            }
        )
        result2 = groq_client.chat_completion(messages_payload)
        reply, docs, place = extract_json(result2)

    return jsonify({"reply": reply, "docs": docs, "place": place})


@app.route("/api/tts", methods=["POST"])
def api_tts():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    lang = body.get("lang", "te")
    if lang not in LANGS:
        lang = "te"

    if not text:
        return jsonify({"error": "Text is required"}), 400
    if len(text) > 1000:
        return jsonify({"error": "Text too long"}), 400

    audio_bytes = get_tts_audio(text, lang)
    return send_file(io.BytesIO(audio_bytes), mimetype="audio/mpeg", as_attachment=False)
