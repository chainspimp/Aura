import os
import sys
import time
import logging
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from datetime import datetime
from typing import Tuple, Optional
from config import IMAGE_OUTPUT_DIR

logger = logging.getLogger(__name__)

# ── Pipeline cache ─────────────────────────────────────────────────────────────
_pipelines: dict = {}   # keyed by quality level
_pipeline_lock   = threading.Lock()


# ── Quality tiers ──────────────────────────────────────────────────────────────
#
# Each tier defines:
#   model_id    — HuggingFace model to load
#   steps       — inference steps
#   guidance    — guidance scale (0.0 = turbo/distilled, 7.5 = classic)
#   size        — output resolution
#   dtype       — torch dtype string
#   download_gb — approximate download size on first use
#   vram_gb     — minimum VRAM recommended
#   time_cpu    — estimated seconds on CPU
#   time_4gb    — estimated seconds on 4GB GPU
#   time_8gb    — estimated seconds on 8GB GPU
#   time_12gb   — estimated seconds on 12GB+ GPU
#
QUALITY_TIERS = {
    "draft": {
        "label":       "⚡ Draft",
        "description": "Tiny model, lowest quality. Good for testing prompts.",
        "model_id":    "segmind/tiny-sd",
        "pipeline":    "StableDiffusionPipeline",
        "steps":       10,
        "guidance":    7.5,
        "size":        (512, 512),
        "dtype":       "float32",
        "download_gb": 0.2,
        "vram_gb":     2,
        "time_cpu":    "60–120 sec",
        "time_4gb":    "5–10 sec",
        "time_8gb":    "3–6 sec",
        "time_12gb":   "2–4 sec",
    },
    "fast": {
        "label":       "🚀 Fast",
        "description": "SDXL-Turbo. 4-step generation, good quality, very fast.",
        "model_id":    "stabilityai/sdxl-turbo",
        "pipeline":    "AutoPipelineForText2Image",
        "steps":       4,
        "guidance":    0.0,
        "size":        (512, 512),
        "dtype":       "float16",
        "download_gb": 6.9,
        "vram_gb":     6,
        "time_cpu":    "3–8 min",
        "time_4gb":    "15–30 sec",
        "time_8gb":    "8–15 sec",
        "time_12gb":   "4–8 sec",
    },
    "balanced": {
        "label":       "⚖️ Balanced",
        "description": "SDXL base. Higher quality, more detail, takes longer.",
        "model_id":    "stabilityai/stable-diffusion-xl-base-1.0",
        "pipeline":    "AutoPipelineForText2Image",
        "steps":       25,
        "guidance":    7.5,
        "size":        (1024, 1024),
        "dtype":       "float16",
        "download_gb": 6.9,
        "vram_gb":     8,
        "time_cpu":    "20–40 min",
        "time_4gb":    "2–4 min",
        "time_8gb":    "40–90 sec",
        "time_12gb":   "20–40 sec",
    },
    "quality": {
        "label":       "✨ Quality",
        "description": "SDXL + refiner pass. Best detail and sharpness.",
        "model_id":    "stabilityai/stable-diffusion-xl-base-1.0",
        "pipeline":    "AutoPipelineForText2Image",
        "steps":       40,
        "guidance":    7.5,
        "size":        (1024, 1024),
        "dtype":       "float16",
        "download_gb": 13.5,
        "vram_gb":     12,
        "time_cpu":    "45–90 min",
        "time_4gb":    "4–8 min",
        "time_8gb":    "90–180 sec",
        "time_12gb":   "40–80 sec",
    },
}


# ── GPU VRAM detection ─────────────────────────────────────────────────────────

def _get_vram_gb() -> float:
    """Return available GPU VRAM in GB. Returns 0 if no GPU detected."""
    try:
        import torch
        if torch.cuda.is_available():
            vram = torch.cuda.get_device_properties(0).total_memory
            return round(vram / (1024 ** 3), 1)
    except Exception:
        pass
    return 0.0


def _time_estimate(tier: dict, vram_gb: float) -> str:
    """Pick the right time estimate based on detected VRAM."""
    if vram_gb >= 12:
        return tier["time_12gb"]
    elif vram_gb >= 8:
        return tier["time_8gb"]
    elif vram_gb >= 4:
        return tier["time_4gb"]
    else:
        return tier["time_cpu"]


# ══════════════════════════════════════════════════════════════════════════════
# QUALITY PICKER DIALOG
# ══════════════════════════════════════════════════════════════════════════════

