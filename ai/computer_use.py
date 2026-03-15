# ============================================
# FILE: ai/computer_use.py
# AURA Computer Use — Full Device Control
#
# Loop: Screenshot → Vision AI → Action Plan → Execute → Repeat
#
# Capabilities:
#   • Mouse move, click, double-click, right-click, drag
#   • Keyboard typing, hotkeys, key combos
#   • Screenshot + vision model to read the screen
#   • AI plans multi-step actions from plain English
#   • Self-verifies each step before moving on
#   • Opens apps, browses web, fills forms, clicks buttons
# ============================================

import os
import re
import sys
import time
import base64
import logging
import subprocess
from io import BytesIO
from typing import Optional, List, Dict, Callable, Tuple
from datetime import datetime

import requests
import pyautogui
import ctypes
from PIL import ImageGrab, Image, ImageDraw

from config import OLLAMA_API_URL, OLLAMA_MODEL, OLLAMA_VISION_MODEL, \
    OLLAMA_COMPUTER_VISION_MODEL, OLLAMA_COMPUTER_PLAN_MODEL

logger = logging.getLogger(__name__)

# Safety: pyautogui won't move mouse off screen and crash
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.3   # small pause between actions — looks natural

# ── Common app launch paths (Windows) ─────────────────────
APP_SHORTCUTS = {
    "chrome":       [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        "chrome",
    ],
    "firefox":      [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        "firefox",
    ],
    "edge":         [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "msedge",
    ],
    "spotify":      [
        os.path.expanduser(r"~\AppData\Roaming\Spotify\Spotify.exe"),
        os.path.expanduser(r"~\AppData\Local\Spotify\Spotify.exe"),
        "spotify",
    ],
    "notepad":      ["notepad"],
    "discord":      [
        os.path.expanduser(r"~\AppData\Local\Discord\Update.exe"),
        "discord",
    ],
    "vscode":       [
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Microsoft VS Code\Code.exe"),
        "code",
    ],
    "explorer":     ["explorer"],
    "task manager": ["taskmgr"],
    "calculator":   ["calc"],
    "paint":        ["mspaint"],
    "cmd":          ["cmd"],
    "powershell":   ["powershell"],
    "settings":     ["ms-settings:"],
    "steam":        [
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Program Files\Steam\steam.exe",
    ],
    "obs":          [r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"],
    "vlc":          [r"C:\Program Files\VideoLAN\VLC\vlc.exe"],
    "word":         ["winword"],
    "excel":        ["excel"],
    "outlook":      ["outlook"],
}

# ── Website shortcuts ──────────────────────────────────────
SITE_SHORTCUTS = {
    "youtube":   "https://www.youtube.com",
    "spotify":   "https://open.spotify.com",
    "github":    "https://github.com",
    "google":    "https://www.google.com",
    "gmail":     "https://mail.google.com",
    "reddit":    "https://www.reddit.com",
    "twitter":   "https://twitter.com",
    "x":         "https://x.com",
    "twitch":    "https://www.twitch.tv",
    "netflix":   "https://www.netflix.com",
    "amazon":    "https://www.amazon.com",
    "chatgpt":   "https://chat.openai.com",
}


# ═══════════════════════════════════════════════════════════
# SCREEN READER
# Takes screenshots and asks the vision model what it sees
# ═══════════════════════════════════════════════════════════

class ScreenReader:

    def screenshot(self) -> Image.Image:
        """Capture the full screen and return as PIL Image."""
        return ImageGrab.grab()

    def screenshot_b64(self, scale: float = 0.6) -> str:
        """
        Capture screen, downscale for faster vision inference,
        return as base64 JPEG string.
        """
        img = self.screenshot()
        w, h = img.size
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode()

    def describe(self, question: str = "What is currently on screen?") -> str:
        """Send a screenshot to the vision model and get a description."""
        b64 = self.screenshot_b64()
        try:
            resp = requests.post(
                OLLAMA_API_URL,
                json={
                    "model": OLLAMA_COMPUTER_VISION_MODEL,
                    "prompt": question,
                    "images": [b64],
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 400}
                },
                timeout=45
            )
            return resp.json().get("response", "").strip()
        except Exception as e:
            logger.error(f"Vision error: {e}")
            return f"Vision unavailable: {e}"

    def find_element(self, description: str) -> Optional[Tuple[int, int]]:
        """
        Ask the vision model where a UI element is on screen.
        Returns (x, y) pixel coords or None.
        """
        b64 = self.screenshot_b64()
        screen_w, screen_h = pyautogui.size()
        prompt = (
            f"Look at this screenshot. Find: '{description}'\n"
            f"Screen size: {screen_w}x{screen_h} pixels.\n"
            f"Return ONLY: x,y  (the pixel coordinates of the center of that element).\n"
            f"Example response: 450,320\n"
            f"If not found, return: NOT_FOUND"
        )
        try:
            resp = requests.post(
                OLLAMA_API_URL,
                json={
                    "model": OLLAMA_COMPUTER_VISION_MODEL,
                    "prompt": prompt,
                    "images": [b64],
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": 30}
                },
                timeout=45
            )
            raw = resp.json().get("response", "").strip()
            if "NOT_FOUND" in raw.upper():
                return None
            match = re.search(r'(\d+)\s*,\s*(\d+)', raw)
            if match:
                x, y = int(match.group(1)), int(match.group(2))
                # Scale back up if vision model saw a downscaled image
                scale = 1 / 0.6
                return (int(x * scale), int(y * scale))
        except Exception as e:
            logger.error(f"find_element error: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# VIRTUAL MOUSE
# Snaps real cursor to target, acts, then snaps back —
# so fast it appears invisible behind the blue overlay
# ═══════════════════════════════════════════════════════════

class VirtualMouse:
    @staticmethod
    def _get_pos():
        return pyautogui.position()

    @staticmethod
    def _send_click(x: int, y: int, button: str = "left", clicks: int = 1):
        """Snap to position, click, snap back — all within a few ms."""
        orig = pyautogui.position()
        ctypes.windll.user32.SetCursorPos(x, y)
        time.sleep(0.04)
        if button == "right":
            pyautogui.click(x, y, button="right")
        elif clicks == 2:
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.click(x, y)
        time.sleep(0.04)
        ctypes.windll.user32.SetCursorPos(orig.x, orig.y)

    @staticmethod
    def _send_drag(x1: int, y1: int, x2: int, y2: int):
        orig = pyautogui.position()
        ctypes.windll.user32.SetCursorPos(x1, y1)
        time.sleep(0.05)
        pyautogui.dragTo(x2, y2, duration=0.3, button="left")
        time.sleep(0.05)
        ctypes.windll.user32.SetCursorPos(orig.x, orig.y)


# ═══════════════════════════════════════════════════════════
# ACTION EXECUTOR
# Shows blue AURA cursor moving to each target, then acts
# ═══════════════════════════════════════════════════════════

class ActionExecutor:

    def __init__(self, screen: ScreenReader):
        self.screen  = screen
        self.vmouse  = VirtualMouse()
        self._overlay = None

    def _get_overlay(self):
        if self._overlay is None:
            try:
                from ai.cursor_overlay import get_overlay
                self._overlay = get_overlay()
            except Exception as e:
                logger.warning(f"Overlay unavailable: {e}")
        return self._overlay

    def _move_overlay(self, x: int, y: int, label: str = ""):
        ov = self._get_overlay()
        if ov:
            try:
                ov.move_to(x, y, label=label)
            except Exception:
                pass

    def _pulse_overlay(self):
        ov = self._get_overlay()
        if ov:
            try:
                ov.pulse()
            except Exception:
                pass

    def execute(self, action: Dict) -> str:
        atype = action.get("type", "").lower()

        try:
            if atype == "open_app":
                return self._open_app(action.get("app", ""))

            elif atype == "open_url":
                return self._open_url(action.get("url", ""))

            elif atype == "search_on_site":
                return self.search_on_site(action.get("site", "google"), action.get("query", ""))

            elif atype == "click":
                return self._click(action, clicks=1, button="left")

            elif atype == "double_click":
                return self._click(action, clicks=2, button="left")

            elif atype == "right_click":
                return self._click(action, clicks=1, button="right")

            elif atype == "type":
                text = action.get("text", "")
                time.sleep(0.2)
                pyautogui.write(text, interval=0.04)
                return f"Typed: {text[:50]}"

            elif atype == "hotkey":
                keys = action.get("keys", "")
                key_list = [k.strip() for k in keys.replace("+", " ").split()]
                pyautogui.hotkey(*key_list)
                return f"Hotkey: {keys}"

            elif atype == "press":
                key = action.get("key", "enter")
                pyautogui.press(key)
                return f"Pressed: {key}"

            elif atype == "scroll":
                x = action.get("x", None)
                y = action.get("y", None)
                amount = action.get("amount", 3)
                direction = action.get("direction", "down")
                clicks_n = amount if direction == "up" else -amount
                if x and y:
                    self._move_overlay(x, y, "scrolling")
                    pyautogui.scroll(clicks_n, x=x, y=y)
                else:
                    pyautogui.scroll(clicks_n)
                return f"Scrolled {direction} {amount}"

            elif atype == "drag":
                x1, y1 = action.get("x1", 0), action.get("y1", 0)
                x2, y2 = action.get("x2", 0), action.get("y2", 0)
                self._move_overlay(x1, y1, "dragging")
                self._pulse_overlay()
                self.vmouse._send_drag(x1, y1, x2, y2)
                self._move_overlay(x2, y2, "dropped")
                return f"Dragged ({x1},{y1}) -> ({x2},{y2})"

            elif atype == "move":
                x, y = action.get("x", 0), action.get("y", 0)
                self._move_overlay(x, y, "moving")
                return f"Moved to ({x},{y})"

            elif atype == "wait":
                secs = min(float(action.get("seconds", 1.0)), 15)
                ov = self._get_overlay()
                if ov:
                    ov.set_label(f"waiting {secs}s...")
                time.sleep(secs)
                return f"Waited {secs}s"

            elif atype == "screenshot":
                question = action.get("question", "What is currently on screen?")
                ov = self._get_overlay()
                if ov:
                    ov.set_label("reading screen...")
                desc = self.screen.describe(question)
                return f"[SCREEN] {desc}"

            elif atype == "find_and_click":
                element = action.get("element", "")
                ov = self._get_overlay()
                if ov:
                    ov.set_label(f"finding {element}...")
                coords = self.screen.find_element(element)
                if coords:
                    self._move_overlay(coords[0], coords[1], f"clicking {element}")
                    self._pulse_overlay()
                    time.sleep(0.1)
                    self.vmouse._send_click(coords[0], coords[1])
                    return f"Clicked '{element}' at {coords}"
                return f"[NOT FOUND] Could not locate '{element}' on screen"

            elif atype == "select_all":
                pyautogui.hotkey("ctrl", "a")
                return "Selected all"

            elif atype == "copy":
                pyautogui.hotkey("ctrl", "c")
                return "Copied"

            elif atype == "paste":
                pyautogui.hotkey("ctrl", "v")
                return "Pasted"

            elif atype == "close_window":
                pyautogui.hotkey("alt", "F4")
                return "Closed window"

            elif atype == "minimize":
                pyautogui.hotkey("win", "down")
                return "Minimized window"

            elif atype == "maximize":
                pyautogui.hotkey("win", "up")
                return "Maximized window"

            else:
                return f"Unknown action type: {atype}"

        except pyautogui.FailSafeException:
            return "[STOPPED] Failsafe triggered — mouse moved to corner"
        except Exception as e:
            return f"[ERROR] {atype}: {e}"

    def _click(self, action: Dict, clicks: int, button: str) -> str:
        element = action.get("element", "")
        if element:
            coords = self.screen.find_element(element)
            if coords:
                self._move_overlay(coords[0], coords[1], f"clicking {element}")
                self._pulse_overlay()
                time.sleep(0.1)
                self.vmouse._send_click(coords[0], coords[1], button, clicks)
                return f"Clicked '{element}' at {coords}"
            return f"[NOT FOUND] '{element}' not visible on screen"
        x, y = action.get("x"), action.get("y")
        if x is not None and y is not None:
            self._move_overlay(x, y, "clicking")
            self._pulse_overlay()
            time.sleep(0.1)
            self.vmouse._send_click(x, y, button, clicks)
            return f"Clicked ({x},{y})"
        return "[ERROR] click needs x,y or element"

    def _open_app(self, app_name: str) -> str:
        ov = self._get_overlay()
        if ov:
            ov.set_label(f"opening {app_name}...")
        key = app_name.lower().strip()
        candidates = APP_SHORTCUTS.get(key, [app_name])
        for candidate in candidates:
            if "*" in candidate:
                import glob
                matches = glob.glob(candidate)
                candidate = matches[-1] if matches else None
                if not candidate:
                    continue
            try:
                if os.path.isfile(candidate):
                    subprocess.Popen([candidate])
                else:
                    if candidate.startswith("ms-"):
                        subprocess.Popen(f"start {candidate}", shell=True)
                    else:
                        subprocess.Popen(candidate, shell=True)
                time.sleep(1.5)
                return f"Opened {app_name}"
            except Exception:
                continue
        return f"[FAILED] Could not open '{app_name}'"

    def _open_url(self, url: str) -> str:
        import webbrowser
        key = url.lower().strip().rstrip("/")
        url = SITE_SHORTCUTS.get(key, url)
        if not url.startswith("http"):
            url = "https://" + url
        ov = self._get_overlay()
        if ov:
            ov.set_label(f"opening {url[:30]}...")
        webbrowser.open(url)
        time.sleep(2.5)
        return f"Opened {url}"

    def search_on_site(self, site: str, query: str) -> str:
        import webbrowser, urllib.parse
        q = urllib.parse.quote_plus(query)
        urls = {
            "youtube":  f"https://www.youtube.com/results?search_query={q}",
            "google":   f"https://www.google.com/search?q={q}",
            "spotify":  f"https://open.spotify.com/search/{q}",
            "reddit":   f"https://www.reddit.com/search/?q={q}",
            "amazon":   f"https://www.amazon.com/s?k={q}",
            "github":   f"https://github.com/search?q={q}",
            "twitter":  f"https://twitter.com/search?q={q}",
            "x":        f"https://x.com/search?q={q}",
            "twitch":   f"https://www.twitch.tv/search?term={q}",
            "bing":     f"https://www.bing.com/search?q={q}",
        }
        target = urls.get(site.lower())
        if target:
            ov = self._get_overlay()
            if ov:
                ov.set_label(f"searching {site}...")
            webbrowser.open(target)
            time.sleep(2.5)
            return f"Searched '{query}' on {site}"
        return f"[UNKNOWN SITE] No search URL for '{site}'"

# ═══════════════════════════════════════════════════════════
# AI PLANNER
# Turns a natural language request into a list of actions
# ═══════════════════════════════════════════════════════════

def ai_plan_actions(task: str, screen_description: str,
                    previous_steps: List[str] = None,
                    screen_w: int = 1920, screen_h: int = 1080) -> List[Dict]:
    """
    Ask the LLM to produce a step-by-step action plan.
    Returns a list of action dicts ready for ActionExecutor.
    """
    prev = "\n".join(previous_steps or []) or "None yet"

    prompt = f"""You are AURA, an AI that controls a Windows computer.

TASK: {task}

CURRENT SCREEN:
{screen_description}

STEPS COMPLETED SO FAR:
{prev}

SCREEN SIZE: {screen_w}x{screen_h}

Plan the NEXT actions needed to complete the task.
Think step by step — what does the screen show, what needs to happen next?

Available action types:
- open_app        : {{"type":"open_app","app":"chrome"}}
- open_url        : {{"type":"open_url","url":"https://youtube.com"}}
- search_on_site  : {{"type":"search_on_site","site":"youtube","query":"juice wrld"}}
- find_and_click  : {{"type":"find_and_click","element":"search bar"}}
- click           : {{"type":"click","x":500,"y":300}}  OR  {{"type":"click","element":"Sign in button"}}
- double_click    : {{"type":"double_click","element":"folder name"}}
- type            : {{"type":"type","text":"juice wrld all girls are the same"}}
- hotkey          : {{"type":"hotkey","keys":"ctrl+t"}}
- press           : {{"type":"press","key":"enter"}}
- scroll          : {{"type":"scroll","direction":"down","amount":3}}
- wait            : {{"type":"wait","seconds":2}}
- screenshot      : {{"type":"screenshot","question":"Is the search results page loaded?"}}

Rules:
- ALWAYS use search_on_site when searching YouTube, Google, Spotify, Reddit, Amazon — it's instant and never fails
- NEVER use find_and_click to click a search bar — use search_on_site or hotkey instead
- Use open_app first if the browser isn't open yet, then search_on_site
- Use type ONLY after you've clicked a text field with find_and_click
- Always add a wait after open_app
- Maximum 8 actions per plan — keep it focused
- If task involves searching on a website, the entire plan should be: open_app → wait → search_on_site

Respond ONLY with a valid JSON array. No markdown, no explanation:
[
  {{"type":"open_app","app":"chrome"}},
  {{"type":"wait","seconds":2}},
  ...
]"""

    try:
        resp = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_COMPUTER_PLAN_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 1500}
            },
            timeout=180
        )
        raw = resp.json().get("response", "").strip()
        # Extract JSON array
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            import json
            return json.loads(match.group(0))
    except Exception as e:
        logger.error(f"Action planning failed: {e}")

    return []


