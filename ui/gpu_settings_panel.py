# =============================================================================
# FILE: ui/gpu_settings_panel.py
# AURA GPU & Image Generation Settings Panel
#
# A Tkinter settings panel that surfaces GPU/device config for image gen.
# Integrates with the existing image_gen.py QUALITY_TIERS system.
#
# Usage — add to your main_gui.py settings window:
#   from ui.gpu_settings_panel import GPUSettingsPanel
#   panel = GPUSettingsPanel(parent_frame, app_config, save_config_fn)
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import logging

logger = logging.getLogger(__name__)

# ── Theme colours (match AURA's obsidian dark theme) ──────────────────────────
BG      = "#0b0f1e"
SURFACE = "#111827"
EDGE    = "#1e293b"
BLUE    = "#3b82f6"
BLUE2   = "#60a5fa"
GREEN   = "#22c55e"
AMBER   = "#f59e0b"
RED     = "#ef4444"
T1      = "#f1f5f9"
T2      = "#94a3b8"
T3      = "#475569"


class GPUSettingsPanel(tk.Frame):
    """
    Settings panel for GPU / image generation configuration.
    Embed this in any Tkinter Frame.
    """

    def __init__(self, parent, app_config: dict, save_config_fn=None, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self._cfg      = app_config
        self._save_cfg = save_config_fn
        self._gpu_info = {}
        self._build()
        self._detect_gpu_async()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        # Title
        tk.Label(
            self, text="🎨  Image Generation & GPU",
            font=("Segoe UI", 12, "bold"),
            fg=BLUE, bg=BG
        ).pack(anchor="w", padx=16, pady=(16, 4))

        # GPU status card
        self._gpu_frame = tk.Frame(self, bg=SURFACE, bd=0)
        self._gpu_frame.pack(fill="x", padx=16, pady=(0, 12))

        self._gpu_label = tk.Label(
            self._gpu_frame,
            text="🔍 Detecting GPU...",
            font=("Segoe UI", 10), fg=T2, bg=SURFACE, justify="left"
        )
        self._gpu_label.pack(anchor="w", padx=12, pady=10)

        # Device selection
        self._build_device_row()

        # Default quality tier
        self._build_quality_row()

        # Precision
        self._build_precision_row()

        # Memory optimisations
        self._build_memory_section()

        # Benchmark button
        tk.Button(
            self,
            text="⚡ Run Benchmark (generate test image)",
            font=("Segoe UI", 9),
            fg=T1, bg=EDGE, relief="flat", cursor="hand2",
            command=self._run_benchmark
        ).pack(fill="x", padx=16, pady=(4, 0))

        # Save button
        tk.Button(
            self,
            text="💾  Save GPU Settings",
            font=("Segoe UI", 10, "bold"),
            fg="#000", bg=GREEN, relief="flat", cursor="hand2",
            command=self._save
        ).pack(fill="x", padx=16, pady=(8, 16))

    def _build_device_row(self):
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=16, pady=4)

        tk.Label(row, text="Device:", font=("Segoe UI", 10),
                 fg=T2, bg=BG, width=18, anchor="w").pack(side="left")

        self._device_var = tk.StringVar(
            value=self._cfg.get("image_device", "auto")
        )
        for val, label in [("auto", "Auto-detect"), ("cuda", "GPU (CUDA)"),
                            ("cpu", "CPU only"), ("mps", "Apple MPS")]:
            tk.Radiobutton(
                row, text=label, variable=self._device_var, value=val,
                font=("Segoe UI", 9), fg=T2, bg=BG,
                selectcolor=EDGE, activebackground=BG,
                command=self._on_device_change
            ).pack(side="left", padx=6)

    def _build_quality_row(self):
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=16, pady=4)

        tk.Label(row, text="Default quality:", font=("Segoe UI", 10),
                 fg=T2, bg=BG, width=18, anchor="w").pack(side="left")

        self._quality_var = tk.StringVar(
            value=self._cfg.get("image_default_quality", "ask")
        )
        quality_options = ["ask", "draft", "fast", "balanced", "quality"]
        quality_menu = ttk.Combobox(
            row, textvariable=self._quality_var,
            values=quality_options, state="readonly", width=14,
            font=("Segoe UI", 9)
        )
        quality_menu.pack(side="left", padx=4)

        tk.Label(
            row,
            text="('ask' = show picker dialog each time)",
            font=("Segoe UI", 8), fg=T3, bg=BG
        ).pack(side="left", padx=8)

    def _build_precision_row(self):
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=16, pady=4)

        tk.Label(row, text="Precision:", font=("Segoe UI", 10),
                 fg=T2, bg=BG, width=18, anchor="w").pack(side="left")

        self._precision_var = tk.StringVar(
            value=self._cfg.get("image_precision", "auto")
        )
        for val, label in [("auto", "Auto"), ("float16", "float16 (GPU, faster)"),
                            ("float32", "float32 (CPU safe)")]:
            tk.Radiobutton(
                row, text=label, variable=self._precision_var, value=val,
                font=("Segoe UI", 9), fg=T2, bg=BG,
                selectcolor=EDGE, activebackground=BG
            ).pack(side="left", padx=6)

    def _build_memory_section(self):
        sep = tk.Frame(self, bg=EDGE, height=1)
        sep.pack(fill="x", padx=16, pady=8)

        tk.Label(
            self, text="Memory Optimisations",
            font=("Segoe UI", 10, "bold"), fg=T2, bg=BG
        ).pack(anchor="w", padx=16)

        opts = [
            ("attention_slicing",    "Attention slicing (saves ~20% VRAM)"),
            ("vae_slicing",          "VAE slicing (CPU: reduces RAM spikes)"),
            ("xformers",             "xFormers memory-efficient attention (GPU only)"),
            ("sequential_offload",   "Sequential CPU offload (min VRAM, very slow)"),
        ]
        self._mem_vars = {}
        for key, label in opts:
            var = tk.BooleanVar(value=self._cfg.get(f"imggen_{key}", key != "sequential_offload"))
            self._mem_vars[key] = var
            tk.Checkbutton(
                self, text=label, variable=var,
                font=("Segoe UI", 9), fg=T2, bg=BG,
                selectcolor=EDGE, activebackground=BG
            ).pack(anchor="w", padx=28, pady=1)

    # ── GPU Detection ─────────────────────────────────────────────────────────

    def _detect_gpu_async(self):
        threading.Thread(target=self._detect_gpu, daemon=True).start()

    def _detect_gpu(self):
        info = _get_gpu_info()
        self._gpu_info = info
        self.after(0, lambda: self._update_gpu_label(info))

    def _update_gpu_label(self, info: dict):
        if info.get("cuda"):
            name   = info.get("name", "Unknown GPU")
            vram   = info.get("vram_gb", 0)
            color  = GREEN
            text   = f"✅ GPU: {name}  |  VRAM: {vram}GB  |  CUDA {info.get('cuda_version','')}"
            # Auto-set device to cuda if auto-detect
            if self._device_var.get() == "auto":
                self._device_var.set("cuda")
        elif info.get("mps"):
            color = AMBER
            text  = "🍎 Apple Silicon MPS available"
            if self._device_var.get() == "auto":
                self._device_var.set("mps")
        else:
            color = RED
            text  = "⚠️  No GPU detected — image generation will use CPU (slow)"
            self._device_var.set("cpu")

        self._gpu_label.config(text=text, fg=color)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_device_change(self):
        device = self._device_var.get()
        if device == "cpu":
            self._precision_var.set("float32")
        elif device in ("cuda", "mps"):
            self._precision_var.set("float16")

    def _run_benchmark(self):
        """Generate a quick test image and report the time."""
        def _bench():
            self.after(0, lambda: messagebox.showinfo(
                "Benchmark",
                "Generating test image: 'a red circle on white background'\n\n"
                "Check the AURA chat window for timing results."
            ))
            try:
                import time
                from tools.image_gen import generate_image_local
                self._apply_to_config()
                start = time.time()
                result, _ = generate_image_local(
                    "a red circle on a white background",
                    quality=self._cfg.get("image_default_quality", "fast")
                )
                elapsed = time.time() - start
                self.after(0, lambda: messagebox.showinfo(
                    "Benchmark Complete",
                    f"✅ Generated in {elapsed:.1f}s\nDevice: {self._device_var.get()}"
                ))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Benchmark Error", str(e)))

        threading.Thread(target=_bench, daemon=True).start()

    def _apply_to_config(self):
        """Write current UI state to config dict."""
        self._cfg["image_device"]          = self._device_var.get()
        self._cfg["image_default_quality"] = self._quality_var.get()
        self._cfg["image_precision"]       = self._precision_var.get()
        for key, var in self._mem_vars.items():
            self._cfg[f"imggen_{key}"] = var.get()

    def _save(self):
        self._apply_to_config()
        _patch_image_gen(self._cfg)
        if self._save_cfg:
            self._save_cfg(self._cfg)
        messagebox.showinfo("Saved", "GPU settings saved and applied.")


