import time
import subprocess
import logging

logger = logging.getLogger(__name__)

class ServiceManager:
    def __init__(self):
        self.ollama_failures = 0
        self.max_failures = 3
    
    def record_failure(self):
        self.ollama_failures += 1
        logger.warning(f"Ollama failures: {self.ollama_failures}")
    
    def record_success(self):
        self.ollama_failures = 0
    
    def should_restart(self):
        return self.ollama_failures >= self.max_failures
    
    def restart_ollama(self):
        try:
            subprocess.Popen(
                ['ollama', 'serve'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(5)
            self.ollama_failures = 0
            return True
        except:
            return False