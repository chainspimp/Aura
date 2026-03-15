import os
import time
import re
import subprocess
import winsound
import threading
from config import PIPER_PATH, PIPER_MODEL

try:
    import pygame
    pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
    pygame_available = True
except:
    pygame_available = False

class InterruptibleTTS:
    def __init__(self):
        self.interrupted = False
        self.is_speaking = False
    
    def speak(self, text, cfg):
        self.interrupted = False
        self.is_speaking = True
        if text.strip() and cfg.get('voice_enabled', True):
            result = text_to_speech(text)
        else:
            result = False
        self.is_speaking = False
        return result
    
    def interrupt(self):
        self.interrupted = True
        self.is_speaking = False
        if pygame_available and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()

def clean_text(txt):
    if not txt:
        return ""
    txt = txt[:500]  # Max length
    txt = re.sub(r'[\U0001F600-\U0001F64F]+', '', txt, flags=re.UNICODE)
    txt = ' '.join(txt.split())
    replacements = {'"':'"', '"':'"', ''': "'", ''': "'", '…':'...'}
    for old, new in replacements.items():
        txt = txt.replace(old, new)
    return ''.join(c for c in txt if ord(c) < 256 and (c.isprintable() or c.isspace())).strip()

def text_to_speech(txt):
    if not txt.strip():
        return False
    
    out = f"output_{threading.current_thread().ident}.wav"
    try:
        txt = clean_text(txt)
        if not txt.strip():
            return False
        
        proc = subprocess.Popen(
            [PIPER_PATH, '--model', PIPER_MODEL, '--output_file', out],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        proc.communicate(input=txt, timeout=30)
        
        if proc.returncode != 0 or not os.path.exists(out):
            return False
        
        success = play_audio(out)
        return success
    except:
        return False
    finally:
        if os.path.exists(out):
            time.sleep(0.5)
            try:
                os.remove(out)
            except:
                pass

def play_audio(fp):
    if not os.path.exists(fp):
        return False
    
    # Try winsound first
    try:
        winsound.PlaySound(fp, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
        return True
    except:
        pass
    
    # Try pygame
    if pygame_available:
        try:
            pygame.mixer.music.load(fp)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            return True
        except:
            pass
    
    return False