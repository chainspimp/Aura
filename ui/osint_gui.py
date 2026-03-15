# ============================================
# FILE: ui/osint_gui.py
# OSINT GUI — dark terminal-aesthetic interface
# Opens when AURA detects an OSINT request
# ============================================

import os
import re
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ── Colour palette ────────────────────────────────────────────────────────────
BG          = "#0a0a0f"
BG2         = "#0f0f1a"
BG3         = "#141428"
PANEL       = "#12121f"
ACCENT      = "#00ff88"
ACCENT2     = "#00ccff"
ACCENT3     = "#ff3366"
TEXT        = "#c8d8e8"
TEXT_DIM    = "#556677"
TEXT_BRIGHT = "#ffffff"
BORDER      = "#1e2a3a"
ENTRY_BG    = "#0d1117"
FONT_MONO   = ("Courier New", 10)
FONT_MONO_S = ("Courier New", 9)
FONT_MONO_L = ("Courier New", 12, "bold")
FONT_UI     = ("Courier New", 10)


class OSINTGui:
    """
    Dark terminal-style GUI for AURA's OSINT engine.
    Pre-fills fields if data was parsed from the chat input.
    Runs the scan in a background thread so the UI stays responsive.
    """

    def __init__(self, prefill: dict = None, web_search_fn=None):
        self.prefill       = prefill or {}
        self.web_search_fn = web_search_fn
        self.scanning      = False

        self.root = tk.Tk()
        self.root.title("AURA // OSINT ENGINE")
        self.root.configure(bg=BG)
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        self.root.resizable(True, True)

        self._set_icon()
        self._build_ui()
        self._prefill_fields()

    # ── Window icon ───────────────────────────────────────────────────────────

    def _set_icon(self):
        try:
            icon = tk.PhotoImage(width=32, height=32)
            # Simple green pixel art eye icon
            for x in range(32):
                for y in range(32):
                    if (x - 16) ** 2 + (y - 16) ** 2 < 100:
                        icon.put("#00ff88", (x, y))
            self.root.iconphoto(True, icon)
        except Exception:
            pass

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ──
        header = tk.Frame(self.root, bg=BG, height=60)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        tk.Label(
            header,
            text="▸ AURA // OSINT ENGINE",
            font=("Courier New", 16, "bold"),
            fg=ACCENT, bg=BG
        ).pack(side="left", padx=20, pady=15)

        tk.Label(
            header,
            text="PUBLIC INTELLIGENCE AGGREGATOR",
            font=("Courier New", 9),
            fg=TEXT_DIM, bg=BG
        ).pack(side="left", padx=5, pady=15)

        # timestamp
        self.clock_var = tk.StringVar()
        tk.Label(
            header,
            textvariable=self.clock_var,
            font=FONT_MONO_S, fg=TEXT_DIM, bg=BG
        ).pack(side="right", padx=20)
        self._tick_clock()

        # Separator
        tk.Frame(self.root, bg=ACCENT, height=1).pack(fill="x")

        # ── Main body split ──
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=0, pady=0)

        # Left panel — inputs
        left = tk.Frame(body, bg=PANEL, width=320)
        left.pack(side="left", fill="y", padx=0, pady=0)
        left.pack_propagate(False)

        # Right panel — results
        right = tk.Frame(body, bg=BG2)
        right.pack(side="left", fill="both", expand=True)

        self._build_input_panel(left)
        self._build_results_panel(right)

        # ── Status bar ──
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")
        status_bar = tk.Frame(self.root, bg=BG, height=28)
        status_bar.pack(fill="x")
        status_bar.pack_propagate(False)

        self.status_var = tk.StringVar(value="READY — Enter target information and press SCAN")
        tk.Label(
            status_bar,
            textvariable=self.status_var,
            font=FONT_MONO_S, fg=TEXT_DIM, bg=BG,
            anchor="w"
        ).pack(side="left", padx=15, pady=4)

    def _build_input_panel(self, parent):
        tk.Label(
            parent,
            text="TARGET PARAMETERS",
            font=("Courier New", 10, "bold"),
            fg=ACCENT2, bg=PANEL
        ).pack(padx=15, pady=(15, 5), anchor="w")

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=15, pady=(0, 10))

        self.fields = {}
        field_defs = [
            ("FULL NAME",    "name",      "e.g. John Smith"),
            ("USERNAME",     "username",  "e.g. jsmith or @jsmith"),
            ("EMAIL",        "email",     "e.g. john@email.com"),
            ("PHONE",        "phone",     "e.g. +1-555-0100"),
            ("LOCATION",     "location",  "e.g. New York, USA"),
            ("EMPLOYER",     "employer",  "e.g. Acme Corp"),
            ("AGE / DOB",    "age",       "e.g. 32 or 1992-05-14"),
            ("WEBSITE",      "website",   "e.g. johnsmith.com"),
        ]

        for label, key, placeholder in field_defs:
            row = tk.Frame(parent, bg=PANEL)
            row.pack(fill="x", padx=15, pady=(0, 8))

            tk.Label(
                row, text=label,
                font=("Courier New", 8, "bold"),
                fg=TEXT_DIM, bg=PANEL, anchor="w"
            ).pack(anchor="w")

            var = tk.StringVar()
            entry = tk.Entry(
                row,
                textvariable=var,
                font=FONT_MONO_S,
                bg=ENTRY_BG, fg=TEXT,
                insertbackground=ACCENT,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightcolor=ACCENT,
                highlightbackground=BORDER,
            )
            entry.pack(fill="x", ipady=5)

            # Placeholder logic
            entry.insert(0, placeholder)
            entry.config(fg=TEXT_DIM)

            def on_focus_in(e, w=entry, ph=placeholder, v=var):
                if w.get() == ph:
                    w.delete(0, "end")
                    w.config(fg=TEXT)

            def on_focus_out(e, w=entry, ph=placeholder, v=var):
                if not w.get().strip():
                    w.insert(0, ph)
                    w.config(fg=TEXT_DIM)

            entry.bind("<FocusIn>",  on_focus_in)
            entry.bind("<FocusOut>", on_focus_out)

            self.fields[key] = (var, entry, placeholder)

        # Source toggles
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=15, pady=(5, 8))
        tk.Label(
            parent, text="SCAN SOURCES",
            font=("Courier New", 10, "bold"),
            fg=ACCENT2, bg=PANEL
        ).pack(padx=15, pady=(0, 5), anchor="w")

        self.source_vars = {}
        sources = [
            ("github",        "GitHub"),
            ("gitlab",        "GitLab"),
            ("reddit",        "Reddit"),
            ("keybase",       "Keybase"),
            ("npm",           "npm packages"),
            ("stackoverflow", "Stack Overflow"),
            ("gravatar",      "Gravatar"),
            ("breaches",      "Data Breaches"),
            ("web_search",    "Web Search"),
        ]

        src_frame = tk.Frame(parent, bg=PANEL)
        src_frame.pack(fill="x", padx=15)

        for i, (key, label) in enumerate(sources):
            var = tk.BooleanVar(value=True)
            cb = tk.Checkbutton(
                src_frame,
                text=label,
                variable=var,
                font=FONT_MONO_S,
                fg=TEXT, bg=PANEL,
                selectcolor=BG3,
                activebackground=PANEL,
                activeforeground=ACCENT,
                bd=0,
                highlightthickness=0,
            )
            cb.grid(row=i // 2, column=i % 2, sticky="w", pady=1)
            self.source_vars[key] = var

        # Buttons
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=15, pady=(10, 8))

        btn_frame = tk.Frame(parent, bg=PANEL)
        btn_frame.pack(fill="x", padx=15, pady=(0, 15))

        self.scan_btn = tk.Button(
            btn_frame,
            text="▶  SCAN TARGET",
            font=("Courier New", 11, "bold"),
            fg=BG, bg=ACCENT,
            relief="flat", bd=0,
            activebackground=ACCENT2,
            activeforeground=BG,
            cursor="hand2",
            command=self._start_scan,
        )
        self.scan_btn.pack(fill="x", pady=(0, 6), ipady=8)

        btn2_frame = tk.Frame(btn_frame, bg=PANEL)
        btn2_frame.pack(fill="x")

        tk.Button(
            btn2_frame,
            text="CLEAR",
            font=FONT_MONO_S,
            fg=TEXT_DIM, bg=BG3,
            relief="flat", bd=0,
            cursor="hand2",
            command=self._clear_fields,
        ).pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 3))

        tk.Button(
            btn2_frame,
            text="EXPORT",
            font=FONT_MONO_S,
            fg=TEXT_DIM, bg=BG3,
            relief="flat", bd=0,
            cursor="hand2",
            command=self._export_report,
        ).pack(side="left", fill="x", expand=True, ipady=5, padx=(3, 0))

    def _build_results_panel(self, parent):
        # Tabs
        tab_bar = tk.Frame(parent, bg=BG2)
        tab_bar.pack(fill="x")

        self.active_tab = tk.StringVar(value="live")
        tab_defs = [("LIVE FEED", "live"), ("PROFILES", "profiles"),
                    ("BREACHES", "breaches"), ("WEB", "web"), ("SUMMARY", "summary")]

        self.tab_buttons = {}
        for label, key in tab_defs:
            btn = tk.Button(
                tab_bar, text=label,
                font=("Courier New", 9, "bold"),
                fg=TEXT_DIM, bg=BG2,
                relief="flat", bd=0,
                padx=12, pady=8,
                cursor="hand2",
                command=lambda k=key: self._switch_tab(k)
            )
            btn.pack(side="left")
            self.tab_buttons[key] = btn

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")

        # Tab content frames
        self.tab_frames = {}
        container = tk.Frame(parent, bg=BG2)
        container.pack(fill="both", expand=True)

        for _, key in tab_defs:
            f = tk.Frame(container, bg=BG2)
            self.tab_frames[key] = f

        # Live feed tab — scrolled text log
        self.live_text = scrolledtext.ScrolledText(
            self.tab_frames["live"],
            font=FONT_MONO_S, bg=BG, fg=TEXT,
            insertbackground=ACCENT,
            relief="flat", bd=0,
            wrap="word",
            state="disabled",
        )
        self.live_text.pack(fill="both", expand=True, padx=2, pady=2)
        self._setup_text_tags(self.live_text)

        # Profiles tab
        self.profiles_text = scrolledtext.ScrolledText(
            self.tab_frames["profiles"],
            font=FONT_MONO_S, bg=BG, fg=TEXT,
            relief="flat", bd=0, wrap="word", state="disabled"
        )
        self.profiles_text.pack(fill="both", expand=True, padx=2, pady=2)
        self._setup_text_tags(self.profiles_text)

        # Breaches tab
        self.breaches_text = scrolledtext.ScrolledText(
            self.tab_frames["breaches"],
            font=FONT_MONO_S, bg=BG, fg=TEXT,
            relief="flat", bd=0, wrap="word", state="disabled"
        )
        self.breaches_text.pack(fill="both", expand=True, padx=2, pady=2)
        self._setup_text_tags(self.breaches_text)

        # Web tab
        self.web_text = scrolledtext.ScrolledText(
            self.tab_frames["web"],
            font=FONT_MONO_S, bg=BG, fg=TEXT,
            relief="flat", bd=0, wrap="word", state="disabled"
        )
        self.web_text.pack(fill="both", expand=True, padx=2, pady=2)
        self._setup_text_tags(self.web_text)

        # Summary tab
        self.summary_text = scrolledtext.ScrolledText(
            self.tab_frames["summary"],
            font=FONT_MONO_S, bg=BG, fg=TEXT,
            relief="flat", bd=0, wrap="word", state="disabled"
        )
        self.summary_text.pack(fill="both", expand=True, padx=2, pady=2)
        self._setup_text_tags(self.summary_text)

        self._switch_tab("live")

    def _setup_text_tags(self, widget):
        widget.tag_config("green",   foreground=ACCENT)
        widget.tag_config("cyan",    foreground=ACCENT2)
        widget.tag_config("red",     foreground=ACCENT3)
        widget.tag_config("dim",     foreground=TEXT_DIM)
        widget.tag_config("bright",  foreground=TEXT_BRIGHT)
        widget.tag_config("heading", foreground=ACCENT2, font=("Courier New", 10, "bold"))
        widget.tag_config("warn",    foreground="#ffaa00")

    def _switch_tab(self, key: str):
        self.active_tab.set(key)
        for k, f in self.tab_frames.items():
            f.pack_forget()
        self.tab_frames[key].pack(fill="both", expand=True)
        for k, btn in self.tab_buttons.items():
            btn.config(
                fg=ACCENT if k == key else TEXT_DIM,
                bg=BG3 if k == key else BG2
            )

    # ── Field helpers ─────────────────────────────────────────────────────────

    def _prefill_fields(self):
        for key, value in self.prefill.items():
            if value and key in self.fields:
                var, entry, placeholder = self.fields[key]
                entry.config(fg=TEXT)
                entry.delete(0, "end")
                entry.insert(0, value)

    def _get_field(self, key: str):
        if key not in self.fields:
            return None
        var, entry, placeholder = self.fields[key]
        val = entry.get().strip()
        return val if val and val != placeholder else None

    def _clear_fields(self):
        for key, (var, entry, placeholder) in self.fields.items():
            entry.delete(0, "end")
            entry.insert(0, placeholder)
            entry.config(fg=TEXT_DIM)
        self._clear_text(self.live_text)
        self._clear_text(self.profiles_text)
        self._clear_text(self.breaches_text)
        self._clear_text(self.web_text)
        self._clear_text(self.summary_text)
        self.status_var.set("CLEARED — Ready for new target")
        self.last_results = None

    def _clear_text(self, widget):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.config(state="disabled")

    # ── Clock ─────────────────────────────────────────────────────────────────

    def _tick_clock(self):
        self.clock_var.set(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    # ── Logging to live feed ──────────────────────────────────────────────────

    def _log(self, msg: str, tag: str = ""):
        def _write():
            self.live_text.config(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.live_text.insert("end", f"[{ts}] ", "dim")
            self.live_text.insert("end", msg + "\n", tag or "")
            self.live_text.see("end")
            self.live_text.config(state="disabled")
        self.root.after(0, _write)

    def _append_to(self, widget, msg: str, tag: str = ""):
        def _write():
            widget.config(state="normal")
            widget.insert("end", msg, tag)
            widget.config(state="disabled")
        self.root.after(0, _write)

    # ── Scan ──────────────────────────────────────────────────────────────────

    def _start_scan(self):
        if self.scanning:
            return

        params = {
            "name":     self._get_field("name"),
            "username": self._get_field("username"),
            "email":    self._get_field("email"),
            "phone":    self._get_field("phone"),
            "location": self._get_field("location"),
            "employer": self._get_field("employer"),
            "age":      self._get_field("age"),
            "website":  self._get_field("website"),
        }

        # Strip @ from username
        if params.get("username") and params["username"].startswith("@"):
            params["username"] = params["username"][1:]

        if not any([params.get("name"), params.get("username"), params.get("email")]):
            messagebox.showwarning(
                "Input Required",
                "Please enter at least a Name, Username, or Email to scan."
            )
            return

        # Clear previous results
        for w in [self.live_text, self.profiles_text,
                  self.breaches_text, self.web_text, self.summary_text]:
            self._clear_text(w)

        self.scanning = True
        self.scan_btn.config(text="◼  SCANNING...", bg="#1a3a2a", fg=ACCENT, state="disabled")
        self.status_var.set("SCANNING — Do not close window...")
        self._switch_tab("live")

        self._log("=" * 55, "dim")
        self._log("AURA OSINT ENGINE — SCAN INITIATED", "green")
        self._log(f"Target: {params.get('name') or params.get('username') or params.get('email')}", "bright")
        self._log("=" * 55, "dim")

        enabled = {k: v.get() for k, v in self.source_vars.items()}

        thread = threading.Thread(
            target=self._run_scan_thread,
            args=(params, enabled),
            daemon=True
        )
        thread.start()

    def _run_scan_thread(self, params: dict, enabled: dict):
        try:
            from tools.osint import OSINTEngine, generate_report

            # Monkey-patch the print function so we capture live output
            engine = OSINTEngine(
                web_search_fn=self.web_search_fn if enabled.get("web_search") else None
            )

            # Override engine's internal print with our log
            import builtins
            original_print = builtins.print
            def captured_print(*args, **kwargs):
                msg = " ".join(str(a) for a in args)
                self._log(msg)
                original_print(*args, **kwargs)
            builtins.print = captured_print

            results = engine.investigate(
                name     = params.get("name"),
                email    = params.get("email"),
                username = params.get("username"),
                location = params.get("location"),
            )

            builtins.print = original_print

            self.last_results = results
            self._render_results(results, params)

            # Save report
            try:
                from tools.osint import generate_report
                import re as _re
                subject = params.get("name") or params.get("username") or params.get("email") or "target"
                safe = _re.sub(r'[^a-zA-Z0-9]', '_', subject)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                os.makedirs("osint_reports", exist_ok=True)
                path = os.path.join("osint_reports", f"osint_{safe}_{ts}.docx")
                saved = generate_report(results, path)
                self._log(f"Report saved: {saved}", "green")
                self.root.after(0, lambda: self.status_var.set(f"COMPLETE — Report: {saved}"))
            except Exception as e:
                self._log(f"Report save failed: {e}", "warn")

        except Exception as e:
            logger.error(f"Scan error: {e}", exc_info=True)
            self._log(f"SCAN ERROR: {e}", "red")
            self.root.after(0, lambda: self.status_var.set(f"ERROR: {e}"))
        finally:
            self.scanning = False
            self.root.after(0, lambda: self.scan_btn.config(
                text="▶  SCAN TARGET", bg=ACCENT, fg=BG, state="normal"
            ))

    def _render_results(self, results: dict, params: dict):
        SKIP = {"found","top_repos","verified_proofs","accounts","urls","top_articles",
                "recent_posts","top_subreddits","recent_activity","top_answers","packages",
                "top_languages","organizations","starred_repos","projects","search_links"}

        def kv(widget, key, val):
            if val is None or val == "" or val == [] or val == {}:
                return
            self._append_to(widget, f"  {key.replace('_',' ').upper():<22}", "dim")
            self._append_to(widget, f"{val}\n", "bright")

        def section(widget, title):
            self._append_to(widget, f"\n{'─'*54}\n", "dim")
            self._append_to(widget, f"  {title}\n", "heading")
            self._append_to(widget, f"{'─'*54}\n", "dim")

        def render_list(widget, label, items, max_items=8):
            if not items:
                return
            self._append_to(widget, f"\n  {label}\n", "cyan")
            for item in (items[:max_items] if isinstance(items, list) else []):
                if isinstance(item, dict):
                    parts = []
                    for k, v in item.items():
                        if v and k not in ("url","links","description","desc"):
                            parts.append(f"{k}: {v}")
                    line = " | ".join(parts[:4])
                    url = item.get("url","")
                    self._append_to(widget, f"    • {line}\n", "green")
                    if url:
                        self._append_to(widget, f"      {url}\n", "dim")
                    if item.get("desc") or item.get("description"):
                        self._append_to(widget, f"      {item.get('desc') or item.get('description','')}\n", "dim")
                else:
                    self._append_to(widget, f"    • {item}\n", "green")

        # ── Platform hits tab (profiles) ──
        hits = results.get("platform_hits", [])
        if hits:
            section(self.profiles_text, f"USERNAME FOUND ON {len(hits)} PLATFORMS")
            for h in hits:
                self._append_to(self.profiles_text, f"  ✅ {h['platform']:<20}", "green")
                self._append_to(self.profiles_text, f"{h['url']}\n", "dim")

        # API profiles
        for platform, data in results.get("api_profiles", {}).items():
            if not data.get("found"):
                continue
            section(self.profiles_text, platform.upper())
            for k, v in data.items():
                if k not in SKIP:
                    kv(self.profiles_text, k, v)
            render_list(self.profiles_text, "TOP REPOS", data.get("top_repos"))
            render_list(self.profiles_text, "TOP LANGUAGES", data.get("top_languages"))
            render_list(self.profiles_text, "ORGANIZATIONS", data.get("organizations"))
            render_list(self.profiles_text, "VERIFIED IDENTITIES", data.get("verified_proofs"))
            render_list(self.profiles_text, "ACTIVE SUBREDDITS", data.get("top_subreddits"))
            render_list(self.profiles_text, "RECENT POSTS", data.get("recent_posts"))
            render_list(self.profiles_text, "PACKAGES", data.get("packages"))
            render_list(self.profiles_text, "PROJECTS", data.get("projects"))

        if not hits and not any(d.get("found") for d in results.get("api_profiles",{}).values()):
            self._append_to(self.profiles_text, "\n  No profiles found.\n", "dim")

        # Email info
        ei = results.get("email_info")
        if ei:
            section(self.profiles_text, "EMAIL ANALYSIS")
            for k, v in ei.items():
                kv(self.profiles_text, k, v)

        # Domain info
        di = results.get("domain_info")
        if di:
            section(self.profiles_text, "DOMAIN / WEBSITE")
            for k, v in di.items():
                if k != "technologies":
                    kv(self.profiles_text, k, v)
            if di.get("technologies"):
                kv(self.profiles_text, "technologies", ", ".join(di["technologies"]))

        # Phone info
        pi = results.get("phone_info")
        if pi:
            section(self.profiles_text, "PHONE")
            kv(self.profiles_text, "number",  pi.get("number"))
            kv(self.profiles_text, "country", pi.get("country"))

        # Image search links
        img = results.get("image_search", {})
        if img:
            section(self.profiles_text, "PERSON SEARCH LINKS")
            for label, url in img.items():
                self._append_to(self.profiles_text, f"  {label.replace('_',' ').title():<24}", "dim")
                self._append_to(self.profiles_text, f"{url}\n", "cyan")

        # ── Breaches tab ──
        b = results.get("data_breaches", {})
        if b.get("found"):
            self._append_to(self.breaches_text, f"\n  ⚠  FOUND IN {b['count']} BREACH(ES)\n\n", "warn")
            for breach in b.get("breaches", []):
                self._append_to(self.breaches_text, f"  ■ {breach.get('name','?')}\n", "red")
                self._append_to(self.breaches_text, f"    Domain:   {breach.get('domain','?')}\n", "dim")
                self._append_to(self.breaches_text, f"    Date:     {breach.get('breach_date','?')}\n", "dim")
                self._append_to(self.breaches_text, f"    Records:  {breach.get('pwn_count',0):,}\n", "warn")
                self._append_to(self.breaches_text, f"    Exposed:  {', '.join(breach.get('data_classes',[]))}\n", "warn")
                if breach.get("description"):
                    self._append_to(self.breaches_text, f"    Info:     {breach['description']}\n", "dim")
                self._append_to(self.breaches_text, "\n", "")
        elif b.get("found") is False:
            self._append_to(self.breaches_text, "\n  ✓ Email not found in known data breaches.\n", "green")
        else:
            self._append_to(self.breaches_text, f"\n  {b.get('message','No breach data — provide an email address')}\n", "dim")

        # ── Web tab ──
        web = results.get("web_presence", {}).get("search_results", {})
        if web:
            for category, content in web.items():
                self._append_to(self.web_text, f"\n  ■ {category}\n", "cyan")
                self._append_to(self.web_text, f"{'─'*54}\n", "dim")
                self._append_to(self.web_text, content[:1000] + "\n", "")
        else:
            self._append_to(self.web_text, "\n  No web search results (web search may be disabled).\n", "dim")

        # ── Summary tab ──
        self._append_to(self.summary_text, "\n  OSINT INTELLIGENCE SUMMARY\n", "heading")
        self._append_to(self.summary_text, f"  Target:  ", "dim")
        self._append_to(self.summary_text,
            f"{params.get('name') or params.get('username') or params.get('email')}\n", "bright")
        self._append_to(self.summary_text,
            f"  Scanned: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n", "dim")

        for line in results.get("summary", []):
            tag = "green" if "✅" in line else "warn" if "⚠" in line else "cyan"
            indent = "    " if line.startswith("   •") else "  "
            self._append_to(self.summary_text, f"{indent}{line}\n", tag)

        if results.get("errors"):
            self._append_to(self.summary_text, f"\n  ERRORS ({len(results['errors'])})\n", "warn")
            for err in results["errors"]:
                self._append_to(self.summary_text, f"  • {err}\n", "dim")

        self._log("=" * 55, "dim")
        self._log("SCAN COMPLETE", "green")
        self._log("=" * 55, "dim")
        self.root.after(0, lambda: self._switch_tab("summary"))

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_report(self):
        if not hasattr(self, "last_results") or not self.last_results:
            messagebox.showinfo("No Results", "Run a scan first before exporting.")
            return
        try:
            from tools.osint import generate_report
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                defaultextension=".docx",
                filetypes=[("Word Document", "*.docx"), ("Text File", "*.txt")],
                initialfile="osint_report.docx"
            )
            if path:
                saved = generate_report(self.last_results, path)
                messagebox.showinfo("Exported", f"Report saved to:\n{saved}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    # ── Show ──────────────────────────────────────────────────────────────────

    def show(self):
        self.root.mainloop()

    def show_nonblocking(self):
        """Open window without blocking AURA's main loop."""
        thread = threading.Thread(target=self.root.mainloop, daemon=True)
        thread.start()


def launch_osint_gui(prefill: dict = None, web_search_fn=None, blocking: bool = True):
    """
    Create and show the OSINT GUI.
    Call from main.py when OSINT intent is detected.
    """
    gui = OSINTGui(prefill=prefill, web_search_fn=web_search_fn)
    if blocking:
        gui.show()
    else:
        gui.show_nonblocking()