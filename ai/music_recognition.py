# ============================================
# FILE: music_recognition.py
# Fixed: credentials loaded from environment via config, hmac call corrected
# ============================================

import sounddevice as sd
import numpy as np
import wave
import hmac
import hashlib
import base64
import time
import os
import logging
import requests

logger = logging.getLogger(__name__)

class MusicRecognitionSystem:
    """
    ACRCloud-based music recognition.
    Credentials are read from environment variables:
        ACR_HOST, ACR_ACCESS_KEY, ACR_ACCESS_SECRET
    which should be set in your .env file and loaded by config.py.
    """

    def __init__(self, host: str = None, access_key: str = None, access_secret: str = None):
        self.host = host or os.environ.get("ACR_HOST", "identify-us-west-2.acrcloud.com")
        self.access_key = access_key or os.environ.get("ACR_ACCESS_KEY", "")
        self.access_secret = access_secret or os.environ.get("ACR_ACCESS_SECRET", "")
        self.sample_rate = 44100
        self.duration = 8

        if not self.access_key or not self.access_secret:
            logger.warning("ACRCloud credentials not set. Music recognition will fail.")

    def record_clip(self) -> np.ndarray:
        print("🎵 Listening for music...")
        recording = sd.rec(
            int(self.duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype='int16'
        )
        sd.wait()
        return recording

    def recognize(self) -> dict | None:
        audio = self.record_clip()
        filename = f"temp_capture_{os.getpid()}.wav"

        try:
            # Write WAV file
            with wave.open(filename, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit = 2 bytes
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio.tobytes())

            file_size = os.path.getsize(filename)
            timestamp = str(int(time.time()))

            # Build HMAC-SHA1 signature (corrected argument order)
            string_to_sign = (
                f"POST\n/v1/identify\n{self.access_key}\naudio\n1\n{timestamp}"
            )
            sign = base64.b64encode(
                hmac.new(
                    self.access_secret.encode('utf-8'),
                    string_to_sign.encode('utf-8'),
                    hashlib.sha1
                ).digest()
            ).decode('utf-8')

            with open(filename, "rb") as audio_file:
                files = {"sample": audio_file}
                data = {
                    "access_key": self.access_key,
                    "sample_bytes": file_size,
                    "timestamp": timestamp,
                    "signature": sign,
                    "data_type": "audio",
                    "signature_version": "1",
                }
                resp = requests.post(
                    f"https://{self.host}/v1/identify",
                    files=files,
                    data=data,
                    timeout=15
                )
                response = resp.json()

            status = response.get("status", {})
            if status.get("code") == 0:
                music = response["metadata"]["music"][0]
                return {
                    "title": music.get("title", "Unknown"),
                    "artist": music["artists"][0]["name"] if music.get("artists") else "Unknown",
                    "cover_url": music.get("album", {}).get("cover"),
                    "spotify_id": (
                        music.get("external_metadata", {})
                            .get("spotify", {})
                            .get("track", {})
                            .get("id")
                    ),
                }
            else:
                logger.warning(f"ACRCloud returned non-zero status: {status}")
                return None

        except Exception as e:
            logger.error(f"Music recognition error: {e}")
            return None
        finally:
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except OSError as e:
                    logger.warning(f"Could not remove temp file {filename}: {e}")