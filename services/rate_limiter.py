import time
import threading
from collections import deque

class RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()
        self.lock = threading.Lock()
    
    def allow(self):
        with self.lock:
            now = time.time()
            while self.calls and self.calls[0] < now - self.period:
                self.calls.popleft()
            
            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                return True
            return False