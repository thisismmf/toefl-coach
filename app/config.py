"""Runtime settings. Everything here can be overridden live from the UI."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
CHART_DIR = DATA_DIR / "charts"
STATIC_DIR = ROOT / "static"
DB_PATH = DATA_DIR / "toefl.db"

for d in (DATA_DIR, CHART_DIR):
    d.mkdir(parents=True, exist_ok=True)

HOST = os.getenv("TOEFL_HOST", "127.0.0.1")
PORT = int(os.getenv("TOEFL_PORT", "8781"))

DEFAULTS = {
    "provider": os.getenv("TOEFL_PROVIDER", "ollama"),
    "model": os.getenv("TOEFL_MODEL", "qwen3-vl:8b"),
    "temperature": 0.2,
    "num_ctx": 8192,
}

PROVIDERS = {
    "ollama": {
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "api_key": os.getenv("OLLAMA_API_KEY"),
        "label": "Ollama (local)",
    },
    "ollama_cloud": {
        # Cloud models are served by ollama.com, not by the local daemon.
        "base_url": os.getenv("OLLAMA_CLOUD_BASE_URL", "https://ollama.com"),
        "api_key": os.getenv("OLLAMA_API_KEY"),
        "label": "Ollama Cloud",
    },
    "openai": {
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "api_key": os.getenv("OPENAI_API_KEY"),
        "label": "OpenAI-compatible",
    },
    "anthropic": {
        "base_url": os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "label": "Anthropic",
    },
}
