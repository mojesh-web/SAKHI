import os


def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
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
        except Exception:
            pass


load_env_file()

# Default to production/secure settings unless explicitly overridden
DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

# Groq Configuration
GROQ_API_KEYS = os.environ.get("GROQ_API_KEYS", "")
if not GROQ_API_KEYS:
    GROQ_API_KEYS = os.environ.get("GROQ_API_KEY", "")

# We will validate API keys early in the GroqClient, but store raw here
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_STT_MODEL = "whisper-large-v3"
GROQ_CHAT_MODELS = [
    os.environ.get("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile"),
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
]

# Audio constraints
MAX_AUDIO_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MIN_AUDIO_SIZE_BYTES = 500

# Chat constraints
MAX_CHAT_HISTORY = 8
MAX_TOKENS = 300
TEMPERATURE = 0.3
STT_TEMPERATURE = 0.0

# Rate Limiting
RATELIMIT_DEFAULT = "50 per minute"
