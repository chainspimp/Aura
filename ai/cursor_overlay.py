# ============================================
# FILE: ai/cursor_overlay.py
# AURA Virtual Cursor — Blue Animated Overlay
#
# Creates a transparent fullscreen window that
# sits above everything and shows a glowing
# blue AURA cursor that moves independently
# from the user's real mouse.
#
# The real mouse is saved before each action,
# snaps to the target to click, then instantly
# returns — so fast it's invisible. The blue
# cursor is what you actually see moving.
# ============================================

import threading
import time
import math
import tkinter as tk
from typing import Optional, Tuple


class CursorOverlay:
    """
    Transparent fullscreen tkinter overlay.
    Draws a glowing blue AURA cursor that animates
    smoothly to any screen position.
    """

    CURSOR_RADIUS   = 14
    GLOW_RADIUS     = 26
    ANIM_STEPS      = 18       # frames per movement animation
    ANIM_DURATION   = 0.22     # seconds for a full move
    CLICK_PULSE_MS  = 280      # click ripple animation duration

    # Colours
    CURSOR_FILL     = "#00aaff"
    CURSOR_OUTLINE  = "#ffffff"
    GLOW_COLOUR     = "#0044cc"
    LABEL_FG        = "#00ddff"
    LABEL_BG        = "#001133"
    RIPPLE_COLOUR   = "#00ccff"
    TRANSPARENT_KEY = "#010101"   # colour treated as transparent by Windows

    def __init__(self):
        self._x: float = 100.0
        self._y: float = 100.0
        self._label_text: str = ""
        self._visible: bool = False
        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._lock  = threading.Lock()
        self._ripples = []   # list of active ripple animations

    # ── Lifecycle ─────────────────────────────────────────

    def start(self):
        """Launch the overlay window in a background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def stop(self):
        """Destroy the overlay."""
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass
        self._root   = None
        self._canvas = None

    def show(self):
        self._visible = True
        if self._canvas:
            self._root.after(0, self._redraw)

    def hide(self):
        self._visible = False
        if self._canvas:
            self._root.after(0, lambda: self._canvas.delete("all"))

    def set_label(self, text: str):
        """Set the status label shown under the cursor."""
        self._label_text = text
        if self._canvas:
            self._root.after(0, self._redraw)

    # ── Movement ──────────────────────────────────────────

    def move_to(self, x: int, y: int, label: str = ""):
        """
        Smoothly animate the cursor to (x, y).
        Blocks until animation completes.
        """
        if not self._canvas:
            return

        if label:
            self._label_text = label

        start_x, start_y = self._x, self._y
        steps = self.ANIM_STEPS
        delay = self.ANIM_DURATION / steps

        for i in range(1, steps + 1):
            t = i / steps
            # Ease in-out cubic
            t = t * t * (3 - 2 * t)
            self._x = start_x + (x - start_x) * t
            self._y = start_y + (y - start_y) * t
            if self._canvas:
                self._root.after(0, self._redraw)
            time.sleep(delay)

        self._x, self._y = float(x), float(y)

    def pulse(self, colour: str = None):
        """Trigger a click ripple animation at current position."""
        if not self._canvas:
            return
        colour = colour or self.RIPPLE_COLOUR
        ripple = {"x": self._x, "y": self._y,
                  "r": self.CURSOR_RADIUS, "max_r": 55,
                  "colour": colour, "alpha": 1.0}
        self._ripples.append(ripple)
        self._root.after(0, self._animate_ripple)

    # ── Internal drawing ──────────────────────────────────

    def _run(self):
        """Tkinter main loop — runs in its own thread."""
        import pyautogui
        sw, sh = pyautogui.size()

        self._root = tk.Tk()
        self._root.overrideredirect(True)         # no title bar
        self._root.attributes("-topmost", True)   # always on top
        self._root.attributes("-transparentcolor", self.TRANSPARENT_KEY)
        self._root.attributes("-alpha", 1.0)
        self._root.geometry(f"{sw}x{sh}+0+0")
        self._root.configure(bg=self.TRANSPARENT_KEY)
        # Make it click-through on Windows
        try:
            import ctypes
            hwnd = self._root.winfo_id()
            GWL_EXSTYLE   = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )
        except Exception:
            pass

        self._canvas = tk.Canvas(
            self._root,
            width=sw, height=sh,
            bg=self.TRANSPARENT_KEY,
            highlightthickness=0,
        )
        self._canvas.pack()

        # Start hidden
        self._root.after(0, self._redraw)
        self._ready.set()
        self._root.mainloop()

    def _redraw(self):
        """Redraw the cursor on the canvas."""
        if not self._canvas:
            return
        self._canvas.delete("cursor")

        if not self._visible:
            return

        x, y = int(self._x), int(self._y)
        r = self.CURSOR_RADIUS
        gr = self.GLOW_RADIUS

        # Glow ring (outer)
        self._canvas.create_oval(
            x - gr, y - gr, x + gr, y + gr,
            fill="", outline=self.GLOW_COLOUR,
            width=2, tags="cursor"
        )

        # Mid glow
        self._canvas.create_oval(
            x - r - 4, y - r - 4, x + r + 4, y + r + 4,
            fill="", outline="#0066ee",
            width=1, tags="cursor"
        )

        # Main circle fill
        self._canvas.create_oval(
            x - r, y - r, x + r, y + r,
            fill=self.CURSOR_FILL,
            outline=self.CURSOR_OUTLINE,
            width=2, tags="cursor"
        )

        # Inner white dot
        self._canvas.create_oval(
            x - 4, y - 4, x + 4, y + 4,
            fill="white", outline="",
            tags="cursor"
        )

        # AURA label
        if self._label_text:
            pad = 5
            tx, ty = x + r + 8, y - 10
            # Background pill
            text_w = len(self._label_text) * 7 + pad * 2
            self._canvas.create_rectangle(
                tx - pad, ty - pad,
                tx + text_w, ty + 16 + pad,
                fill=self.LABEL_BG,
                outline=self.CURSOR_FILL,
                width=1, tags="cursor"
            )
            self._canvas.create_text(
                tx, ty,
                text=self._label_text,
                fill=self.LABEL_FG,
                font=("Courier New", 9, "bold"),
                anchor="nw", tags="cursor"
            )

    def _animate_ripple(self):
        """Expand and fade ripple circles."""
        if not self._canvas or not self._ripples:
            return

        self._canvas.delete("ripple")
        still_active = []

        for rpl in self._ripples:
            rpl["r"] += (rpl["max_r"] - self.CURSOR_RADIUS) / 12
            rpl["alpha"] -= 0.09
            if rpl["alpha"] > 0:
                a = max(0, min(1, rpl["alpha"]))
                # Approximate alpha with outline width
                self._canvas.create_oval(
                    rpl["x"] - rpl["r"], rpl["y"] - rpl["r"],
                    rpl["x"] + rpl["r"], rpl["y"] + rpl["r"],
                    fill="", outline=rpl["colour"],
                    width=max(1, int(a * 3)),
                    tags="ripple"
                )
                still_active.append(rpl)

        self._ripples = still_active
        self._root.after(0, self._redraw)   # redraw cursor on top of ripple
        if self._ripples:
            self._root.after(30, self._animate_ripple)


# ── Singleton ─────────────────────────────────────────────

_overlay_instance: Optional[CursorOverlay] = None

def get_overlay() -> CursorOverlay:
    global _overlay_instance
    if _overlay_instance is None:
        _overlay_instance = CursorOverlay()
        _overlay_instance.start()
        _overlay_instance.show()
    return _overlay_instance