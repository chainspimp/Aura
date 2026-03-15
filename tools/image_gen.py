import os
import sys
import time
import logging
from datetime import datetime
from typing import Tuple, Optional
from config import IMAGE_OUTPUT_DIR

logger = logging.getLogger(__name__)

def generate_image_local(prompt: str, image_count: int = 0) -> Tuple[str, Optional[str]]:
    """Generate images locally using SDXL-Turbo - MUCH FASTER"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(IMAGE_OUTPUT_DIR, f"image_{timestamp}_{image_count}.png")
        
        print(f"🎨 Generating image: {prompt}")
        print(f"   Using SDXL-Turbo (FAST mode - 10-30 seconds)...")
        
        try:
            from diffusers import AutoPipelineForText2Image
            import torch
            
            # Use SDXL-Turbo - generates in 1-4 steps (MUCH FASTER!)
            model_id = "stabilityai/sdxl-turbo"
            
            print(f"   📥 Loading SDXL-Turbo model (first time downloads ~7GB)...")
            
            # Load optimized for CPU
            pipe = AutoPipelineForText2Image.from_pretrained(
                model_id,
                torch_dtype=torch.float32,
                variant="fp32"
            )
            pipe = pipe.to("cpu")
            
            # Aggressive memory optimizations
            pipe.enable_attention_slicing()
            pipe.enable_vae_slicing()
            pipe.enable_vae_tiling()
            
            print(f"   ⚡ Generating (only 4 steps - very fast!)...")
            
            # SDXL-Turbo is optimized for 1-4 steps only!
            image = pipe(
                prompt=prompt,
                num_inference_steps=4,
                guidance_scale=0.0,
                height=512,
                width=512
            ).images[0]
            
            print(f"   💾 Saving image...")
            image.save(output_path)
            
            print(f"✅ Image generated in ~30 seconds: {output_path}")
            
            # Clear from memory
            del pipe
            import gc
            gc.collect()
            
            return f"Image generated successfully! (FAST mode)\nPrompt: {prompt}\nSaved to: {output_path}", output_path
            
        except ImportError:
            return """⚠️ Diffusers library not installed!

Install with:
pip install diffusers transformers accelerate torch

Then try again!""", None
            
        except Exception as e:
            logger.error(f"SDXL-Turbo error: {e}, falling back to lightweight model")
            # Fallback to smaller, faster model
            try:
                from diffusers import StableDiffusionPipeline
                import torch
                
                print(f"   📥 Using ultra-lightweight model (200MB)...")
                
                # Tiny SD - only 200MB!
                model_id = "segmind/tiny-sd"
                
                pipe = StableDiffusionPipeline.from_pretrained(
                    model_id,
                    torch_dtype=torch.float32,
                    safety_checker=None
                )
                pipe = pipe.to("cpu")
                pipe.enable_attention_slicing()
                
                print(f"   ⚡ Generating (lightweight mode)...")
                
                image = pipe(
                    prompt,
                    num_inference_steps=10,
                    guidance_scale=7.5,
                    height=512,
                    width=512
                ).images[0]
                
                image.save(output_path)
                print(f"✅ Image generated: {output_path}")
                
                del pipe
                import gc
                gc.collect()
                
                return f"Image generated successfully! (Lightweight mode)\nPrompt: {prompt}\nSaved to: {output_path}", output_path
                
            except Exception as e2:
                logger.error(f"Fallback error: {e2}")
                return f"Image generation failed: {str(e2)}\n\nTry installing: pip install diffusers transformers accelerate torch", None
            
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return f"Image generation failed: {str(e)}", None

def display_image(image_path: str, prompt: str):
    """Display generated image in a window with save option"""
    try:
        import tkinter as tk
        from tkinter import messagebox, filedialog
        from PIL import Image, ImageTk
        
        # Create window
        window = tk.Tk()
        window.title(f"AURA - Generated Image")
        
        # Load image
        img = Image.open(image_path)
        
        # Resize if too large (max 800x800)
        max_size = 800
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # Convert for tkinter
        photo = ImageTk.PhotoImage(img)
        
        # Create layout
        frame = tk.Frame(window)
        frame.pack(padx=10, pady=10)
        
        # Display image
        label = tk.Label(frame, image=photo)
        label.image = photo  # Keep reference
        label.pack()
        
        # Display prompt
        prompt_label = tk.Label(frame, text=f"Prompt: {prompt}", wraplength=500, font=("Arial", 10))
        prompt_label.pack(pady=(10, 5))
        
        # Button frame
        button_frame = tk.Frame(frame)
        button_frame.pack(pady=10)
        
        def save_as():
            """Save image to user-chosen location"""
            file_path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("All files", "*.*")],
                initialfile=f"aura_generated_{int(time.time())}.png"
            )
            if file_path:
                try:
                    original_img = Image.open(image_path)
                    original_img.save(file_path)
                    messagebox.showinfo("Saved", f"Image saved to:\n{file_path}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to save: {e}")
        
        def close_window():
            """Close the window"""
            window.destroy()
        
        def regenerate():
            """Regenerate with same prompt"""
            window.destroy()
            print(f"🔄 Regenerating image...")
            generate_image_local(prompt, int(time.time()))
        
        # Buttons
        save_btn = tk.Button(button_frame, text="💾 Save As...", command=save_as, width=15, height=2, font=("Arial", 10))
        save_btn.grid(row=0, column=0, padx=5)
        
        regen_btn = tk.Button(button_frame, text="🔄 Regenerate", command=regenerate, width=15, height=2, font=("Arial", 10))
        regen_btn.grid(row=0, column=1, padx=5)
        
        close_btn = tk.Button(button_frame, text="✖ Close", command=close_window, width=15, height=2, font=("Arial", 10))
        close_btn.grid(row=0, column=2, padx=5)
        
        # Info label
        info_label = tk.Label(frame, text=f"Auto-saved to: {image_path}", font=("Arial", 8), fg="gray")
        info_label.pack(pady=(5, 0))
        
        # Center window
        window.update_idletasks()
        x = (window.winfo_screenwidth() // 2) - (window.winfo_width() // 2)
        y = (window.winfo_screenheight() // 2) - (window.winfo_height() // 2)
        window.geometry(f"+{x}+{y}")
        
        # Run window
        window.mainloop()
        
    except ImportError:
        print("⚠️ tkinter not available, image saved but can't display")
        # Fallback: open with default viewer
        try:
            if sys.platform == "win32":
                os.startfile(image_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", image_path])
            else:
                subprocess.run(["xdg-open", image_path])
        except:
            print(f"Please open manually: {image_path}")
    except Exception as e:
        logger.error(f"Display error: {e}")
        print(f"Image saved to: {image_path}")