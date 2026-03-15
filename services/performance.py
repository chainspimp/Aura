import time
from collections import deque

class PerformanceMonitor:
    def __init__(self):
        self.metrics = {
            'response_times': deque(maxlen=1000),
            'tts_times': deque(maxlen=1000),
            'vision_times': deque(maxlen=1000),
            'speech_recognition_times': deque(maxlen=1000),
            'thinking_times': deque(maxlen=1000),
            'tool_times': deque(maxlen=1000)
        }
        self.start_time = time.time()
    
    def log(self, category, value):
        if category in self.metrics:
            self.metrics[category].append(value)
    
    def stats(self):
        stats = {}
        for cat, values in self.metrics.items():
            if values:
                stats[cat] = {
                    'avg': sum(values) / len(values),
                    'max': max(values),
                    'min': min(values),
                    'count': len(values)
                }
            else:
                stats[cat] = {'avg': 0, 'max': 0, 'min': 0, 'count': 0}
        stats['uptime'] = time.time() - self.start_time
        return stats