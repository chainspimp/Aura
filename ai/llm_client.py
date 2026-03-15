"""
ai/llm_client.py — AURA Centralized LLM Client

Single place for every Ollama call in the project.
Every feature — chat, coding, thinking, planning, routing,
hacker agent, VM agent, OSINT, self-improvement — uses this.

Features:
  • Automatic retry with exponential backoff
  • Streaming support (yields tokens one by one)
  • Per-model timeout config (coding needs longer than routing)
  • Ollama health check + auto-restart via ServiceManager
  • Consistent error handling and logging everywhere
  • Generation stats (tokens/sec, duration) on every call
  • Thread-safe singleton — one client, shared across all modules
"""

import json
import time
import logging
import threading
import subprocess
import requests
from typing import Generator, Optional, Dict, Any, Callable

from config import OLLAMA_API_URL

logger = logging.getLogger(__name__)

# ── Per-model timeout overrides (seconds) ─────────────────────────────────────
# Routing calls need to be fast. Coding calls can take minutes.
_MODEL_TIMEOUTS: Dict[str, int] = {
    # fast models — routing, planning, short answers
    "default":   120,
    "routing":    30,   # decision.py tool router
    "planning":  120,   # planner.py
    "thinking":  180,   # deepseek-r1
    "coding":    600,   # deepseek-coder — long files
    "vision":     60,   # vision model
    "chat":      200,   # main conversation
}

# ── Retry config ───────────────────────────────────────────────────────────────
MAX_RETRIES    = 3
RETRY_BACKOFF  = [1, 3, 7]   # seconds between retries


