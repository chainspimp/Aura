# ============================================
# FILE: ui/vm_gui.py
# AURA VM Mode — Cursor-style IDE GUI
#
# Left  : Chat panel — describe what to build
# Center: File tree — all project files
# Right : Code editor — live streaming code
# Bottom: Terminal — run output and logs
# ============================================

import os
import re
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk, filedialog, messagebox
from datetime import datetime
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

# ── Palette — dark IDE aesthetic ──────────────────────────
BG          = "#0d1117"
BG2         = "#161b22"
BG3         = "#21262d"
BG4         = "#30363d"
PANEL       = "#13181f"
ACCENT      = "#58a6ff"
ACCENT2     = "#3fb950"
ACCENT3     = "#f78166"
ACCENT4     = "#d2a8ff"
YELLOW      = "#e3b341"
TEXT        = "#c9d1d9"
TEXT_DIM    = "#484f58"
TEXT_BRIGHT = "#f0f6fc"
BORDER      = "#30363d"
CURSOR_COL  = "#58a6ff"

FONT_CODE   = ("JetBrains Mono", 10) if False else ("Courier New", 10)
FONT_UI     = ("Segoe UI",       10)
FONT_UI_S   = ("Segoe UI",        9)
FONT_UI_B   = ("Segoe UI",       10, "bold")
FONT_MONO_S = ("Courier New",     9)

# Syntax highlight colours (simple keyword-based)
SYNTAX = {
    "keyword":  "#ff7b72",
    "string":   "#a5d6ff",
    "comment":  "#8b949e",
    "number":   "#79c0ff",
    "function": "#d2a8ff",
    "class":    "#ffa657",
    "builtin":  "#79c0ff",
    "operator": "#ff7b72",
}

PYTHON_KEYWORDS = {
    "def", "class", "import", "from", "return", "if", "elif", "else",
    "for", "while", "try", "except", "finally", "with", "as", "in",
    "not", "and", "or", "is", "None", "True", "False", "pass", "break",
    "continue", "raise", "yield", "lambda", "async", "await", "global",
    "nonlocal", "del", "assert",
}

JS_KEYWORDS = {
    "const", "let", "var", "function", "return", "if", "else", "for",
    "while", "class", "import", "export", "from", "default", "new",
    "this", "async", "await", "try", "catch", "finally", "throw",
    "typeof", "instanceof", "true", "false", "null", "undefined",
    "extends", "super", "static",
}


