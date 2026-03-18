# =============================================================================
# FILE: config.py  (UPDATED — cross-platform + new feature flags)
# =============================================================================

import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── Platform-aware path resolution ───────────────────────────────────────────
# Import is deferred to avoid circular imports, but platform_compat drives paths
try:
    from platform_compat import get_piper_path, get_piper_model, get_vosk_model_path
    _PIPER_PATH  = get_piper_path()  or ""
    _PIPER_MODEL = get_piper_model() or ""
    _VOSK_PATH   = get_vosk_model_path() or ""
except ImportError:
    _PIPER_PATH  = ""
    _PIPER_MODEL = ""
    _VOSK_PATH   = ""

# Allow .env overrides to win
PIPER_PATH      = os.environ.get("PIPER_PATH",      _PIPER_PATH)
PIPER_MODEL     = os.environ.get("PIPER_MODEL",     _PIPER_MODEL)
VOSK_MODEL_PATH = os.environ.get("VOSK_MODEL_PATH", _VOSK_PATH)

# ── Files ─────────────────────────────────────────────────────────────────────
MEMORY_FILE = str(Path(os.environ.get("AURA_DATA_DIR", ".")) / "aura_memory.json")
CONFIG_FILE = str(Path(os.environ.get("AURA_DATA_DIR", ".")) / "aura_config.json")

# ── Ollama API ────────────────────────────────────────────────────────────────
OLLAMA_API_URL   = os.environ.get("OLLAMA_API_URL",   "http://localhost:11434/api/generate")
OLLAMA_MODEL     = os.environ.get("OLLAMA_MODEL",     "gemma3n:e2b")
OLLAMA_HACK      = os.environ.get("OLLAMA_HACK",      "xploiter/pentester:latest")
OLLAMA_VISION_MODEL  = os.environ.get("OLLAMA_VISION_MODEL",  "qwen3-vl:2b")
OLLAMA_THINKING_MODEL = os.environ.get("OLLAMA_THINKING_MODEL", "deepseek-r1:8b")
OLLAMA_CODING_MODEL  = os.environ.get("OLLAMA_CODING_MODEL",  "deepseek-coder-v2:16b")
OLLAMA_COMPUTER_VISION_MODEL = os.environ.get("OLLAMA_COMPUTER_VISION_MODEL", "qwen2.5-vl:7b")
OLLAMA_COMPUTER_PLAN_MODEL   = os.environ.get("OLLAMA_COMPUTER_PLAN_MODEL",   "gemma3n:e2b")

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN       = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_ALLOWED_IDS = os.environ.get("TELEGRAM_ALLOWED_IDS", "")

# ── Music recognition ─────────────────────────────────────────────────────────
ACR_HOST          = os.environ.get("ACR_HOST",          "identify-us-west-2.acrcloud.com")
ACR_ACCESS_KEY    = os.environ.get("ACR_ACCESS_KEY",    "")
ACR_ACCESS_SECRET = os.environ.get("ACR_ACCESS_SECRET", "")

# ── Audio ─────────────────────────────────────────────────────────────────────
SAMPLE_RATE  = 16000
CHUNK_SIZE   = 4000
LISTEN_TIMEOUT = 8

# ── Memory ────────────────────────────────────────────────────────────────────
MAX_MEMORY_ENTRIES  = 100
MAX_CONTEXT_ENTRIES = 15

# ── Output directories ────────────────────────────────────────────────────────
IMAGE_OUTPUT_DIR = os.environ.get("AURA_IMAGE_DIR", "generated_images")
CODE_OUTPUT_DIR  = os.environ.get("AURA_CODE_DIR",  "generated_code")
os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)
os.makedirs(CODE_OUTPUT_DIR,  exist_ok=True)


# =============================================================================
# RUNTIME CONFIG  (aura_config.json)
# =============================================================================

def load_config() -> dict:
    default = {
        # Existing settings
        "voice_enabled":        True,
        "vision_enabled":       True,
        "auto_visual_context":  False,
        "response_timeout":     200,
        "max_tts_length":       500,
        "debug_mode":           False,
        "audio_method":         "auto",
        "use_vad":              True,
        "enable_thinking":      False,
        "enable_web_search":    True,
        "enable_coding":        False,

        # New feature flags
        "enable_skills":        True,     # Skills plugin system
        "enable_browser":       True,     # Playwright browser control
        "enable_scheduler":     True,     # Proactive scheduler daemon
        "enable_telegram_bot":  False,    # Telegram remote interface
        "browser_headless":     True,     # Run browser in headless mode
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Merge so new defaults aren't lost on upgrade
                default.update(data)
    except Exception as e:
        logger.warning(f"Config load error (using defaults): {e}")
    return default


def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logger.error(f"Config save error: {e}")
