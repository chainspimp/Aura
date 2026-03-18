# =============================================================================
# FILE: platform_compat.py
# AURA Cross-Platform Compatibility Layer
#
# Detects OS and provides platform-appropriate:
#   - TTS (Piper on Windows, espeak/say on Linux/macOS)
#   - Voice input paths
#   - App launcher shortcuts
#   - File paths and default dirs
#   - Process management
#
# Import this instead of hardcoding platform checks throughout the codebase.
# =============================================================================

import os
import sys
import shutil
import platform
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# ── OS detection ──────────────────────────────────────────────────────────────

SYSTEM   = platform.system()      # "Windows", "Linux", "Darwin"
IS_WIN   = SYSTEM == "Windows"
IS_LINUX = SYSTEM == "Linux"
IS_MAC   = SYSTEM == "Darwin"


# =============================================================================
# PATH RESOLUTION
# =============================================================================

def find_executable(name: str, candidates: List[str] = None) -> Optional[str]:
    """
    Find an executable by name. Checks PATH first, then a candidate list.
    Returns the full path or None.
    """
    found = shutil.which(name)
    if found:
        return found
    for candidate in (candidates or []):
        if Path(candidate).is_file():
            return candidate
    return None


def get_piper_path() -> Optional[str]:
    """Locate the Piper TTS executable for the current platform."""
    env_path = os.environ.get("PIPER_PATH")
    if env_path and Path(env_path).is_file():
        return env_path

    if IS_WIN:
        candidates = [
            r"C:\Users\Chains\Desktop\Projects\piper-tts\piper\piper.exe",
            r"C:\piper\piper.exe",
            str(Path.home() / "piper" / "piper.exe"),
        ]
    elif IS_MAC:
        candidates = [
            "/usr/local/bin/piper",
            str(Path.home() / ".local" / "bin" / "piper"),
            str(Path.home() / "piper" / "piper"),
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/piper",
            "/usr/local/bin/piper",
            str(Path.home() / ".local" / "bin" / "piper"),
            str(Path.home() / "piper" / "piper"),
        ]

    return find_executable("piper", candidates)


def get_piper_model() -> Optional[str]:
    """Locate the default Piper voice model."""
    env_path = os.environ.get("PIPER_MODEL")
    if env_path and Path(env_path).is_file():
        return env_path

    if IS_WIN:
        search_roots = [
            Path(r"C:\Users\Chains\Desktop\Projects\piper-tts\piper\voices"),
            Path.home() / "piper" / "voices",
        ]
    else:
        search_roots = [
            Path.home() / ".local" / "share" / "piper" / "voices",
            Path.home() / "piper" / "voices",
            Path("/usr/share/piper/voices"),
        ]

    for root in search_roots:
        if root.exists():
            # Find first .onnx file
            for f in root.glob("**/*.onnx"):
                return str(f)
    return None


def get_vosk_model_path() -> Optional[str]:
    """Locate the Vosk speech recognition model directory."""
    env_path = os.environ.get("VOSK_MODEL_PATH")
    if env_path and Path(env_path).is_dir():
        return env_path

    search_roots = [
        Path.cwd(),
        Path.home() / "vosk-models",
        Path.home() / ".local" / "share" / "vosk",
    ]
    if IS_WIN:
        search_roots.insert(0, Path(r"C:\Users\Chains\Desktop\Projects\Aura\AuraV2"))

    for root in search_roots:
        if not root.exists():
            continue
        for d in root.iterdir():
            if d.is_dir() and "vosk" in d.name.lower():
                # Check it's a valid model (has conf/ or am/)
                if (d / "conf").exists() or (d / "am").exists():
                    return str(d)
    return None


# =============================================================================
# TTS  (Text-to-Speech)
# =============================================================================