BG      = "#0b0f1e"
SURFACE = "#111827"
EDGE    = "#1e293b"
BLUE    = "#3b82f6"
BLUE2   = "#60a5fa"
T1      = "#f1f5f9"
T2      = "#94a3b8"
T3      = "#475569"
GREEN   = "#22c55e"
AMBER   = "#f59e0b"


class QualityPickerDialog:
    """
    Popup dialog that asks the user which quality tier to use.
    Returns the chosen tier key or None if cancelled.
    """

    def __init__(self, prompt: str):
        self.prompt    = prompt
        self.chosen    = None
        self._vram_gb  = _get_vram_gb()

        self.root = tk.Tk()
        self.root.withdraw()

        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self.root.title("AURA — Image Quality")
        self.root.configure(bg=BG)
        self.root.geometry("640x520")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

        self._build()

        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"640x520+{(sw-640)//2}+{(sh-520)//2}")

        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.attributes("-topmost", True)
        self.root.after(200, lambda: self.root.attributes("-topmost", False))

    def _build(self):
        # Header
        hdr = tk.Frame(self.root, bg=SURFACE, height=52)
        hdr.pack(side="top", fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="🎨  Choose Image Quality",
                 font=("Trebuchet MS", 13, "bold"),
                 fg=BLUE, bg=SURFACE).pack(side="left", padx=20)

        # GPU info
        vram_str = (f"GPU: {self._vram_gb}GB VRAM detected"
                    if self._vram_gb > 0 else "No GPU detected — using CPU")
        tk.Label(hdr, text=vram_str,
                 font=("Segoe UI", 9), fg=T3, bg=SURFACE).pack(side="right", padx=16)

        # Prompt preview
        short_prompt = self.prompt[:80] + ("..." if len(self.prompt) > 80 else "")
        tk.Label(self.root, text=f'"{short_prompt}"',
                 font=("Segoe UI", 9, "italic"), fg=T3, bg=BG,
                 wraplength=580).pack(padx=20, pady=(12, 4))

        tk.Frame(self.root, bg=EDGE, height=1).pack(fill="x", padx=20, pady=4)

        # Quality tier buttons
        content = tk.Frame(self.root, bg=BG)
        content.pack(fill="both", expand=True, padx=20, pady=8)

        for key, tier in QUALITY_TIERS.items():
            self._tier_card(content, key, tier)

        # Cancel button
        tk.Frame(self.root, bg=EDGE, height=1).pack(fill="x", padx=20, pady=(4, 0))
        cancel_row = tk.Frame(self.root, bg=BG)
        cancel_row.pack(fill="x", padx=20, pady=10)
        tk.Button(cancel_row, text="Cancel",
                  font=("Segoe UI", 10), fg=T3, bg=BG,
                  activeforeground=T2, activebackground=BG,
                  relief="flat", bd=0, cursor="hand2",
                  command=self._cancel).pack(side="right")

    def _tier_card(self, parent, key: str, tier: dict):
        time_est   = _time_estimate(tier, self._vram_gb)
        vram_ok    = self._vram_gb >= tier["vram_gb"] or self._vram_gb == 0
        warn_color = T2 if vram_ok else AMBER

        card = tk.Frame(parent, bg=SURFACE, padx=14, pady=10,
                        cursor="hand2")
        card.pack(fill="x", pady=3)

        # Left: label + description
        left = tk.Frame(card, bg=SURFACE)
        left.pack(side="left", fill="x", expand=True)

        top_row = tk.Frame(left, bg=SURFACE)
        top_row.pack(anchor="w")
        tk.Label(top_row, text=tier["label"],
                 font=("Segoe UI", 11, "bold"),
                 fg=T1, bg=SURFACE).pack(side="left")
        tk.Label(top_row, text=f"  {tier['size'][0]}×{tier['size'][1]}",
                 font=("Consolas", 9), fg=T3, bg=SURFACE).pack(side="left")

        tk.Label(left, text=tier["description"],
                 font=("Segoe UI", 9), fg=T2, bg=SURFACE).pack(anchor="w")

        # Right: time estimate + VRAM note
        right = tk.Frame(card, bg=SURFACE)
        right.pack(side="right", padx=4)

        tk.Label(right, text=f"⏱  {time_est}",
                 font=("Segoe UI", 9, "bold"),
                 fg=GREEN, bg=SURFACE).pack(anchor="e")

        vram_note = (f"needs {tier['vram_gb']}GB VRAM"
                     if self._vram_gb > 0 and not vram_ok
                     else f"~{tier['download_gb']}GB download")
        tk.Label(right, text=vram_note,
                 font=("Segoe UI", 8), fg=warn_color, bg=SURFACE).pack(anchor="e")

        # Click anywhere on the card to select
        def select(k=key):
            self.chosen = k
            self.root.destroy()

        card.bind("<Button-1>", lambda e, k=key: select(k))
        for child in card.winfo_children():
            child.bind("<Button-1>", lambda e, k=key: select(k))
            for sub in child.winfo_children():
                sub.bind("<Button-1>", lambda e, k=key: select(k))

        # Hover effect
        def on_enter(e, f=card):
            f.config(bg=EDGE)
            for c in f.winfo_children():
                try:
                    c.config(bg=EDGE)
                except Exception:
                    pass

        def on_leave(e, f=card):
            f.config(bg=SURFACE)
            for c in f.winfo_children():
                try:
                    c.config(bg=SURFACE)
                except Exception:
                    pass

        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

    def _cancel(self):
        self.chosen = None
        self.root.destroy()

    def ask(self) -> Optional[str]:
        self.root.mainloop()
        return self.chosen


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE LOADER
# ══════════════════════════════════════════════════════════════════════════════

