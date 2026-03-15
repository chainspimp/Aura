# ============================================
# FILE: thinking.py
# Fixed: unbounded cache replaced with a bounded LRU cache (max 128 entries)
# ============================================

import time
import hashlib
import requests
import logging
from collections import OrderedDict
from typing import Tuple
from config import OLLAMA_API_URL, OLLAMA_THINKING_MODEL

logger = logging.getLogger(__name__)

_CACHE_MAX = 128


class _LRUCache:
    """Simple thread-unsafe LRU cache — fine for single-threaded inference loop."""

    def __init__(self, maxsize: int = _CACHE_MAX):
        self._store: OrderedDict[str, Tuple[str, str]] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> Tuple[str, str] | None:
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return None

    def set(self, key: str, value: Tuple[str, str]):
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        if len(self._store) > self._maxsize:
            self._store.popitem(last=False)  # evict oldest


class ThinkingSystem:
    """Advanced reasoning using a specialized reasoning model."""

    def __init__(self):
        self._cache = _LRUCache(maxsize=_CACHE_MAX)

    def deep_think(self, problem: str, context: str = "") -> Tuple[str, str]:
        print("🧠 Deep thinking mode activated...")

        cache_key = hashlib.md5(f"{problem}{context}".encode()).hexdigest()
        cached = self._cache.get(cache_key)
        if cached:
            print("💭 Using cached thoughts")
            return cached

        thinking_prompt = f"""You are an advanced reasoning system. Think deeply about this problem step by step.

Problem: {problem}

Context: {context}

Think through this carefully:
1. Break down the problem
2. Consider different approaches
3. Reason through implications
4. Arrive at a well-reasoned conclusion

Provide your reasoning process and final answer."""

        try:
            resp = requests.post(
                OLLAMA_API_URL,
                json={
                    "model": OLLAMA_THINKING_MODEL,
                    "prompt": thinking_prompt,
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 800}
                },
                timeout=120
            )
            resp.raise_for_status()
            reasoning = resp.json().get("response", "").strip()

            if "conclusion:" in reasoning.lower():
                parts = reasoning.lower().split("conclusion:")
                thinking_process = parts[0].strip()
                conclusion = parts[1].strip() if len(parts) > 1 else reasoning
            else:
                thinking_process = reasoning
                conclusion = reasoning

            result = (thinking_process, conclusion)
            self._cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Thinking error: {e}")
            return "", f"Thinking failed: {e}"