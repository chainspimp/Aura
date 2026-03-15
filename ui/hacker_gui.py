# ============================================
# FILE: ui/hacker_gui.py
# AURA Security Terminal — Hacker Mode GUI
# Dark green-on-black terminal aesthetic
# ============================================

import os
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ── Palette ───────────────────────────────────────────────
BG        = "#030a03"
BG2       = "#060f06"
BG3       = "#0a150a"
PANEL     = "#050d05"
GREEN     = "#00ff41"
GREEN2    = "#00cc33"
GREEN_DIM = "#005510"
CYAN      = "#00ffff"
YELLOW    = "#ffff00"
RED       = "#ff0040"
ORANGE    = "#ff8800"
WHITE     = "#e0ffe0"
DIM       = "#2a4a2a"
BORDER    = "#0f2a0f"

FONT_TERM  = ("Courier New", 10)
FONT_TERMS = ("Courier New", 9)
FONT_TERML = ("Courier New", 12, "bold")
FONT_UI    = ("Courier New", 10)

BANNER = r"""
   ___   __  ______  ___    ____  ___  _____
  / _ | / / / / __ \/ _ |  / __/ / _ \/ ___/
 / __ |/ /_/ / /_/ / __ | _\ \  / ___/ /__  
/_/ |_|\____/\____/_/ |_|/___/ /_/   \___/  
                                              
         [ SECURITY AGENT v2.0 ]
         [ ETHICAL HACKING MODE ]
"""