# =============================================================================
# IMAGE GEN PATCHER
# Applies the config to the live image_gen pipeline loader at runtime
# =============================================================================

def _patch_image_gen(cfg: dict):
    """
    Monkey-patch tools/image_gen._load_pipeline to use the config device/dtype.
    This avoids rewriting image_gen.py entirely while giving full config control.
    """
    try:
        import tools.image_gen as ig

        device_cfg    = cfg.get("image_device", "auto")
        precision_cfg = cfg.get("image_precision", "auto")

        _orig_load = ig._load_pipeline

        def _patched_load(quality: str):
            import torch
            pipe, err = _orig_load(quality)
            if pipe is None:
                return pipe, err

            # Determine device
            if device_cfg == "auto":
                device = "cuda" if torch.cuda.is_available() else \
                         "mps"  if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else \
                         "cpu"
            else:
                device = device_cfg

            # Determine dtype
            if precision_cfg == "auto":
                dtype = torch.float16 if device != "cpu" else torch.float32
            elif precision_cfg == "float16":
                dtype = torch.float16
            else:
                dtype = torch.float32

            # Move to device with correct dtype
            try:
                pipe = pipe.to(device=device, dtype=dtype)
                logger.info(f"Image pipeline: device={device}, dtype={dtype}")
            except Exception as e:
                logger.warning(f"Pipeline move to {device} failed: {e}")

            # Memory optimisations
            if cfg.get("imggen_attention_slicing", True):
                try: pipe.enable_attention_slicing()
                except Exception: pass

            if cfg.get("imggen_vae_slicing", True) and device == "cpu":
                try: pipe.enable_vae_slicing()
                except Exception: pass

            if cfg.get("imggen_xformers", False) and device == "cuda":
                try: pipe.enable_xformers_memory_efficient_attention()
                except Exception: pass

            if cfg.get("imggen_sequential_offload", False):
                try: pipe.enable_sequential_cpu_offload()
                except Exception: pass

            return pipe, None

        ig._load_pipeline = _patched_load
        logger.info("image_gen patched with GPU config")

    except Exception as e:
        logger.warning(f"Could not patch image_gen: {e}")


# =============================================================================
# HELPERS
# =============================================================================

def _get_gpu_info() -> dict:
    info = {"cuda": False, "mps": False}
    try:
        import torch
        if torch.cuda.is_available():
            info["cuda"]         = True
            info["name"]         = torch.cuda.get_device_name(0)
            info["vram_gb"]      = round(
                torch.cuda.get_device_properties(0).total_memory / 1024**3, 1
            )
            info["cuda_version"] = torch.version.cuda or ""
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            info["mps"] = True
    except Exception:
        pass
    return info


# =============================================================================
# STANDALONE TEST
# python -m ui.gpu_settings_panel
# =============================================================================

if __name__ == "__main__":
    root = tk.Tk()
    root.title("AURA — GPU Settings")
    root.configure(bg=BG)
    root.geometry("640x560")

    cfg = {
        "image_device":          "auto",
        "image_default_quality": "ask",
        "image_precision":       "auto",
    }

    def _save(c):
        print("Saved config:", {k: v for k, v in c.items() if "image" in k or "imggen" in k})

    panel = GPUSettingsPanel(root, cfg, _save)
    panel.pack(fill="both", expand=True)
    root.mainloop()