def _load_pipeline(quality: str):
    """Load and cache the pipeline for the given quality tier."""
    global _pipelines

    if quality in _pipelines:
        return _pipelines[quality], None

    with _pipeline_lock:
        if quality in _pipelines:
            return _pipelines[quality], None

        tier = QUALITY_TIERS[quality]
        model_id     = tier["model_id"]
        pipeline_cls = tier["pipeline"]
        dtype_str    = tier["dtype"]

        try:
            import torch
            from diffusers import (
                AutoPipelineForText2Image,
                StableDiffusionPipeline,
            )

            dtype = torch.float16 if dtype_str == "float16" else torch.float32
            use_gpu = torch.cuda.is_available()
            device  = "cuda" if use_gpu else "cpu"

            # float16 only works on GPU — fall back to float32 on CPU
            if not use_gpu:
                dtype = torch.float32

            print(f"   📥 Loading {tier['label']} model ({tier['download_gb']}GB)...")
            print(f"   Device: {device.upper()}"
                  + (f"  ({_get_vram_gb()}GB VRAM)" if use_gpu else " (no GPU)"))

            if pipeline_cls == "StableDiffusionPipeline":
                pipe = StableDiffusionPipeline.from_pretrained(
                    model_id,
                    torch_dtype=dtype,
                    safety_checker=None,
                )
            else:
                pipe = AutoPipelineForText2Image.from_pretrained(
                    model_id,
                    torch_dtype=dtype,
                    variant="fp16" if (use_gpu and dtype_str == "float16") else None,
                )

            pipe = pipe.to(device)
            pipe.enable_attention_slicing()

            if use_gpu:
                try:
                    pipe.enable_xformers_memory_efficient_attention()
                except Exception:
                    pass
            else:
                try:
                    pipe.enable_vae_slicing()
                    pipe.enable_vae_tiling()
                except Exception:
                    pass

            _pipelines[quality] = pipe
            logger.info(f"Pipeline loaded: {quality} ({model_id})")
            return pipe, None

        except ImportError:
            return None, "diffusers_missing"
        except Exception as e:
            logger.error(f"Pipeline load error ({quality}): {e}")
            return None, str(e)