class HackerTerminalGUI:
    """
    Full hacking terminal GUI.
    Left panel: command input + task launcher
    Right panel: live terminal output with colour coding
    Bottom: status bar + phase indicator
    """

    def __init__(self, agent=None, env_label: str = ""):
        self.agent     = agent
        self.env_label = env_label   # e.g. "WSL — Ubuntu 22.04" or "Git Bash"
        self._task_q   = queue.Queue()
        self._scanning = False

        self.root = tk.Tk()
        self.root.title("AURA // SECURITY AGENT")
        self.root.configure(bg=BG)
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)

        self._build_ui()
        self._print_banner()
        self._tick_clock()

        # Wire agent log callback to GUI
        if self.agent:
            self.agent.set_log_callback(self._agent_log)

    # ── NEW: thread-safe permission dialog ─────────────────
    def ask_tool_permission(self, tool_name: str, install_cmd: str) -> bool:
        """
        Called from the agent background thread before installing a tool.
        Shows a yes/no dialog on the main thread and blocks until answered.
        """
        result = [None]
        event  = threading.Event()

        def _show():
            env = self.env_label or "current shell"
            approved = messagebox.askyesno(
                "Tool Installation Required",
                f"'{tool_name}' is not installed.\n\n"
                f"Environment : {env}\n"
                f"Install cmd : {install_cmd}\n\n"
                f"Allow AURA to install '{tool_name}' now?",
                parent=self.root
            )
            result[0] = approved
            event.set()

        self.root.after(0, _show)
        event.wait(timeout=120)
        return bool(result[0])

    # ── UI Construction ───────────────────────────────────

    def _build_ui(self):
        # ── Titlebar ──
        title_bar = tk.Frame(self.root, bg=BG, height=50)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        tk.Label(
            title_bar,
            text="▓▓ AURA SECURITY AGENT ▓▓",
            font=("Courier New", 13, "bold"),
            fg=GREEN, bg=BG
        ).pack(side="left", padx=20, pady=10)

        # Environment badge (WSL / Git Bash / PowerShell / CMD)
        if self.env_label:
            env_color = CYAN if "WSL" in self.env_label or "Bash" in self.env_label else YELLOW
            tk.Label(
                title_bar,
                text=f"[ {self.env_label} ]",
                font=("Courier New", 9, "bold"),
                fg=env_color, bg=BG
            ).pack(side="left", padx=4, pady=10)

        self.clock_var = tk.StringVar()
        tk.Label(
            title_bar, textvariable=self.clock_var,
            font=FONT_TERMS, fg=DIM, bg=BG
        ).pack(side="right", padx=20)

        self.status_var = tk.StringVar(value="● IDLE")
        tk.Label(
            title_bar, textvariable=self.status_var,
            font=("Courier New", 10, "bold"),
            fg=GREEN_DIM, bg=BG
        ).pack(side="right", padx=10)

        tk.Frame(self.root, bg=GREEN_DIM, height=1).pack(fill="x")

        # ── Body ──
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)

        # Left panel
        left = tk.Frame(body, bg=PANEL, width=300)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._build_left(left)

        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # Right panel — terminal
        right = tk.Frame(body, bg=BG2)
        right.pack(side="left", fill="both", expand=True)
        self._build_terminal(right)

        # Status bar
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")
        self._build_statusbar()

    def _build_left(self, parent):
        # Section label
        def section(text):
            tk.Label(
                parent, text=text,
                font=("Courier New", 8, "bold"),
                fg=GREEN2, bg=PANEL, anchor="w"
            ).pack(fill="x", padx=12, pady=(10, 2))
            tk.Frame(parent, bg=GREEN_DIM, height=1).pack(fill="x", padx=12)

        # ── Task input ──
        section("▸ TASK / TARGET")
        self.task_var = tk.StringVar()
        self.task_entry = tk.Text(
            parent, height=4,
            font=FONT_TERMS,
            bg=BG3, fg=WHITE,
            insertbackground=GREEN,
            relief="flat", bd=0,
            highlightthickness=1,
            highlightcolor=GREEN2,
            highlightbackground=BORDER,
            wrap="word",
        )
        self.task_entry.pack(fill="x", padx=12, pady=6)
        self.task_entry.insert("1.0", "e.g. scan 192.168.1.1 for open ports")
        self.task_entry.config(fg=DIM)

        def on_focus_in(e):
            if self.task_entry.get("1.0", "end").strip() == "e.g. scan 192.168.1.1 for open ports":
                self.task_entry.delete("1.0", "end")
                self.task_entry.config(fg=WHITE)

        def on_focus_out(e):
            if not self.task_entry.get("1.0", "end").strip():
                self.task_entry.insert("1.0", "e.g. scan 192.168.1.1 for open ports")
                self.task_entry.config(fg=DIM)

        self.task_entry.bind("<FocusIn>",  on_focus_in)
        self.task_entry.bind("<FocusOut>", on_focus_out)
        self.task_entry.bind("<Control-Return>", lambda e: self._launch_task())

        self.launch_btn = tk.Button(
            parent,
            text="▶  EXECUTE TASK",
            font=("Courier New", 10, "bold"),
            fg=BG, bg=GREEN,
            relief="flat", bd=0,
            activebackground=CYAN,
            activeforeground=BG,
            cursor="hand2",
            command=self._launch_task,
        )
        self.launch_btn.pack(fill="x", padx=12, pady=(0, 8), ipady=7)

        # ── Manual command ──
        section("▸ MANUAL COMMAND")
        cmd_frame = tk.Frame(parent, bg=PANEL)
        cmd_frame.pack(fill="x", padx=12, pady=6)

        self.cmd_var = tk.StringVar()
        self.cmd_entry = tk.Entry(
            cmd_frame,
            textvariable=self.cmd_var,
            font=FONT_TERMS,
            bg=BG3, fg=GREEN,
            insertbackground=GREEN,
            relief="flat", bd=0,
            highlightthickness=1,
            highlightcolor=GREEN2,
            highlightbackground=BORDER,
        )
        self.cmd_entry.pack(fill="x", ipady=5)
        self.cmd_entry.bind("<Return>", lambda e: self._run_manual_cmd())

        tk.Button(
            parent,
            text="RUN",
            font=FONT_TERMS,
            fg=BG, bg=GREEN2,
            relief="flat", bd=0,
            cursor="hand2",
            command=self._run_manual_cmd,
        ).pack(fill="x", padx=12, ipady=4, pady=(0, 6))

        # ── Quick tools ──
        section("▸ QUICK RECON")
        quick_cmds = [
            ("Port Scan",       "nmap -sV -T4 {target}"),
            ("Full Scan",       "nmap -sV -sC -O -T4 {target}"),
            ("Web Headers",     "curl -I {target}"),
            ("WHOIS",           "whois {target}"),
            ("DNS Lookup",      "dig {target} ANY +short"),
            ("Dir Brute",       "gobuster dir -u http://{target} -w /usr/share/wordlists/dirb/common.txt"),
            ("Vuln Scan",       "nikto -h {target}"),
            ("SSL Check",       "sslscan {target}"),
            ("WAF Detect",      "wafw00f http://{target}"),
            ("Tech Detect",     "whatweb {target}"),
            ("Subdomain Enum",  "subfinder -d {target}"),
            ("Email Harvest",   "theHarvester -d {target} -b all"),
        ]

        scroll_frame = tk.Frame(parent, bg=PANEL)
        scroll_frame.pack(fill="both", expand=True, padx=12)

        canvas = tk.Canvas(scroll_frame, bg=PANEL, highlightthickness=0)
        scrollbar = tk.Scrollbar(scroll_frame, orient="vertical",
                                  command=canvas.yview)
        btn_frame = tk.Frame(canvas, bg=PANEL)

        btn_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=btn_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for label, cmd_template in quick_cmds:
            btn = tk.Button(
                btn_frame,
                text=f"  {label}",
                font=FONT_TERMS,
                fg=GREEN_DIM if "{target}" in cmd_template else GREEN2,
                bg=BG3,
                relief="flat", bd=0,
                anchor="w",
                cursor="hand2",
                command=lambda t=cmd_template: self._quick_cmd(t),
            )
            btn.pack(fill="x", pady=1, ipady=3)
            btn.bind("<Enter>", lambda e, b=btn: b.config(fg=GREEN, bg=BORDER))
            btn.bind("<Leave>", lambda e, b=btn, t=cmd_template:
                     b.config(fg=GREEN_DIM if "{target}" in t else GREEN2, bg=BG3))

        # ── Controls ──
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=12, pady=4)
        ctrl = tk.Frame(parent, bg=PANEL)
        ctrl.pack(fill="x", padx=12, pady=(0, 10))

        tk.Button(ctrl, text="STOP", font=FONT_TERMS,
                  fg=RED, bg=BG3, relief="flat", bd=0,
                  cursor="hand2", command=self._stop_task,
        ).pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 2))

        tk.Button(ctrl, text="CLEAR", font=FONT_TERMS,
                  fg=DIM, bg=BG3, relief="flat", bd=0,
                  cursor="hand2", command=self._clear_terminal,
        ).pack(side="left", fill="x", expand=True, ipady=4, padx=2)

        tk.Button(ctrl, text="REPORT", font=FONT_TERMS,
                  fg=CYAN, bg=BG3, relief="flat", bd=0,
                  cursor="hand2", command=self._save_report,
        ).pack(side="left", fill="x", expand=True, ipady=4, padx=(2, 0))

    def _build_terminal(self, parent):
        # Tab bar
        tab_bar = tk.Frame(parent, bg=BG2)
        tab_bar.pack(fill="x")

        self.active_tab = "terminal"
        self.tab_btns = {}
        tabs = [("TERMINAL", "terminal"), ("FINDINGS", "findings"),
                ("REPORT", "report")]

        for label, key in tabs:
            btn = tk.Button(
                tab_bar, text=label,
                font=("Courier New", 9, "bold"),
                fg=DIM, bg=BG2,
                relief="flat", bd=0,
                padx=14, pady=7,
                cursor="hand2",
                command=lambda k=key: self._switch_tab(k)
            )
            btn.pack(side="left")
            self.tab_btns[key] = btn

        tk.Frame(parent, bg=GREEN_DIM, height=1).pack(fill="x")

        container = tk.Frame(parent, bg=BG2)
        container.pack(fill="both", expand=True)

        self.tab_frames = {}
        for _, key in tabs:
            f = tk.Frame(container, bg=BG2)
            self.tab_frames[key] = f

        # Terminal output
        self.terminal = scrolledtext.ScrolledText(
            self.tab_frames["terminal"],
            font=FONT_TERM, bg=BG, fg=GREEN,
            insertbackground=GREEN,
            relief="flat", bd=0,
            wrap="word", state="disabled",
            cursor="xterm",
        )
        self.terminal.pack(fill="both", expand=True, padx=2, pady=2)
        self._setup_tags(self.terminal)

        # Findings
        self.findings_text = scrolledtext.ScrolledText(
            self.tab_frames["findings"],
            font=FONT_TERMS, bg=BG, fg=GREEN,
            relief="flat", bd=0, wrap="word", state="disabled"
        )
        self.findings_text.pack(fill="both", expand=True, padx=2, pady=2)
        self._setup_tags(self.findings_text)

        # Report
        self.report_text = scrolledtext.ScrolledText(
            self.tab_frames["report"],
            font=FONT_TERMS, bg=BG, fg=WHITE,
            relief="flat", bd=0, wrap="word", state="disabled"
        )
        self.report_text.pack(fill="both", expand=True, padx=2, pady=2)
        self._setup_tags(self.report_text)

        self._switch_tab("terminal")

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=BG, height=26)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        self.phase_var = tk.StringVar(value="IDLE")
        tk.Label(bar, textvariable=self.phase_var,
                 font=FONT_TERMS, fg=GREEN2, bg=BG, anchor="w"
        ).pack(side="left", padx=15)

        self.progress_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.progress_var,
                 font=FONT_TERMS, fg=DIM, bg=BG, anchor="e"
        ).pack(side="right", padx=15)

    def _setup_tags(self, widget):
        widget.tag_config("green",    foreground=GREEN)
        widget.tag_config("green2",   foreground=GREEN2)
        widget.tag_config("cyan",     foreground=CYAN)
        widget.tag_config("yellow",   foreground=YELLOW)
        widget.tag_config("red",      foreground=RED)
        widget.tag_config("orange",   foreground=ORANGE)
        widget.tag_config("white",    foreground=WHITE)
        widget.tag_config("dim",      foreground=DIM)
        widget.tag_config("banner",   foreground=GREEN,
                          font=("Courier New", 9))
        widget.tag_config("phase",    foreground=CYAN,
                          font=("Courier New", 10, "bold"))
        widget.tag_config("success",  foreground=GREEN,
                          font=("Courier New", 10, "bold"))
        widget.tag_config("warn",     foreground=YELLOW)
        widget.tag_config("error",    foreground=RED)
        widget.tag_config("cmd",      foreground=GREEN2,
                          font=("Courier New", 10, "bold"))
        widget.tag_config("analysis", foreground=CYAN)
        widget.tag_config("output",   foreground=GREEN)

    def _switch_tab(self, key):
        self.active_tab = key
        for k, f in self.tab_frames.items():
            f.pack_forget()
        self.tab_frames[key].pack(fill="both", expand=True)
        for k, btn in self.tab_btns.items():
            btn.config(
                fg=GREEN if k == key else DIM,
                bg=BG3 if k == key else BG2
            )

    # ── Output helpers ────────────────────────────────────

    def _write(self, widget, text, tag=""):
        def _do():
            widget.config(state="normal")
            widget.insert("end", text, tag)
            widget.see("end")
            widget.config(state="disabled")
        self.root.after(0, _do)

    def _print_banner(self):
        self._write(self.terminal, BANNER, "banner")
        env_line = f"[AURA-SEC] Shell : {self.env_label}\n" if self.env_label else ""
        self._write(self.terminal,
            f"\n{env_line}"
            "[AURA-SEC] Type a task above or use quick recon buttons\n"
            "[AURA-SEC] Ctrl+Enter to launch task\n"
            "[AURA-SEC] AURA will ask your permission before installing any missing tool\n\n",
            "dim"
        )

    def _agent_log(self, line: str, level: str = "info"):
        """Called by HackerAgent for every log line."""
        tag_map = {
            "success":  "success",
            "warn":     "warn",
            "error":    "error",
            "phase":    "phase",
            "step":     "cyan",
            "analysis": "analysis",
            "dim":      "dim",
        }
        tag = tag_map.get(level, "green")

        # Colour specific patterns
        if line.startswith("[>]") or "] [>]" in line:
            tag = "cmd"
        elif line.startswith("    ") or "]     " in line:
            tag = "output"
        elif "[AI]" in line:
            tag = "analysis"
        elif "[+]" in line:
            tag = "success"
        elif "[!]" in line:
            tag = "warn"
        elif "[?]" in line:          # permission prompts — yellow
            tag = "yellow"
        elif "[*]" in line:
            tag = "green2"
        elif "PHASE:" in line:
            tag = "phase"
        elif "Shell ready" in line or "Virtual shell" in line or "WSL" in line:
            tag = "cyan"

        self._write(self.terminal, line + "\n", tag)

        # Update phase indicator
        if "PHASE:" in line:
            phase = line.split("PHASE:")[-1].strip()
            self.root.after(0, lambda: self.phase_var.set(f"PHASE: {phase}"))

    def _print_terminal(self, msg: str, tag: str = "green"):
        self._write(self.terminal, msg + "\n", tag)

    # ── Actions ───────────────────────────────────────────

    def _get_target(self) -> str:
        """Extract target from task entry or cmd entry."""
        task = self.task_entry.get("1.0", "end").strip()
        if task == "e.g. scan 192.168.1.1 for open ports":
            return ""
        return task

    def _launch_task(self):
        if self._scanning:
            self._print_terminal("[!] Already running a task. Stop it first.", "warn")
            return

        task = self._get_target()
        if not task:
            self._print_terminal("[!] Enter a task first.", "warn")
            return

        if not self.agent:
            self._print_terminal("[!] Agent not initialised.", "error")
            return

        self._scanning = True
        self.launch_btn.config(text="◼  RUNNING...", bg=GREEN_DIM,
                                fg=GREEN, state="disabled")
        self.status_var.set("● SCANNING")
        self.phase_var.set("Starting...")
        self._switch_tab("terminal")

        def run():
            try:
                result = self.agent.run_task(task)
                self._render_findings(result.get("findings", []))
                report = result.get("report_path")
                if report:
                    self._render_report(report)
                self.root.after(0, lambda: self.status_var.set("● DONE"))
                self.root.after(0, lambda: self.phase_var.set("COMPLETE"))
                self.root.after(0, lambda: self._switch_tab("findings"))
            except Exception as e:
                self._print_terminal(f"[!] Task failed: {e}", "error")
            finally:
                self._scanning = False
                self.root.after(0, lambda: self.launch_btn.config(
                    text="▶  EXECUTE TASK", bg=GREEN, fg=BG, state="normal"
                ))
                self.root.after(0, lambda: self.status_var.set("● IDLE"))

        threading.Thread(target=run, daemon=True).start()

    def _run_manual_cmd(self):
        cmd = self.cmd_var.get().strip()
        if not cmd:
            return
        self.cmd_var.set("")

        if not self.agent:
            self._print_terminal("[!] Agent not initialised.", "error")
            return

        self._print_terminal(f"[>] {cmd}", "cmd")
        self._switch_tab("terminal")

        def run():
            # Ensure session is started
            if not self.agent._active:
                self._print_terminal("[*] Starting session...", "green2")
                self.agent.start_session()

            # Run command, stream each line directly to terminal
            lines = []
            def on_line(line):
                if line.strip():
                    self._print_terminal(f"    {line}", "green")
                    lines.append(line)

            output = self.agent.session.run(cmd, timeout=60, on_line=on_line)

            # If on_line didn't fire (emulator returns all at once), print now
            if not lines and output and output.strip():
                for line in output.strip().split("\n"):
                    self._print_terminal(f"    {line}", "green")
            elif not lines and not output:
                self._print_terminal("    [no output]", "dim")

        threading.Thread(target=run, daemon=True).start()

    def _quick_cmd(self, template: str):
        """Run a quick recon command, substituting {target}."""
        target_text = self._get_target()
        # Try to extract just the IP/domain from the task
        import re
        ip_match = re.search(
            r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
            r'[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]\.[a-zA-Z]{2,})',
            target_text
        )
        target = ip_match.group(0) if ip_match else target_text

        if not target or "{target}" in template and not target:
            self._print_terminal(
                "[!] Enter a target in the task box first.", "warn"
            )
            return

        cmd = template.replace("{target}", target)
        self.cmd_var.set(cmd)
        self._run_manual_cmd()

    def _stop_task(self):
        if self.agent:
            self.agent.stop_session()
            self._scanning = False
            self.launch_btn.config(
                text="▶  EXECUTE TASK", bg=GREEN, fg=BG, state="normal"
            )
            self.status_var.set("● STOPPED")
            self.phase_var.set("STOPPED")
            self._print_terminal("\n[*] Session terminated.", "warn")

    def _clear_terminal(self):
        self.terminal.config(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.config(state="disabled")
        self._print_banner()

    def _render_findings(self, findings):
        w = self.findings_text
        w.config(state="normal")
        w.delete("1.0", "end")

        w.insert("end", "\n  PENTEST FINDINGS\n", "phase")
        w.insert("end", "  " + "─" * 52 + "\n\n", "dim")

        for i, f in enumerate(findings, 1):
            w.insert("end", f"  [{i}] {f['phase']} — {f['tool'].upper()}\n", "cyan")
            w.insert("end", f"  CMD: {f['command']}\n", "cmd")
            w.insert("end", "\n  OUTPUT (truncated):\n", "dim")
            w.insert("end", f"  {f['output'][:500]}\n", "output")
            w.insert("end", "\n  AI ANALYSIS:\n", "dim")
            w.insert("end", f"  {f['analysis']}\n", "analysis")
            w.insert("end", "\n  " + "─" * 52 + "\n\n", "dim")

        w.config(state="disabled")

    def _render_report(self, report_path: str):
        w = self.report_text
        w.config(state="normal")
        w.delete("1.0", "end")
        w.insert("end", f"\n  Report saved to:\n  {report_path}\n\n", "success")
        w.insert("end", "  Switch to FINDINGS tab for full results.\n", "dim")
        w.config(state="disabled")

    def _save_report(self):
        if not self.agent or not self.agent.findings:
            messagebox.showinfo("No Report", "Run a task first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word", "*.docx"), ("Text", "*.txt")],
            initialfile="pentest_report.docx"
        )
        if path:
            saved = self.agent._generate_report(
                self.agent.target or "unknown",
                {},
                self.agent.findings
            )
            import shutil
            shutil.copy(saved, path)
            messagebox.showinfo("Saved", f"Report saved to:\n{path}")

    def _tick_clock(self):
        self.clock_var.set(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    # ── Show ──────────────────────────────────────────────

    def show(self):
        self.root.mainloop()

    def show_nonblocking(self):
        t = threading.Thread(target=self.root.mainloop, daemon=True)
        t.start()


def launch_hacker_gui(blocking=True):
    from ai.hacker_agent import get_hacker_agent
    from ai.hacker_runner import _probe_environment
    env_label = _probe_environment()
    agent = get_hacker_agent()
    gui = HackerTerminalGUI(agent=agent, env_label=env_label)

    # Wire permission dialog before session starts
    agent.set_permission_callback(gui.ask_tool_permission)

    def _start_session_async():
        import time
        time.sleep(0.3)  # small delay so GUI renders first
        agent.start_session()

    threading.Thread(target=_start_session_async, daemon=True).start()
    if blocking:
        gui.show()
    else:
        gui.show_nonblocking()