# ══════════════════════════════════════════════════════════════════════════════
# CORE CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class LLMClient:
    """
    Thread-safe Ollama client.
    Use the module-level helpers (call, stream, route) instead of
    instantiating this directly — they use the shared singleton.
    """

    def __init__(self, base_url: str = OLLAMA_API_URL):
        self._base_url  = base_url
        self._lock      = threading.Lock()
        self._stats     = {
            "total_calls":    0,
            "total_failures": 0,
            "total_tokens":   0,
            "total_time":     0.0,
        }

    # ── Public: blocking call ─────────────────────────────────────────────────

    def call(
        self,
        model:       str,
        prompt:      str,
        system:      str   = "",
        temperature: float = 0.7,
        max_tokens:  int   = 800,
        timeout_key: str   = "default",
        images:      list  = None,     # for vision calls — list of base64 strings
    ) -> str:
        """
        Make a blocking LLM call. Returns the response string.
        Retries automatically on failure with exponential backoff.
        Returns empty string if all retries fail (never raises).
        """
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        timeout     = _MODEL_TIMEOUTS.get(timeout_key, _MODEL_TIMEOUTS["default"])
        payload     = self._build_payload(model, full_prompt, False,
                                          temperature, max_tokens, images)
        start       = time.time()

        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.post(self._base_url, json=payload, timeout=timeout)
                resp.raise_for_status()
                data   = resp.json()
                result = data.get("response", "").strip()

                self._record_success(time.time() - start, data)
                return result

            except requests.exceptions.ConnectionError:
                logger.warning(f"Ollama not reachable (attempt {attempt + 1}/{MAX_RETRIES}) "
                               f"— is 'ollama serve' running?")
                self._maybe_restart_ollama()

            except requests.exceptions.Timeout:
                logger.warning(f"Ollama timeout after {timeout}s "
                               f"(attempt {attempt + 1}/{MAX_RETRIES}, model={model})")

            except requests.exceptions.HTTPError as e:
                logger.error(f"Ollama HTTP error: {e} (model={model})")
                # 4xx errors won't fix themselves — don't retry
                if resp.status_code < 500:
                    break

            except Exception as e:
                logger.error(f"LLM call error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")

            self._record_failure()
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

        logger.error(f"All {MAX_RETRIES} attempts failed for model={model}")
        return ""

    # ── Public: streaming call ────────────────────────────────────────────────

    def stream(
        self,
        model:       str,
        prompt:      str,
        system:      str   = "",
        temperature: float = 0.7,
        max_tokens:  int   = 4096,
        timeout_key: str   = "default",
        on_token:    Optional[Callable[[str], None]] = None,
    ) -> Generator[str, None, None]:
        """
        Stream tokens from the LLM one at a time.
        Yields each token as it arrives.
        Optionally calls on_token(token) callback for GUI updates.

        Usage:
            for token in client.stream(model, prompt):
                print(token, end="", flush=True)

        Or with callback:
            client.stream(model, prompt, on_token=gui.append_token)
        """
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        timeout     = _MODEL_TIMEOUTS.get(timeout_key, _MODEL_TIMEOUTS["default"])
        payload     = self._build_payload(model, full_prompt, True,
                                          temperature, max_tokens, None)
        start       = time.time()
        token_count = 0

        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.post(
                    self._base_url, json=payload,
                    stream=True, timeout=timeout
                )
                resp.raise_for_status()

                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    token = chunk.get("response", "")
                    if token:
                        token_count += 1
                        if on_token:
                            on_token(token)
                        yield token

                    if chunk.get("done"):
                        duration = time.time() - start
                        self._record_success(duration, chunk, token_count)
                        return

                return  # clean exit

            except requests.exceptions.ConnectionError:
                logger.warning(f"Stream: Ollama not reachable (attempt {attempt + 1}/{MAX_RETRIES})")
                self._maybe_restart_ollama()

            except requests.exceptions.Timeout:
                logger.warning(f"Stream: timeout after {timeout}s (model={model})")

            except Exception as e:
                logger.error(f"Stream error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")

            self._record_failure()
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                logger.info(f"Retrying stream in {wait}s...")
                time.sleep(wait)
            else:
                yield f"\n[Error: Ollama unreachable after {MAX_RETRIES} attempts]\n"

    # ── Public: collect stream into string ────────────────────────────────────

    def stream_to_str(
        self,
        model:       str,
        prompt:      str,
        system:      str   = "",
        temperature: float = 0.7,
        max_tokens:  int   = 4096,
        timeout_key: str   = "default",
        on_token:    Optional[Callable[[str], None]] = None,
    ) -> str:
        """Convenience: stream but collect all tokens and return as a string."""
        return "".join(self.stream(
            model, prompt, system, temperature,
            max_tokens, timeout_key, on_token
        ))

    # ── Public: check Ollama is alive ─────────────────────────────────────────

    def is_available(self) -> bool:
        """Quick health check — returns True if Ollama responds."""
        try:
            url = self._base_url.replace("/api/generate", "/api/tags")
            resp = requests.get(url, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def get_available_models(self) -> list:
        """Return list of model names currently pulled in Ollama."""
        try:
            url  = self._base_url.replace("/api/generate", "/api/tags")
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception as e:
            logger.error(f"Could not fetch models: {e}")
            return []

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            s = dict(self._stats)
        avg_time = (
            s["total_time"] / s["total_calls"]
            if s["total_calls"] > 0 else 0.0
        )
        tps = (
            s["total_tokens"] / s["total_time"]
            if s["total_time"] > 0 else 0.0
        )
        return {
            **s,
            "avg_response_time_s": round(avg_time, 2),
            "tokens_per_sec":      round(tps, 1),
            "success_rate":        round(
                (s["total_calls"] - s["total_failures"]) / max(s["total_calls"], 1) * 100, 1
            ),
        }

    def reset_stats(self):
        with self._lock:
            self._stats = {
                "total_calls": 0, "total_failures": 0,
                "total_tokens": 0, "total_time": 0.0,
            }

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _build_payload(
        model: str, prompt: str, stream: bool,
        temperature: float, max_tokens: int,
        images: Optional[list]
    ) -> dict:
        payload: Dict[str, Any] = {
            "model":   model,
            "prompt":  prompt,
            "stream":  stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if images:
            payload["images"] = images
        return payload

    def _record_success(self, duration: float, data: dict, tokens: int = 0):
        token_count = tokens or data.get("eval_count", 0)
        with self._lock:
            self._stats["total_calls"]  += 1
            self._stats["total_time"]   += duration
            self._stats["total_tokens"] += token_count

    def _record_failure(self):
        with self._lock:
            self._stats["total_calls"]    += 1
            self._stats["total_failures"] += 1

    def _maybe_restart_ollama(self):
        """Attempt to start Ollama if it's not running."""
        logger.info("Attempting to start Ollama...")
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(4)
            if self.is_available():
                logger.info("Ollama restarted successfully")
            else:
                logger.warning("Ollama still not responding after restart attempt")
        except FileNotFoundError:
            logger.error("'ollama' not found in PATH — is Ollama installed?")
        except Exception as e:
            logger.error(f"Ollama restart failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# Import and use these module-level functions everywhere in the project.
# Never instantiate LLMClient directly in feature code.
# ══════════════════════════════════════════════════════════════════════════════

_client: Optional[LLMClient] = None
_client_lock = threading.Lock()


def get_client() -> LLMClient:
    """Return the shared LLMClient singleton."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = LLMClient()
    return _client


# ══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL HELPERS
# These are what every file in the project should import and use.
# They all route through the singleton with the right timeout key.
# ══════════════════════════════════════════════════════════════════════════════

def llm_call(
    model:       str,
    prompt:      str,
    system:      str   = "",
    temperature: float = 0.7,
    max_tokens:  int   = 800,
    timeout_key: str   = "default",
    images:      list  = None,
) -> str:
    """
    Blocking LLM call. Use this everywhere instead of requests.post().

    Example (replacing old pattern):
        # OLD — don't do this:
        resp = requests.post(OLLAMA_API_URL, json={...}, timeout=30)
        result = resp.json().get("response", "")

        # NEW:
        from ai.llm_client import llm_call
        result = llm_call(OLLAMA_MODEL, prompt, temperature=0.7)
    """
    return get_client().call(
        model=model, prompt=prompt, system=system,
        temperature=temperature, max_tokens=max_tokens,
        timeout_key=timeout_key, images=images,
    )


def llm_stream(
    model:       str,
    prompt:      str,
    system:      str   = "",
    temperature: float = 0.7,
    max_tokens:  int   = 4096,
    timeout_key: str   = "default",
    on_token:    Optional[Callable[[str], None]] = None,
) -> Generator[str, None, None]:
    """
    Streaming LLM call — yields tokens as they arrive.

    Example:
        for token in llm_stream(OLLAMA_MODEL, prompt):
            gui.append(token)
    """
    yield from get_client().stream(
        model=model, prompt=prompt, system=system,
        temperature=temperature, max_tokens=max_tokens,
        timeout_key=timeout_key, on_token=on_token,
    )


def llm_stream_str(
    model:       str,
    prompt:      str,
    system:      str   = "",
    temperature: float = 0.7,
    max_tokens:  int   = 4096,
    timeout_key: str   = "default",
    on_token:    Optional[Callable[[str], None]] = None,
) -> str:
    """Stream and collect into a full string. Use when you need streaming
    progress callbacks but also want the final result as one string."""
    return get_client().stream_to_str(
        model=model, prompt=prompt, system=system,
        temperature=temperature, max_tokens=max_tokens,
        timeout_key=timeout_key, on_token=on_token,
    )


# Convenience shortcuts with correct timeout keys baked in
def chat_call(model: str, prompt: str, system: str = "", temperature: float = 0.7) -> str:
    """Main conversation call."""
    return llm_call(model, prompt, system, temperature, max_tokens=600, timeout_key="chat")


def route_call(model: str, prompt: str) -> str:
    """Fast tool routing call — strict 30s timeout."""
    return llm_call(model, prompt, temperature=0, max_tokens=200, timeout_key="routing")


def think_call(model: str, prompt: str, system: str = "") -> str:
    """Deep thinking call — extended timeout for reasoning models."""
    return llm_call(model, prompt, system, temperature=0.7, max_tokens=1200, timeout_key="thinking")


def code_call(model: str, prompt: str, system: str = "", on_token: Callable = None) -> str:
    """Code generation — longest timeout, streaming for live display."""
    return llm_stream_str(model, prompt, system, temperature=0.15,
                          max_tokens=16384, timeout_key="coding", on_token=on_token)


def plan_call(model: str, prompt: str) -> str:
    """Planning call — moderate timeout, low temperature for consistency."""
    return llm_call(model, prompt, temperature=0.2, max_tokens=1000, timeout_key="planning")


def vision_call(model: str, prompt: str, images: list) -> str:
    """Vision/VLM call with base64 image(s)."""
    return llm_call(model, prompt, temperature=0.5, max_tokens=400,
                    timeout_key="vision", images=images)


def is_ollama_running() -> bool:
    """Quick check — use this on startup to validate Ollama is available."""
    return get_client().is_available()


def llm_stats() -> Dict[str, Any]:
    """Return generation stats for debug panel or logs."""
    return get_client().stats()