class VMGui:
    """
    Cursor-style IDE window for AURA's VM coding mode.
    """

    def __init__(self):
        self._agent   = None
        self._running = False
        self._current_file: Optional[str] = None
        self._files: Dict[str, str] = {}
        self._project_dir: Optional[str] = None
        self._token_buffer = ""
        self._build_phase  = "planning"   # "planning" | "coding" | "running"

        self.root = tk.Tk()
        self.root.title("AURA — VM Mode")
        self.root.configure(bg=BG)
        self.root.geometry("1400x860")
        self.root.minsize(1100, 700)

        self._build_ui()
        self._tick_clock()
        self._welcome()

    # ── UI Construction ───────────────────────────────────

    def _build_ui(self):
        # ── Top bar ──
        top = tk.Frame(self.root, bg=BG, height=44)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(top, text="⬡  AURA VM",
                 font=("Segoe UI", 13, "bold"),
                 fg=ACCENT, bg=BG).pack(side="left", padx=18, pady=8)

        tk.Label(top, text="local · autonomous · coding agent",
                 font=FONT_UI_S, fg=TEXT_DIM, bg=BG).pack(side="left")

        self.clock_var = tk.StringVar()
        tk.Label(top, textvariable=self.clock_var,
                 font=FONT_MONO_S, fg=TEXT_DIM, bg=BG).pack(side="right", padx=16)

        self.status_var = tk.StringVar(value="● idle")
        self.status_lbl = tk.Label(top, textvariable=self.status_var,
                                   font=FONT_UI_S, fg=TEXT_DIM, bg=BG)
        self.status_lbl.pack(side="right", padx=12)

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        # ── Main body ──
        body = tk.PanedWindow(self.root, orient="horizontal",
                               bg=BG, sashwidth=4,
                               sashrelief="flat", sashpad=0)
        body.pack(fill="both", expand=True)

        # Left: chat
        left = tk.Frame(body, bg=PANEL, width=320)
        body.add(left, minsize=260)
        self._build_chat(left)

        # Center: file tree
        center = tk.Frame(body, bg=BG2, width=200)
        body.add(center, minsize=160)
        self._build_filetree(center)

        # Right: code editor + terminal
        right = tk.Frame(body, bg=BG)
        body.add(right, minsize=400)
        self._build_editor_and_terminal(right)

    def _build_chat(self, parent):
        # Header
        hdr = tk.Frame(parent, bg=BG3, height=36)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="CHAT", font=("Segoe UI", 8, "bold"),
                 fg=TEXT_DIM, bg=BG3).pack(side="left", padx=12, pady=8)

        # Chat history
        self.chat_log = scrolledtext.ScrolledText(
            parent,
            font=FONT_UI_S, bg=BG, fg=TEXT,
            relief="flat", bd=0,
            wrap="word", state="disabled",
            highlightthickness=0,
            insertbackground=ACCENT,
        )
        self.chat_log.pack(fill="both", expand=True, padx=0, pady=0)
        self._setup_chat_tags()

        # Separator
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")

        # Input area
        input_frame = tk.Frame(parent, bg=BG3)
        input_frame.pack(fill="x", padx=10, pady=8)

        tk.Label(input_frame, text="What do you want to build?",
                 font=FONT_UI_S, fg=TEXT_DIM, bg=BG3).pack(anchor="w", pady=(0, 4))

        self.task_input = tk.Text(
            input_frame, height=5,
            font=FONT_UI_S,
            bg=BG4, fg=TEXT_BRIGHT,
            insertbackground=ACCENT,
            relief="flat", bd=0,
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BORDER,
            wrap="word",
        )
        self.task_input.pack(fill="x", pady=(0, 6))
        self.task_input.bind("<Control-Return>", lambda e: self._start_build())

        btn_row = tk.Frame(input_frame, bg=BG3)
        btn_row.pack(fill="x")

        self.build_btn = tk.Button(
            btn_row,
            text="▶  Build",
            font=("Segoe UI", 10, "bold"),
            fg=BG, bg=ACCENT2,
            relief="flat", bd=0,
            activebackground="#4ec261",
            activeforeground=BG,
            cursor="hand2",
            command=self._start_build,
        )
        self.build_btn.pack(side="left", fill="x", expand=True,
                             ipady=6, padx=(0, 4))

        tk.Button(
            btn_row,
            text="■  Stop",
            font=FONT_UI_S,
            fg=ACCENT3, bg=BG4,
            relief="flat", bd=0,
            cursor="hand2",
            command=self._stop_build,
        ).pack(side="left", ipady=6, ipadx=10)

        # Open folder button
        tk.Button(
            input_frame,
            text="📁  Open project folder",
            font=FONT_UI_S,
            fg=TEXT_DIM, bg=BG3,
            relief="flat", bd=0,
            cursor="hand2",
            command=self._open_folder,
        ).pack(fill="x", pady=(4, 0), ipady=4)

    def _build_filetree(self, parent):
        hdr = tk.Frame(parent, bg=BG3, height=36)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="FILES", font=("Segoe UI", 8, "bold"),
                 fg=TEXT_DIM, bg=BG3).pack(side="left", padx=12, pady=8)

        self.file_tree = tk.Listbox(
            parent,
            bg=BG2, fg=TEXT,
            font=FONT_MONO_S,
            relief="flat", bd=0,
            selectbackground=BG4,
            selectforeground=ACCENT,
            highlightthickness=0,
            activestyle="none",
            cursor="hand2",
        )
        self.file_tree.pack(fill="both", expand=True)
        self.file_tree.bind("<<ListboxSelect>>", self._on_file_select)

        # Scrollbar
        sb = tk.Scrollbar(parent, command=self.file_tree.yview,
                           bg=BG2, troughcolor=BG2)
        sb.pack(side="right", fill="y")
        self.file_tree.config(yscrollcommand=sb.set)

    def _build_editor_and_terminal(self, parent):
        # Vertical pane: editor top, terminal bottom
        pane = tk.PanedWindow(parent, orient="vertical",
                               bg=BG, sashwidth=4,
                               sashrelief="flat", sashpad=0)
        pane.pack(fill="both", expand=True)

        # ── Editor area ──
        editor_frame = tk.Frame(pane, bg=BG)
        pane.add(editor_frame, minsize=200)

        # Tab bar — THINKING | CODE
        tab_bar = tk.Frame(editor_frame, bg=BG2, height=36)
        tab_bar.pack(fill="x")
        tab_bar.pack_propagate(False)

        self._editor_tab = tk.StringVar(value="thinking")
        self._tab_btns   = {}

        def make_tab(label, key):
            btn = tk.Button(
                tab_bar, text=label,
                font=("Segoe UI", 9, "bold"),
                fg=TEXT_DIM, bg=BG2,
                relief="flat", bd=0,
                padx=16, pady=6,
                cursor="hand2",
                command=lambda k=key: self._switch_editor_tab(k)
            )
            btn.pack(side="left")
            self._tab_btns[key] = btn

        make_tab("🧠  THINKING", "thinking")
        make_tab("</> CODE",     "code")

        self.editor_tab_var = tk.StringVar(value="")
        tk.Label(tab_bar, textvariable=self.editor_tab_var,
                 font=FONT_UI_S, fg=TEXT_DIM, bg=BG2,
                 padx=14).pack(side="left")

        self.line_col_var = tk.StringVar(value="")
        tk.Label(tab_bar, textvariable=self.line_col_var,
                 font=FONT_MONO_S, fg=TEXT_DIM, bg=BG2
                 ).pack(side="right", padx=12)

        tk.Frame(editor_frame, bg=BORDER, height=1).pack(fill="x")

        # Tab container
        tab_container = tk.Frame(editor_frame, bg=BG)
        tab_container.pack(fill="both", expand=True)

        # ── THINKING panel ──
        self._thinking_frame = tk.Frame(tab_container, bg=BG)
        self.thinking_view = scrolledtext.ScrolledText(
            self._thinking_frame,
            font=("Courier New", 10),
            bg="#0d1117", fg="#c9d1d9",
            insertbackground=ACCENT,
            relief="flat", bd=0,
            wrap="word", state="disabled",
            highlightthickness=0,
            padx=16, pady=12,
        )
        self.thinking_view.pack(fill="both", expand=True)
        self._setup_thinking_tags()

        # ── CODE panel ──
        self._code_frame = tk.Frame(tab_container, bg=BG)
        editor_body = tk.Frame(self._code_frame, bg=BG)
        editor_body.pack(fill="both", expand=True)

        self.line_numbers = tk.Text(
            editor_body,
            width=4, font=FONT_CODE,
            bg=BG, fg=TEXT_DIM,
            relief="flat", bd=0,
            state="disabled",
            highlightthickness=0,
            padx=6,
        )
        self.line_numbers.pack(side="left", fill="y")

        tk.Frame(editor_body, bg=BORDER, width=1).pack(side="left", fill="y")

        self.code_editor = scrolledtext.ScrolledText(
            editor_body,
            font=FONT_CODE,
            bg=BG, fg=TEXT,
            insertbackground=CURSOR_COL,
            relief="flat", bd=0,
            wrap="none",
            highlightthickness=0,
            padx=12, pady=8,
            undo=True,
        )
        self.code_editor.pack(side="left", fill="both", expand=True)
        self._setup_editor_tags()
        self.code_editor.bind("<KeyRelease>", self._on_editor_key)
        self.code_editor.bind("<ButtonRelease>", self._update_cursor_pos)

        hscroll = tk.Scrollbar(self._code_frame, orient="horizontal",
                                command=self.code_editor.xview,
                                bg=BG2, troughcolor=BG2)
        hscroll.pack(fill="x")
        self.code_editor.config(xscrollcommand=hscroll.set)

        # Show thinking tab by default
        self._switch_editor_tab("thinking")

        # ── Terminal ──
        term_frame = tk.Frame(pane, bg=BG2)
        pane.add(term_frame, minsize=120)

        term_hdr = tk.Frame(term_frame, bg=BG3, height=32)
        term_hdr.pack(fill="x")
        term_hdr.pack_propagate(False)

        tk.Label(term_hdr, text="TERMINAL",
                 font=("Segoe UI", 8, "bold"),
                 fg=TEXT_DIM, bg=BG3,
                 padx=12, pady=6).pack(side="left")

        self.run_status_var = tk.StringVar(value="")
        tk.Label(term_hdr, textvariable=self.run_status_var,
                 font=FONT_UI_S, fg=ACCENT2, bg=BG3).pack(side="left", padx=4)

        tk.Button(
            term_hdr, text="⊗ Clear",
            font=FONT_UI_S, fg=TEXT_DIM, bg=BG3,
            relief="flat", bd=0, cursor="hand2",
            command=self._clear_terminal
        ).pack(side="right", padx=8)

        tk.Frame(term_frame, bg=BORDER, height=1).pack(fill="x")

        self.terminal = scrolledtext.ScrolledText(
            term_frame,
            font=FONT_MONO_S,
            bg="#010409", fg=ACCENT2,
            relief="flat", bd=0,
            wrap="word", state="disabled",
            highlightthickness=0,
            padx=10, pady=6,
        )
        self.terminal.pack(fill="both", expand=True)
        self._setup_terminal_tags()

    def _switch_editor_tab(self, key: str):
        self._editor_tab.set(key)
        self._thinking_frame.pack_forget()
        self._code_frame.pack_forget()
        if key == "thinking":
            self._thinking_frame.pack(fill="both", expand=True)
        else:
            self._code_frame.pack(fill="both", expand=True)
        for k, btn in self._tab_btns.items():
            btn.config(
                fg=TEXT_BRIGHT if k == key else TEXT_DIM,
                bg=BG3 if k == key else BG2
            )

    # ── Tag setup ─────────────────────────────────────────

    def _setup_chat_tags(self):
        self.chat_log.tag_config("user",    foreground=ACCENT,  font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_config("aura",    foreground=ACCENT2, font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_config("msg",     foreground=TEXT)
        self.chat_log.tag_config("phase",   foreground=ACCENT4, font=("Segoe UI", 9,  "bold"))
        self.chat_log.tag_config("success", foreground=ACCENT2)
        self.chat_log.tag_config("warn",    foreground=YELLOW)
        self.chat_log.tag_config("error",   foreground=ACCENT3)
        self.chat_log.tag_config("dim",     foreground=TEXT_DIM)
        self.chat_log.tag_config("step",    foreground=TEXT)

    def _setup_thinking_tags(self):
        self.thinking_view.tag_config("think",   foreground="#8b949e", font=("Courier New", 10))
        self.thinking_view.tag_config("plan",    foreground="#d2a8ff", font=("Courier New", 10, "bold"))
        self.thinking_view.tag_config("header",  foreground="#58a6ff", font=("Courier New", 11, "bold"))
        self.thinking_view.tag_config("json",    foreground="#a5d6ff")
        self.thinking_view.tag_config("dim",     foreground="#484f58")
        self.thinking_view.tag_config("stream",  foreground="#c9d1d9")
        self.chat_log.tag_config("user",    foreground=ACCENT,  font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_config("aura",    foreground=ACCENT2, font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_config("msg",     foreground=TEXT)
        self.chat_log.tag_config("phase",   foreground=ACCENT4, font=("Segoe UI", 9,  "bold"))
        self.chat_log.tag_config("success", foreground=ACCENT2)
        self.chat_log.tag_config("warn",    foreground=YELLOW)
        self.chat_log.tag_config("error",   foreground=ACCENT3)
        self.chat_log.tag_config("dim",     foreground=TEXT_DIM)
        self.chat_log.tag_config("step",    foreground=TEXT)

    def _setup_editor_tags(self):
        self.code_editor.tag_config("keyword",  foreground=SYNTAX["keyword"])
        self.code_editor.tag_config("string",   foreground=SYNTAX["string"])
        self.code_editor.tag_config("comment",  foreground=SYNTAX["comment"])
        self.code_editor.tag_config("number",   foreground=SYNTAX["number"])
        self.code_editor.tag_config("function", foreground=SYNTAX["function"])
        self.code_editor.tag_config("class",    foreground=SYNTAX["class"])
        self.code_editor.tag_config("builtin",  foreground=SYNTAX["builtin"])
        self.code_editor.tag_config("current_line",
                                    background="#1c2128")
        self.code_editor.tag_config("streaming",
                                    foreground=ACCENT,
                                    font=(*FONT_CODE, "bold") if len(FONT_CODE) == 2
                                    else FONT_CODE)

    def _setup_terminal_tags(self):
        self.terminal.tag_config("cmd",     foreground=ACCENT)
        self.terminal.tag_config("out",     foreground=ACCENT2)
        self.terminal.tag_config("err",     foreground=ACCENT3)
        self.terminal.tag_config("info",    foreground=TEXT)
        self.terminal.tag_config("phase",   foreground=ACCENT4, font=("Courier New", 9, "bold"))
        self.terminal.tag_config("success", foreground=ACCENT2, font=("Courier New", 9, "bold"))
        self.terminal.tag_config("dim",     foreground=TEXT_DIM)

    # ── Welcome message ───────────────────────────────────

    def _welcome(self):
        self._chat_write("AURA", "aura")
        self._chat_write("  VM Mode ready. Describe any project and I'll build it.\n\n", "msg")
        self._chat_write("  Examples:\n", "dim")
        self._chat_write("  • A SaaS dashboard with user auth and Stripe payments\n", "dim")
        self._chat_write("  • A REST API for a todo app with SQLite\n", "dim")
        self._chat_write("  • A Discord bot that replies to commands\n", "dim")
        self._chat_write("  • A web scraper that saves results to CSV\n\n", "dim")
        self._chat_write("  Ctrl+Enter to build\n", "dim")

        self._term_write("AURA VM Agent — ready\n", "info")
        self._term_write(f"Workspace: vm_workspace/\n", "dim")

    # ── Build control ─────────────────────────────────────

    def _start_build(self):
        if self._running:
            return

        task = self.task_input.get("1.0", "end").strip()
        if not task:
            return

        self.task_input.delete("1.0", "end")
        self._files  = {}
        self._current_file = None
        self._running = True
        self._build_phase = "planning"

        self.build_btn.config(text="⏳ Building...", bg=BG4,
                               fg=TEXT_DIM, state="disabled")
        self._set_status("● building", ACCENT)

        # Clear panels
        self.code_editor.config(state="normal")
        self.code_editor.delete("1.0", "end")
        self.code_editor.config(state="disabled")
        self.thinking_view.config(state="normal")
        self.thinking_view.delete("1.0", "end")
        self.thinking_view.insert("end", "═══ PLANNING ARCHITECTURE ═══\n\n", "header")
        self.thinking_view.config(state="disabled")
        self.file_tree.delete(0, "end")
        self._clear_terminal()
        self._switch_editor_tab("thinking")   # show thinking first

        # Show user message
        self._chat_write(f"\nYou\n", "user")
        self._chat_write(f"  {task}\n\n", "msg")

        # Import agent here to avoid circular issues
        try:
            from ai.vm_agent import get_vm_agent
            agent = get_vm_agent()
        except ImportError as e:
            self._chat_write(f"[ERROR] {e}\n", "error")
            self._reset_btn()
            return

        agent.on_log        = self._on_agent_log
        agent.on_token      = self._on_token
        agent.on_file_start = self._on_file_start
        agent.on_file_done  = self._on_file_done
        agent.on_run_result = self._on_run_result
        agent.on_complete   = self._on_complete
        self._agent = agent

        # Run in background thread
        threading.Thread(
            target=self._build_thread,
            args=(agent, task),
            daemon=True
        ).start()

    def _build_thread(self, agent, task):
        try:
            agent.build(task)
        except Exception as e:
            self.root.after(0, lambda: self._chat_write(
                f"[ERROR] {e}\n", "error"
            ))
        finally:
            self.root.after(0, self._reset_btn)

    def _stop_build(self):
        if self._agent:
            self._agent.stop()
        self._running = False
        self._reset_btn()
        self._set_status("● stopped", ACCENT3)
        self._chat_write("  Build stopped.\n", "warn")

    def _reset_btn(self):
        self._running = False
        self.build_btn.config(text="▶  Build", bg=ACCENT2,
                               fg=BG, state="normal")
        self._set_status("● idle", TEXT_DIM)

    # ── Agent callbacks ───────────────────────────────────

    def _on_agent_log(self, msg: str, level: str):
        def _do():
            tag = {
                "phase":   "phase",
                "success": "success",
                "warn":    "warn",
                "error":   "error",
                "step":    "step",
            }.get(level, "dim")
            self._chat_write(f"  {msg}\n", tag)
            self._term_write(f"{msg}\n", tag)
        self.root.after(0, _do)

    def _on_token(self, token: str):
        """Stream tokens into the right panel based on current phase."""
        def _do():
            if self._build_phase == "planning":
                # Show thinking in the THINKING tab
                self.thinking_view.config(state="normal")
                self.thinking_view.insert("end", token, "stream")
                self.thinking_view.see("end")
                self.thinking_view.config(state="disabled")
            else:
                # Show code streaming in CODE tab
                self.code_editor.config(state="normal")
                self.code_editor.insert("end", token, "streaming")
                self.code_editor.see("end")
                self.code_editor.config(state="disabled")
                self._update_line_numbers()
        self.root.after(0, _do)

    def _on_file_start(self, path: str):
        def _do():
            self._current_file = path
            self._build_phase  = "coding"   # switch token routing to code editor
            self.editor_tab_var.set(f"  {os.path.basename(path)}  ●")
            self._set_status(f"● writing {path}", ACCENT)
            # Switch to code tab and clear for new file
            self._switch_editor_tab("code")
            self.code_editor.config(state="normal")
            self.code_editor.delete("1.0", "end")
            self.code_editor.config(state="disabled")
            self._term_write(f"writing {path}...\n", "dim")
        self.root.after(0, _do)

    def _on_file_done(self, path: str, content: str):
        def _do():
            self._files[path] = content
            # Update file tree
            if path not in self.file_tree.get(0, "end"):
                icon = self._file_icon(path)
                self.file_tree.insert("end", f"  {icon} {path}")
            # Show final content with syntax highlighting
            self._show_file(path, content)
            self.editor_tab_var.set(f"  {os.path.basename(path)}")
        self.root.after(0, _do)

    def _on_run_result(self, result: dict):
        def _do():
            self._build_phase = "running"
            if result.get("success"):
                self._term_write("✓ Run successful\n", "success")
                self.run_status_var.set("✓ passing")
            else:
                self._term_write("✗ Run failed\n", "err")
                self.run_status_var.set("✗ error")
            if result.get("stdout"):
                self._term_write(result["stdout"], "out")
            if result.get("stderr"):
                self._term_write(result["stderr"], "err")
        self.root.after(0, _do)

    def _on_complete(self, project_dir: str):
        def _do():
            self._project_dir = project_dir
            self._chat_write("\nAURA\n", "aura")
            self._chat_write(
                f"  ✅ Done! Project saved to:\n  {project_dir}\n\n",
                "success"
            )
            self._chat_write(
                f"  {len(self._files)} files written.\n",
                "dim"
            )
            self._set_status("● done", ACCENT2)
        self.root.after(0, _do)

    # ── File display ──────────────────────────────────────

    def _show_file(self, path: str, content: str):
        self.code_editor.config(state="normal")
        self.code_editor.delete("1.0", "end")
        self.code_editor.insert("1.0", content)
        self._highlight_syntax(path)
        self.code_editor.config(state="normal")   # keep editable
        self.code_editor.see("1.0")
        self._update_line_numbers()

    def _highlight_syntax(self, path: str):
        """Apply basic syntax highlighting based on file extension."""
        ext = os.path.splitext(path)[1].lower()

        # Clear existing tags
        for tag in ["keyword", "string", "comment", "number", "function", "class"]:
            self.code_editor.tag_remove(tag, "1.0", "end")

        content = self.code_editor.get("1.0", "end")

        if ext == ".py":
            keywords = PYTHON_KEYWORDS
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            keywords = JS_KEYWORDS
        else:
            return   # No highlighting for other types yet

        import re as _re

        def apply_tag(pattern, tag, flags=0):
            for m in _re.finditer(pattern, content, flags):
                start = f"1.0 + {m.start()} chars"
                end   = f"1.0 + {m.end()} chars"
                self.code_editor.tag_add(tag, start, end)

        # Comments
        if ext == ".py":
            apply_tag(r'#[^\n]*', "comment")
        else:
            apply_tag(r'//[^\n]*', "comment")
            apply_tag(r'/\*.*?\*/', "comment", _re.DOTALL)

        # Strings
        apply_tag(r'""".*?"""', "string", _re.DOTALL)
        apply_tag(r"'''.*?'''", "string", _re.DOTALL)
        apply_tag(r'"(?:[^"\\]|\\.)*"', "string")
        apply_tag(r"'(?:[^'\\]|\\.)*'", "string")

        # Numbers
        apply_tag(r'\b\d+\.?\d*\b', "number")

        # Keywords (word boundary match)
        for kw in keywords:
            apply_tag(rf'\b{_re.escape(kw)}\b', "keyword")

        # def/class names
        if ext == ".py":
            apply_tag(r'(?<=def )\w+', "function")
            apply_tag(r'(?<=class )\w+', "class")
        else:
            apply_tag(r'(?<=function )\w+', "function")
            apply_tag(r'(?<=class )\w+', "class")

    def _on_file_select(self, event):
        sel = self.file_tree.curselection()
        if not sel:
            return
        entry = self.file_tree.get(sel[0]).strip()
        # Strip icon prefix
        path = re.sub(r'^[^\w./\\]+\s*', '', entry)
        if path in self._files:
            self._current_file = path
            self.editor_tab_var.set(f"  {os.path.basename(path)}")
            self._show_file(path, self._files[path])

    def _file_icon(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        icons = {
            ".py": "🐍", ".js": "📜", ".ts": "📘", ".jsx": "⚛",
            ".tsx": "⚛", ".html": "🌐", ".css": "🎨", ".json": "{}",
            ".md": "📄", ".sh": "⚙", ".txt": "📝", ".sql": "🗄",
            ".env": "🔑", ".yml": "⚙", ".yaml": "⚙", ".toml": "⚙",
            ".gitignore": "🚫",
        }
        return icons.get(ext, "📄")

    # ── Editor helpers ────────────────────────────────────

    def _update_line_numbers(self):
        content = self.code_editor.get("1.0", "end-1c")
        lines   = content.count("\n") + 1
        nums    = "\n".join(str(i) for i in range(1, lines + 1))

        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", "end")
        self.line_numbers.insert("1.0", nums)
        self.line_numbers.config(state="disabled")

    def _on_editor_key(self, event):
        self._update_cursor_pos(event)
        self._update_line_numbers()
        # Auto-save to files dict
        if self._current_file:
            self._files[self._current_file] = self.code_editor.get("1.0", "end-1c")

    def _update_cursor_pos(self, event=None):
        pos = self.code_editor.index("insert")
        line, col = pos.split(".")
        self.line_col_var.set(f"Ln {line}, Col {int(col)+1}")

    # ── Terminal helpers ──────────────────────────────────

    def _term_write(self, msg: str, tag: str = "info"):
        def _do():
            self.terminal.config(state="normal")
            self.terminal.insert("end", msg, tag)
            self.terminal.see("end")
            self.terminal.config(state="disabled")
        self.root.after(0, _do)

    def _clear_terminal(self):
        self.terminal.config(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.config(state="disabled")

    # ── Chat helpers ──────────────────────────────────────

    def _chat_write(self, msg: str, tag: str = "msg"):
        self.chat_log.config(state="normal")
        self.chat_log.insert("end", msg, tag)
        self.chat_log.see("end")
        self.chat_log.config(state="disabled")

    # ── Misc ──────────────────────────────────────────────

    def _set_status(self, text: str, colour: str = TEXT_DIM):
        self.status_var.set(text)
        self.status_lbl.config(fg=colour)

    def _open_folder(self):
        folder = self._project_dir or os.path.join(os.getcwd(), "vm_workspace")
        try:
            import subprocess
            subprocess.Popen(f'explorer "{folder}"')
        except Exception:
            pass

    def _tick_clock(self):
        self.clock_var.set(datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    def show(self):
        self.root.mainloop()

    def show_nonblocking(self):
        import threading
        threading.Thread(target=self.root.mainloop, daemon=True).start()


# ── Launcher ───────────────────────────────────────────────

def launch_vm_gui(blocking: bool = True):
    gui = VMGui()
    if blocking:
        gui.show()
    else:
        gui.show_nonblocking()