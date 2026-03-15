# ============================================
# FILE: realtime_vision.py
# Fixed: lazy YOLO/camera load (only when start() is called), release on stop
# ============================================

import threading
import time
import logging

logger = logging.getLogger(__name__)

class RealTimeVision:
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.running = False
        self.thread = None
        self.scene_state = {"objects": [], "active": False}

        # Camera and model are created lazily to avoid startup cost
        self._cap = None
        self._model = None

    def _load_resources(self):
        """Load camera and YOLO model on first use."""
        if self._cap is None or not self._cap.isOpened():
            import cv2
            self._cap = cv2.VideoCapture(self.camera_index)
            if not self._cap.isOpened():
                raise RuntimeError(f"Cannot open camera index {self.camera_index}")

        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO("yolov8n.pt")
            logger.info("YOLO model loaded")

    def _release_resources(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        # Model can stay cached between sessions (small RAM, avoids reload)

    def vision_loop(self):
        import cv2
        while self.running:
            try:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    time.sleep(0.05)
                    continue

                results = self._model(frame, verbose=False)
                objects = set()
                for r in results:
                    for box in r.boxes:
                        cls = int(box.cls[0])
                        objects.add(self._model.names[cls])

                self.scene_state["objects"] = list(objects)
                self.scene_state["active"] = True

            except Exception as e:
                logger.error(f"Vision loop error: {e}")

            time.sleep(0.05)  # ~20 FPS

    def start(self):
        if self.running:
            print("👁️ Vision already active")
            return
        try:
            self._load_resources()
        except RuntimeError as e:
            print(f"❌ Vision start failed: {e}")
            return

        self.running = True
        self.thread = threading.Thread(target=self.vision_loop, daemon=True)
        self.thread.start()
        print("👁️ Live Vision Activated")

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
        self._release_resources()
        self.scene_state["active"] = False
        print("🛑 Live Vision Deactivated")

    def get_scene(self) -> dict:
        return self.scene_state