def ai_check_complete(task: str, screen_description: str,
                      steps_taken: List[str]) -> bool:
    """
    Ask the AI if the task appears to be done based on the current screen.
    """
    prompt = f"""You are checking whether a computer automation task is complete.

ORIGINAL TASK: {task}
CURRENT SCREEN: {screen_description}
STEPS TAKEN: {chr(10).join(steps_taken)}

Is the task fully complete? Answer ONLY: YES or NO"""

    try:
        resp = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_COMPUTER_PLAN_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 5}
            },
            timeout=30
        )
        answer = resp.json().get("response", "").strip().upper()
        return "YES" in answer
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
# COMPUTER USE AGENT
# Main orchestrator — see → think → act → verify → repeat
# ═══════════════════════════════════════════════════════════

class ComputerUseAgent:
    """
    Gives AURA full control of the desktop.

    Usage:
        agent = ComputerUseAgent()
        result = agent.run("open spotify on chrome and search for juice wrld")
    """

    MAX_ROUNDS   = 8    # max planning rounds before giving up
    MAX_ACTIONS  = 50   # max total actions per task

    def __init__(self, log_cb: Callable = None):
        self.screen   = ScreenReader()
        self.executor = ActionExecutor(self.screen)
        self._log_cb  = log_cb
        self.history: List[str] = []

    def set_log_callback(self, cb: Callable):
        self._log_cb = cb

    def _log(self, msg: str):
        print(f"[COMPUTER] {msg}")
        if self._log_cb:
            self._log_cb(f"[COMPUTER] {msg}", "info")

    def _open_browser(self, browser: str = "chrome") -> str:
        """
        Open a browser reliably. Uses start command so Windows
        finds it even when it's not in PATH.
        """
        start_cmds = {
            "chrome":  ["start", "chrome"],
            "firefox": ["start", "firefox"],
            "edge":    ["start", "msedge"],
        }
        # First try direct exe paths
        result = self.executor._open_app(browser)
        if "[FAILED]" not in result:
            return result
        # Fallback: Windows start command always works for installed browsers
        try:
            cmd = start_cmds.get(browser.lower(), ["start", browser])
            subprocess.Popen(cmd, shell=True)
            time.sleep(2.0)
            self._log(f"Opened {browser} via start command")
            return f"Opened {browser}"
        except Exception as e:
            return f"[FAILED] {e}"

    def _try_fast_path(self, task: str) -> Optional[str]:
        """
        Pattern-match common task types and execute them directly
        without calling the AI planner. Fast, reliable, no timeouts.

        Handles:
          - "open X and search for Y on Z"
          - "search for Y on Z"
          - "open X"
          - "go to URL"
          - "open X and go to URL"
          - "play Y on spotify/youtube"
          - "type Y"
          - hotkeys
        """
        low = task.lower().strip()

        # ── Pattern: open <browser> and search <query> on <site> ──
        m = re.search(
            r'open\s+(\w+)\s+and\s+(?:search(?:\s+for)?|look\s+up|find)\s+(.+?)\s+on\s+(\w+)',
            low
        )
        if m:
            browser, query, site = m.group(1), m.group(2).strip(), m.group(3).strip()
            self._log(f"Fast path: open {browser} → search '{query}' on {site}")
            r1 = self._open_browser(browser)
            self.history.append(f"[open_app] {r1}")
            time.sleep(1.5)
            r2 = self.executor.search_on_site(site, query)
            self.history.append(f"[search_on_site] {r2}")
            return f"Task: {task}\nSteps taken: 2\nActions:\n  {r1}\n  {r2}"

        # ── Pattern: search <query> on <site> (no browser specified) ──
        m = re.search(
            r'(?:search(?:\s+for)?|look\s+up|find)\s+(.+?)\s+on\s+(\w+)',
            low
        )
        if m:
            query, site = m.group(1).strip(), m.group(2).strip()
            self._log(f"Fast path: search '{query}' on {site}")
            r1 = self.executor.search_on_site(site, query)
            self.history.append(f"[search_on_site] {r1}")
            return f"Task: {task}\nSteps taken: 1\nActions:\n  {r1}"

        # ── Pattern: play <song> on <site> ──
        m = re.search(r'play\s+(.+?)\s+on\s+(\w+)', low)
        if m:
            query, site = m.group(1).strip(), m.group(2).strip()
            self._log(f"Fast path: play '{query}' on {site}")
            r1 = self.executor.search_on_site(site, query)
            self.history.append(f"[search_on_site] {r1}")
            return f"Task: {task}\nSteps taken: 1\nActions:\n  {r1}"

        # ── Pattern: open <browser/app> and go to <url> ──
        m = re.search(r'open\s+(\w+)\s+and\s+(?:go\s+to|navigate\s+to|open)\s+(\S+)', low)
        if m:
            browser, url = m.group(1), m.group(2).strip()
            self._log(f"Fast path: open {browser} → go to {url}")
            r1 = self._open_browser(browser)
            self.history.append(f"[open_app] {r1}")
            time.sleep(1.5)
            r2 = self.executor._open_url(url)
            self.history.append(f"[open_url] {r2}")
            return f"Task: {task}\nSteps taken: 2\nActions:\n  {r1}\n  {r2}"

        # ── Pattern: go to / open <url with dot> ──
        m = re.search(r'(?:go\s+to|navigate\s+to|open)\s+((?:https?://)?[\w.-]+\.\w{2,}(?:/\S*)?)', low)
        if m:
            url = m.group(1)
            self._log(f"Fast path: go to {url}")
            r1 = self.executor._open_url(url)
            self.history.append(f"[open_url] {r1}")
            return f"Task: {task}\nSteps taken: 1\nActions:\n  {r1}"

        # ── Pattern: open <app name only> ──
        m = re.match(r'^open\s+(\w[\w\s]*)$', low)
        if m:
            app = m.group(1).strip()
            self._log(f"Fast path: open {app}")
            r1 = self.executor._open_app(app)
            self.history.append(f"[open_app] {r1}")
            return f"Task: {task}\nSteps taken: 1\nActions:\n  {r1}"

        # No fast path matched — fall through to AI planner
        return None

    def run(self, task: str) -> str:
        """
        Execute a natural-language computer task.
        Tries fast-path pattern matching first before calling the AI planner.
        Returns a summary of what was done.
        """
        self._log(f"Starting task: {task}")
        self.history = []

        # ── FAST PATH ────────────────────────────────────────
        # Handle common patterns directly without AI planning.
        # Avoids timeouts and misrouting entirely.
        fast_result = self._try_fast_path(task)
        if fast_result:
            return fast_result
        # ─────────────────────────────────────────────────────

        screen_w, screen_h = pyautogui.size()
        total_actions = 0

        for round_num in range(self.MAX_ROUNDS):
            self._log(f"Round {round_num + 1} — reading screen...")

            screen_desc = self.screen.describe(
                f"Describe what is currently on screen in detail. "
                f"Include: app names, visible text, buttons, input fields, URLs."
            )
            self._log(f"Screen: {screen_desc[:120]}...")

            if round_num > 0 and ai_check_complete(task, screen_desc, self.history):
                self._log("Task complete!")
                break

            self._log("Planning actions...")
            actions = ai_plan_actions(
                task, screen_desc, self.history,
                screen_w=screen_w, screen_h=screen_h
            )

            if not actions:
                self._log("No actions planned — task may be complete or stuck.")
                break

            self._log(f"Executing {len(actions)} actions...")

            for action in actions:
                if total_actions >= self.MAX_ACTIONS:
                    self._log("Action limit reached.")
                    break

                result = self.executor.execute(action)
                total_actions += 1
                step = f"[{action.get('type','?')}] {result}"
                self.history.append(step)
                self._log(step)

                if action.get("type") == "screenshot":
                    break

                time.sleep(0.15)

        summary = (
            f"Task: {task}\n"
            f"Steps taken: {len(self.history)}\n"
            f"Actions:\n" + "\n".join(f"  {s}" for s in self.history)
        )
        return summary


