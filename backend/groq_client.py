import logging
import threading
from typing import Any, Dict, Optional

import requests

from . import config
from .exceptions import ConfigurationError, GroqAPIError

logger = logging.getLogger(__name__)


class GroqKeyManager:
    """Thread-safe key manager that rotates across multiple Groq API keys."""

    def __init__(self, keys_str: str):
        self.lock = threading.Lock()
        self.current_idx = 0
        self.keys = self._parse_keys(keys_str)
        if not self.keys:
            raise ConfigurationError(
                "No valid Groq API keys configured. Please set GROQ_API_KEY in .env."
            )

    def _parse_keys(self, keys_str: str) -> list[str]:
        raw_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        return [
            k
            for k in raw_keys
            if not any(
                ph in k.lower()
                for ph in ["your_first", "your_second", "your_groq", "your_key", "your_api"]
            )
        ]

    def get_current_key(self) -> str:
        with self.lock:
            return self.keys[self.current_idx % len(self.keys)]

    def rotate_key(self) -> None:
        with self.lock:
            if len(self.keys) > 1:
                self.current_idx = (self.current_idx + 1) % len(self.keys)
                logger.warning(f"Rotated Groq API key to index {self.current_idx}")


class GroqClient:
    """A singleton-like client for communicating with Groq."""

    def __init__(self):
        self.key_manager = GroqKeyManager(config.GROQ_API_KEYS)
        self.session = requests.Session()
        self.active_chat_model = None

    def _call_api(
        self,
        endpoint: str,
        json_data: Optional[Dict] = None,
        files: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        total_keys = len(self.key_manager.keys)
        last_error = None

        url = f"{config.GROQ_BASE_URL}{endpoint}"

        for _ in range(max(total_keys, 1)):
            api_key = self.key_manager.get_current_key()
            headers = {"Authorization": f"Bearer {api_key}"}

            try:
                if files:
                    resp = self.session.post(
                        url, headers=headers, files=files, data=data, timeout=30
                    )
                else:
                    resp = self.session.post(url, headers=headers, json=json_data, timeout=30)

                if resp.status_code in (401, 403, 429):
                    self.key_manager.rotate_key()
                    last_error = f"HTTP {resp.status_code}: {resp.text}"
                    continue

                resp.raise_for_status()
                return resp.json()

            except requests.exceptions.RequestException as e:
                if (
                    hasattr(e, "response")
                    and e.response is not None
                    and e.response.status_code in (401, 403, 429)
                ):
                    self.key_manager.rotate_key()
                    last_error = str(e)
                    continue
                raise GroqAPIError(f"Network error calling Groq: {str(e)}")

        raise GroqAPIError(
            f"All Groq API keys exhausted. Last error: {last_error}", status_code=500
        )

    def transcribe_audio(
        self, audio_bytes: bytes, filename: str, mimetype: str, language: str, prompt: str = ""
    ) -> str:
        files = {"file": (filename, audio_bytes, mimetype)}
        data = {
            "model": config.GROQ_STT_MODEL,
            "temperature": str(config.STT_TEMPERATURE),
        }
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt

        result = self._call_api("/audio/transcriptions", files=files, data=data)
        return result.get("text", "").strip(), result.get("language", "")

    def chat_completion(self, messages: list[Dict[str, str]]) -> Dict[str, Any]:
        models_to_try = (
            [self.active_chat_model] if self.active_chat_model else config.GROQ_CHAT_MODELS
        )

        last_err = None
        for model_name in models_to_try:
            if not model_name:
                continue
            payload = {
                "model": model_name,
                "temperature": config.TEMPERATURE,
                "max_tokens": config.MAX_TOKENS,
                "response_format": {"type": "json_object"},
                "messages": messages,
            }
            try:
                res = self._call_api("/chat/completions", json_data=payload)
                self.active_chat_model = model_name
                return res
            except Exception as e:
                logger.warning(f"Chat model '{model_name}' failed: {e}")
                last_err = e
                continue

        raise GroqAPIError(f"All chat models failed. Last error: {last_err}", status_code=500)


groq_client = GroqClient()
