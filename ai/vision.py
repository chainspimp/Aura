# ============================================
# FILE: vision.py
# Fixed: VisionCache now uses a proper O(1) LRU via OrderedDict instead of O(n) min()
# ============================================

import cv2
import base64
import hashlib
import requests
import logging
from collections import OrderedDict
from PIL import Image
from io import BytesIO
from config import OLLAMA_API_URL, OLLAMA_VISION_MODEL

logger = logging.getLogger(__name__)


class VisionCache:
    """LRU cache for vision inference results."""

    def __init__(self, maxsize: int = 50):
        self._store: OrderedDict[str, str] = OrderedDict()
        self._maxsize = maxsize

    def _key(self, img: Image.Image, prompt: str) -> str:
        img_hash = hashlib.md5(img.tobytes()).hexdigest()
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        return f"{img_hash}_{prompt_hash}"

    def get(self, img: Image.Image, prompt: str) -> str | None:
        key = self._key(img, prompt)
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return None

    def set(self, img: Image.Image, prompt: str, resp: str):
        key = self._key(img, prompt)
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = resp
        if len(self._store) > self._maxsize:
            self._store.popitem(last=False)  # evict LRU entry


vision_cache = VisionCache()


def grab_frame(device: int = 0) -> Image.Image | None:
    cap = None
    try:
        cap = cv2.VideoCapture(device)
        if not cap.isOpened():
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # Flush warm-up frames
        for _ in range(3):
            cap.read()

        for _ in range(5):
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0 and frame.mean() > 10:
                return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    except Exception as e:
        logger.error(f"grab_frame error: {e}")
    finally:
        if cap is not None:
            cap.release()
    return None


def pil_to_b64(img: Image.Image) -> str:
    try:
        if img.size[0] > 800 or img.size[1] > 600:
            img = img.copy()
            img.thumbnail((800, 600), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.error(f"pil_to_b64 error: {e}")
        return ""


def describe_frame(img: Image.Image, prompt: str | None = None) -> str:
    prompt = prompt or "Describe what you see in this image. Be concise."

    cached = vision_cache.get(img, prompt)
    if cached:
        return cached

    b64 = pil_to_b64(img)
    if not b64:
        return "Can't process image."

    try:
        resp = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_VISION_MODEL,
                "prompt": prompt,
                "images": [b64],
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 200}
            },
            timeout=60
        )
        resp.raise_for_status()
        result = resp.json().get("response", "").strip()

        if result:
            vision_cache.set(img, prompt, result)
        return result or "Can't describe image."

    except Exception as e:
        logger.error(f"describe_frame error: {e}")
        return "Vision unavailable."


def get_visual_context(force: bool = False) -> str:
    try:
        img = grab_frame()
        if img:
            return describe_frame(img, "Briefly describe the current scene.")
    except Exception as e:
        logger.error(f"get_visual_context error: {e}")
    return "Camera unavailable."