# ═══════════════════════════════════════════════════════════
# INTENT DETECTOR
# Decides if a user message needs computer use
# ═══════════════════════════════════════════════════════════

COMPUTER_USE_TRIGGERS = [
    r'\bopen\b.{1,40}\b(app|chrome|firefox|spotify|discord|notepad|vscode|steam|browser)\b',
    r'\b(click|press|type|scroll)\b',
    r'\bgo to\b.{1,30}\b(website|site|page|url)\b',
    r'\bnavigate to\b',
    r'\bsearch (for|on)\b',
    r'\b(play|queue|add).{1,40}\b(spotify|youtube|music)\b',
    r'\bcontrol my (computer|pc|screen|desktop)\b',
    r'\buse my (mouse|keyboard)\b',
    r'\b(close|minimize|maximize|resize)\b.{1,20}\b(window|app)\b',
    r'\bfill (in|out)\b.{1,20}\b(form|field)\b',
    r'\bdownload\b.{1,30}\bfrom\b',
    r'\bdo it (on|in) (my|the) (browser|screen|computer)\b',
    r'\bon (chrome|firefox|edge|my browser)\b',
    r'\btype (this|that|it)\b',
    r'\bmove (the )?(mouse|cursor)\b',
]

COMPUTER_USE_EXCLUDE = [
    r'\bhow (do|does|to|can)\b',
    r'\bwhat is\b',
    r'\bexplain\b',
    r'\bwrite (a|me|the) (code|script|function|program)\b',
]


def should_use_computer(text: str) -> bool:
    low = text.lower().strip()
    for pat in COMPUTER_USE_EXCLUDE:
        if re.search(pat, low):
            return False
    for pat in COMPUTER_USE_TRIGGERS:
        if re.search(pat, low):
            return True
    return False


# ── Singleton ──────────────────────────────────────────────

_cu_agent: Optional[ComputerUseAgent] = None

def get_computer_agent() -> ComputerUseAgent:
    global _cu_agent
    if _cu_agent is None:
        _cu_agent = ComputerUseAgent()
    return _cu_agent