def unload_pipelines():
    """Release all cached pipelines from memory."""
    global _pipelines
    import gc
    with _pipeline_lock:
        _pipelines.clear()
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    logger.info("All image pipelines unloaded")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN GENERATION FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def generate_image_local(prompt: str, image_count: int = 0,
                          quality: str = None) -> Tuple[str, Optional[str]]:
    """
    Generate an image locally.

    If quality is None (default), shows a picker dialog so the user
    can choose their preferred quality / speed tradeoff.
    """
    try:
        # ── Show quality picker if not pre-specified ───────────────────────
        if quality is None:
            picker = QualityPickerDialog(prompt)
            quality = picker.ask()
            if quality is None:
                return "Image generation cancelled.", None

        tier = QUALITY_TIERS.get(quality, QUALITY_TIERS["fast"])

        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(
            IMAGE_OUTPUT_DIR, f"image_{quality}_{timestamp}_{image_count}.png"
        )

        vram_gb   = _get_vram_gb()
        time_est  = _time_estimate(tier, vram_gb)
        w, h      = tier["size"]

        print(f"\n🎨 Generating image: {prompt}")
        print(f"   Quality: {tier['label']}  |  Size: {w}×{h}"
              f"  |  Steps: {tier['steps']}")
        print(f"   ⏱  Estimated time: {time_est}")

        # ── Load pipeline ──────────────────────────────────────────────────
        pipe, err = _load_pipeline(quality)

        if err == "diffusers_missing":
            return (
                "⚠️ Diffusers not installed.\n"
                "Run: py -3.11 -m pip install diffusers transformers accelerate torch"
            ), None

        if pipe is None:
            # Try falling back to draft quality
            if quality != "draft":
                print(f"   ⚠️  {tier['label']} failed — falling back to Draft mode")
                return generate_image_local(prompt, image_count, quality="draft")
            return f"Image generation failed: {err}", None

        # ── Generate ───────────────────────────────────────────────────────
        print("   ⚡ Generating...")
        start = time.time()

        gen_kwargs = dict(
            prompt              = prompt,
            num_inference_steps = tier["steps"],
            guidance_scale      = tier["guidance"],
            height              = h,
            width               = w,
        )

        image = pipe(**gen_kwargs).images[0]

        elapsed = time.time() - start
        print(f"   💾 Saving... ({elapsed:.1f}s)")
        image.save(output_path)
        print(f"✅ Done: {output_path}")

        return (
            f"Image generated! ({tier['label'].split()[1]} mode)\n"
            f"Prompt: {prompt}\n"
            f"Size: {w}×{h}  |  Time: {elapsed:.1f}s\n"
            f"Saved to: {output_path}"
        ), output_path

    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return f"Image generation failed: {e}", None


# ══════════════════════════════════════════════════════════════════════════════
# DISPLAY WINDOW
# ══════════════════════════════════════════════════════════════════════════════

def display_image(image_path: str, prompt: str):
    """Display the generated image with Save / Regenerate / Close buttons."""
    try:
        from PIL import Image, ImageTk

        window = tk.Tk()
        window.title("AURA — Generated Image")
        window.configure(bg=BG)

        img = Image.open(image_path)
        if img.width > 800 or img.height > 800:
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)

        photo = ImageTk.PhotoImage(img)

        tk.Label(window, image=photo, bg=BG).pack(padx=10, pady=(10, 4))
        tk.Label(window,
                 text=f'"{prompt[:80]}{"..." if len(prompt) > 80 else ""}"',
                 font=("Segoe UI", 9, "italic"), fg=T2, bg=BG,
                 wraplength=760).pack()

        btn_row = tk.Frame(window, bg=BG)
        btn_row.pack(pady=10)

        def save_as():
            fp = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("All", "*.*")],
                initialfile=f"aura_{int(time.time())}.png"
            )
            if fp:
                try:
                    Image.open(image_path).save(fp)
                    messagebox.showinfo("Saved", f"Saved to:\n{fp}")
                except Exception as e:
                    messagebox.showerror("Error", str(e))

        def regenerate():
            window.destroy()
            generate_image_local(prompt, int(time.time()))

        for text, cmd, color in [
            ("💾 Save As", save_as,           BLUE),
            ("🔄 Regenerate", regenerate,     "#14532d"),
            ("✖ Close", window.destroy,      EDGE),
        ]:
            tk.Button(btn_row, text=text, command=cmd,
                      font=("Segoe UI", 10), fg=T1, bg=color,
                      activeforeground=T1, activebackground=SURFACE,
                      relief="flat", bd=0, padx=18, pady=7,
                      cursor="hand2").pack(side="left", padx=6)

        tk.Label(window, text=f"Saved: {image_path}",
                 font=("Segoe UI", 8), fg=T3, bg=BG).pack(pady=(0, 8))

        window.update_idletasks()
        x = (window.winfo_screenwidth()  - window.winfo_width())  // 2
        y = (window.winfo_screenheight() - window.winfo_height()) // 2
        window.geometry(f"+{x}+{y}")
        window.mainloop()

    except ImportError:
        print("⚠️ tkinter/PIL not available")
        try:
            if sys.platform == "win32":
                os.startfile(image_path)
        except Exception:
            print(f"Open manually: {image_path}")
    except Exception as e:
        logger.error(f"Display error: {e}")
        print(f"Image saved to: {image_path}")