class TTSBackend:
    """Unified TTS interface that works on Windows, Linux, and macOS."""

    def speak(self, text: str, max_length: int = 500):
        text = text[:max_length]
        if not text.strip():
            return
        backend = self._detect_backend()
        if backend == "piper":
            self._speak_piper(text)
        elif backend == "espeak":
            self._speak_espeak(text)
        elif backend == "say":
            self._speak_say(text)
        elif backend == "sapi":
            self._speak_sapi(text)
        else:
            logger.warning("No TTS backend available.")

    def _detect_backend(self) -> str:
        if get_piper_path():
            return "piper"
        if IS_MAC and shutil.which("say"):
            return "say"
        if IS_LINUX and shutil.which("espeak"):
            return "espeak"
        if IS_LINUX and shutil.which("espeak-ng"):
            return "espeak"
        if IS_WIN:
            return "sapi"
        return "none"

    def _speak_piper(self, text: str):
        piper  = get_piper_path()
        model  = get_piper_model()
        if not piper or not model:
            return self._speak_espeak(text) if IS_LINUX else None
        import tempfile, pygame
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            proc = subprocess.run(
                [piper, "--model", model, "--output_file", wav_path],
                input=text.encode(),
                capture_output=True,
                timeout=30
            )
            if proc.returncode == 0 and Path(wav_path).exists():
                try:
                    pygame.mixer.init()
                    pygame.mixer.music.load(wav_path)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        pygame.time.wait(50)
                except Exception as e:
                    logger.warning(f"Pygame playback failed: {e}")
        finally:
            try:
                os.unlink(wav_path)
            except Exception:
                pass

    def _speak_espeak(self, text: str):
        cmd = shutil.which("espeak-ng") or shutil.which("espeak") or "espeak"
        try:
            subprocess.run([cmd, "-s", "160", text], timeout=30)
        except Exception as e:
            logger.warning(f"espeak failed: {e}")

    def _speak_say(self, text: str):
        """macOS built-in TTS."""
        try:
            subprocess.run(["say", text], timeout=30)
        except Exception as e:
            logger.warning(f"say failed: {e}")

    def _speak_sapi(self, text: str):
        """Windows SAPI via PowerShell (no extra libs needed)."""
        try:
            ps_cmd = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Speak('{text.replace(chr(39), '')}');"
            )
            subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True,
                timeout=30
            )
        except Exception as e:
            logger.warning(f"SAPI TTS failed: {e}")


# =============================================================================
# APP LAUNCHER
# =============================================================================

# Platform-specific app shortcut tables
_APP_SHORTCUTS_WIN: Dict[str, List[str]] = {
    "chrome":       [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"),
        "chrome",
    ],
    "firefox":      ["C:/Program Files/Mozilla Firefox/firefox.exe", "firefox"],
    "edge":         [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "msedge"],
    "vscode":       [
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        str(Path.home() / "AppData/Local/Programs/Microsoft VS Code/Code.exe"),
        "code",
    ],
    "spotify":      [str(Path.home() / "AppData/Roaming/Spotify/Spotify.exe"), "spotify"],
    "discord":      [str(Path.home() / "AppData/Local/Discord/Update.exe"), "discord"],
    "notepad":      ["notepad"],
    "calculator":   ["calc"],
    "explorer":     ["explorer"],
    "terminal":     ["wt", "cmd"],
    "powershell":   ["powershell"],
}

_APP_SHORTCUTS_LINUX: Dict[str, List[str]] = {
    "chrome":       ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
    "firefox":      ["firefox"],
    "vscode":       ["code", "code-oss"],
    "spotify":      ["spotify"],
    "discord":      ["discord"],
    "terminal":     ["gnome-terminal", "konsole", "xterm", "xfce4-terminal", "tilix"],
    "calculator":   ["gnome-calculator", "kcalc", "xcalc"],
    "files":        ["nautilus", "dolphin", "thunar", "nemo"],
    "text editor":  ["gedit", "kate", "mousepad", "xed"],
}

_APP_SHORTCUTS_MAC: Dict[str, List[str]] = {
    "chrome":       ["open -a 'Google Chrome'"],
    "firefox":      ["open -a Firefox"],
    "vscode":       ["open -a 'Visual Studio Code'", "code"],
    "spotify":      ["open -a Spotify"],
    "discord":      ["open -a Discord"],
    "terminal":     ["open -a Terminal"],
    "safari":       ["open -a Safari"],
    "calculator":   ["open -a Calculator"],
    "finder":       ["open ."],
}


def launch_app(app_name: str) -> bool:
    """
    Launch an application by name. Returns True on success.
    Works on Windows, Linux, and macOS.
    """
    name_low = app_name.lower().strip()

    if IS_WIN:
        shortcuts = _APP_SHORTCUTS_WIN
    elif IS_MAC:
        shortcuts = _APP_SHORTCUTS_MAC
    else:
        shortcuts = _APP_SHORTCUTS_LINUX

    # Try known shortcuts
    for shortcut_key, cmds in shortcuts.items():
        if shortcut_key in name_low or name_low in shortcut_key:
            for cmd in cmds:
                try:
                    # macOS 'open -a ...' needs shell=True
                    use_shell = IS_MAC and cmd.startswith("open")
                    if use_shell:
                        subprocess.Popen(cmd, shell=True)
                    else:
                        executable = cmd if Path(cmd).is_file() else shutil.which(cmd) or cmd
                        subprocess.Popen([executable])
                    logger.info(f"Launched: {cmd}")
                    return True
                except Exception:
                    continue

    # Fallback: try launching the name directly
    try:
        subprocess.Popen([shutil.which(name_low) or name_low])
        return True
    except Exception:
        logger.warning(f"Could not launch: {app_name}")
        return False


