import os
import json
from dotenv import load_dotenv

load_dotenv()

# Paths
PIPER_PATH = os.environ.get("PIPER_PATH", r"C:\Users\Chains\Desktop\Projects\piper-tts\piper\piper.exe")
PIPER_MODEL = os.environ.get("PIPER_MODEL", r"C:\Users\Chains\Desktop\Projects\piper-tts\piper\voices\en_US-hfc_female-medium.onnx")
VOSK_MODEL_PATH = os.environ.get("VOSK_MODEL_PATH", r"C:\Users\Chains\Desktop\Projects\Aura\AuraV2\vosk-model-small-en-us-0.15")

# Files
MEMORY_FILE = "aura_memory.json"
CONFIG_FILE = "aura_config.json"

# API
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3n:e2b")
OLLAMA_HACK = os.environ.get("OLLAMA_HACK", "xploiter/pentester:latest")
OLLAMA_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "qwen3-vl:2b")
OLLAMA_THINKING_MODEL = os.environ.get("OLLAMA_THINKING_MODEL", "deepseek-r1:8b")
OLLAMA_CODING_MODEL = os.environ.get("OLLAMA_CODING_MODEL", "deepseek-coder-v2:16b")
OLLAMA_COMPUTER_VISION_MODEL =os.environ.get("OLLAMA_CODING_MODEL", "qwen2.5-vl:7b") # Screen reading + UI element finding
OLLAMA_COMPUTER_PLAN_MODEL   = os.environ.get("OLLAMA_CODING_MODEL", "gemma3n:e2b")    # Action planning — uses main model (fast)

# ACRCloud music recognition — set these in your .env file, never hardcode
ACR_HOST = os.environ.get("ACR_HOST", "identify-us-west-2.acrcloud.com")
ACR_ACCESS_KEY = os.environ.get("ACR_ACCESS_KEY", "")
ACR_ACCESS_SECRET = os.environ.get("ACR_ACCESS_SECRET", "")

# Audio
SAMPLE_RATE = 16000
CHUNK_SIZE = 4000
LISTEN_TIMEOUT = 8

# Memory
MAX_MEMORY_ENTRIES = 100
MAX_CONTEXT_ENTRIES = 15

# Output
IMAGE_OUTPUT_DIR = "generated_images"
CODE_OUTPUT_DIR = "generated_code"
os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)
os.makedirs(CODE_OUTPUT_DIR, exist_ok=True)

def load_config():
    default = {
        "voice_enabled": True,
        "vision_enabled": True,
        "auto_visual_context": True,
        "response_timeout": 200,
        "max_tts_length": 500,
        "debug_mode": False,
        "audio_method": "auto",
        "use_vad": True,
        "enable_thinking": True,
        "enable_web_search": True,
        "enable_coding": True
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                default.update(json.load(f))
    except Exception:
        pass
    return default

def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Config save error: {e}")