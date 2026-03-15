import json
import time
import pyaudio
from vosk import Model, KaldiRecognizer
from config import VOSK_MODEL_PATH, SAMPLE_RATE, CHUNK_SIZE, LISTEN_TIMEOUT

try:
    import webrtcvad
    webrtcvad_available = True
except:
    webrtcvad_available = False

# Initialize model once
vosk_model = Model(VOSK_MODEL_PATH)

def listen(timeout=LISTEN_TIMEOUT):
    start = time.time()
    try:
        rec = KaldiRecognizer(vosk_model, SAMPLE_RATE)
        vad = webrtcvad.Vad(3) if webrtcvad_available else None
        
        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE
        )
        
        silence_start = None
        has_spoken = False
        
        while time.time() - start < timeout:
            if stream.get_read_available() < CHUNK_SIZE:
                time.sleep(0.01)
                continue
            
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            
            # Check if speech
            if vad:
                is_speech = vad.is_speech(data, SAMPLE_RATE)
            else:
                # Simple energy-based detection
                energy = sum(abs(int.from_bytes(data[i:i+2], 'little', signed=True)) 
                           for i in range(0, len(data), 2)) / (len(data)//2)
                is_speech = energy > 1000
            
            if is_speech:
                has_spoken = True
                silence_start = None
            elif has_spoken and not silence_start:
                silence_start = time.time()
            elif has_spoken and silence_start and time.time() - silence_start > 1.5:
                break
            
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if txt := result.get("text", "").strip():
                    stream.stop_stream()
                    stream.close()
                    audio.terminate()
                    return txt, True
        
        txt = json.loads(rec.FinalResult()).get("text", "").strip()
        stream.stop_stream()
        stream.close()
        audio.terminate()
        return txt, bool(txt)
    except:
        return "", False