# =============================================================================
# SCREEN CAPTURE (cross-platform)
# =============================================================================

def take_screenshot() -> Optional[bytes]:
    """Take a screenshot and return PNG bytes. Works on all platforms."""
    try:
        from PIL import ImageGrab, Image
        import io
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"PIL screenshot failed ({e}), trying scrot/gnome-screenshot")

    # Linux fallback
    if IS_LINUX:
        import tempfile
        for tool in ["scrot", "gnome-screenshot"]:
            if not shutil.which(tool):
                continue
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                path = tmp.name
            args = [tool, path] if tool == "scrot" else ["gnome-screenshot", "-f", path]
            try:
                subprocess.run(args, timeout=5, capture_output=True)
                if Path(path).exists():
                    data = Path(path).read_bytes()
                    os.unlink(path)
                    return data
            except Exception:
                continue
    return None


# =============================================================================
# CONFIG PATHS
# =============================================================================

def get_config_dir() -> Path:
    """Return the platform-appropriate config directory for AURA."""
    if IS_WIN:
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif IS_MAC:
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "AURA"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_data_dir() -> Path:
    """Return the platform-appropriate data directory for AURA."""
    if IS_WIN:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    elif IS_MAC:
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "AURA"
    d.mkdir(parents=True, exist_ok=True)
    return d


# =============================================================================
# DEPENDENCY CHECKER
# =============================================================================

def check_platform_deps() -> Dict[str, bool]:
    """
    Check which platform-specific dependencies are available.
    Returns a dict of {name: available}.
    """
    checks = {}

    # TTS
    checks["piper"]      = bool(get_piper_path())
    checks["espeak"]     = bool(shutil.which("espeak") or shutil.which("espeak-ng"))
    checks["say (macOS)"] = IS_MAC and bool(shutil.which("say"))

    # Speech recognition
    checks["vosk"]       = bool(get_vosk_model_path())

    # Vision
    checks["ffmpeg"]     = bool(shutil.which("ffmpeg"))

    # Browser
    try:
        import playwright
        checks["playwright"] = True
    except ImportError:
        checks["playwright"] = False

    # Scheduler
    try:
        import apscheduler
        checks["apscheduler"] = True
    except ImportError:
        checks["apscheduler"] = False

    # Telegram
    try:
        import telegram
        checks["python-telegram-bot"] = True
    except ImportError:
        checks["python-telegram-bot"] = False

    # Platform-specific
    if IS_LINUX:
        checks["pulseaudio/pipewire"] = (
            bool(shutil.which("pulseaudio")) or bool(shutil.which("pipewire"))
        )
        checks["portaudio"]  = _check_portaudio_linux()
        checks["scrot"]      = bool(shutil.which("scrot"))

    return checks


def _check_portaudio_linux() -> bool:
    """Check if PortAudio dev libs are installed on Linux (needed by pyaudio)."""
    try:
        result = subprocess.run(
            ["pkg-config", "--exists", "portaudio-2.0"],
            capture_output=True
        )
        return result.returncode == 0
    except Exception:
        # Try ldconfig as fallback
        try:
            result = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True)
            return "libportaudio" in result.stdout
        except Exception:
            return False


def print_deps_report():
    """Print a dependency status report to stdout."""
    print(f"\n🖥️  AURA Platform: {SYSTEM} ({platform.machine()})")
    print(f"🐍 Python: {platform.python_version()}\n")
    print("📦 Dependencies:")
    deps = check_platform_deps()
    for name, ok in deps.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    print()

    # Platform-specific install hints
    if IS_LINUX:
        missing = [k for k, v in deps.items() if not v]
        if missing:
            print("💡 Linux install hints:")
            hints = {
                "portaudio": "sudo apt install portaudio19-dev python3-pyaudio",
                "espeak":    "sudo apt install espeak-ng",
                "piper":     "Download from https://github.com/rhasspy/piper/releases",
                "playwright": "pip install playwright && playwright install chromium",
                "apscheduler": "pip install apscheduler",
                "python-telegram-bot": "pip install python-telegram-bot",
                "scrot":     "sudo apt install scrot",
                "ffmpeg":    "sudo apt install ffmpeg",
            }
            for m in missing:
                hint = hints.get(m)
                if hint:
                    print(f"  → {m}: {hint}")
    elif IS_MAC:
        print("💡 macOS: Install Homebrew deps with:  brew install portaudio espeak ffmpeg")

    print()


if __name__ == "__main__":
    print_deps_report()
