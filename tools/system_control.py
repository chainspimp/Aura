import subprocess
import psutil
import pyautogui
import json
import requests
from config import OLLAMA_API_URL, OLLAMA_MODEL

class SystemController:
    def __init__(self):
        pass
    
    def open_app(self, app_name: str):
        try:
            print(f"🚀 Opening: {app_name}")
            subprocess.Popen(app_name, shell=True)
            return f"Opened {app_name}"
        except Exception as e:
            return f"Failed to open {app_name}: {e}"
    
    def close_app(self, app_name: str):
        closed = False
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if app_name.lower() in proc.info['name'].lower():
                    proc.kill()
                    closed = True
            except:
                pass
        return f"Closed {app_name}" if closed else f"No running app named {app_name}"
    
    def click(self, x: int, y: int):
        pyautogui.click(x, y)
        return f"Clicked at {x}, {y}"
    
    def type_text(self, text: str):
        pyautogui.write(text, interval=0.02)
        return f"Typed: {text}"

def decide_system_action(user_prompt):
    system_prompt = f"""You are an AI that controls Windows.

User request: {user_prompt}

Return ONLY valid JSON (no other text):
{{"action": "open_app", "target": "notepad"}}
{{"action": "close_app", "target": "chrome"}}
{{"action": "type_text", "target": "Hello World"}}

Your response:"""
    
    resp = requests.post(
        OLLAMA_API_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": system_prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 200}
        },
        timeout=60
    )
    txt = resp.json().get("response", "").strip()
    try:
        return json.loads(txt)
    except:
        return None

def execute_system_action(action_json):
    if not action_json:
        return None
    
    controller = SystemController()
    action = action_json.get("action")
    target = action_json.get("target", "")
    
    if action == "open_app":
        return controller.open_app(target)
    elif action == "close_app":
        return controller.close_app(target)
    elif action == "type_text":
        return controller.type_text(target)
    
    return "Unknown system action."