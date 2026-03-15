# ============================================
# FILE: decision.py
# Updated with computer_use routing
# ============================================

import json
import requests
import re
from typing import Dict
from config import OLLAMA_API_URL, OLLAMA_MODEL

class DecisionSystem:
    def __init__(self, tool_executor, thinking_system, coding_system=None, face_system=None, music_system=None):
        self.tools = tool_executor
        self.thinking = thinking_system
        self.coding = coding_system
        self.face = face_system
        self.music_system = music_system

    def ai_route(self, prompt: str, context: str) -> Dict[str, bool]:
        """Use LLM to decide which tools should be used with strict JSON parsing"""
        
        routing_prompt = f"""
You are a tool router. Return ONLY a raw JSON object. 
No markdown blocks, no explanations, no preamble.

{{
  "code_generation": false,
  "web_search": false,
  "deep_research": false,
  "deep_thinking": false,
  "image_generation": false,
  "face_recognition": false,
  "vision_analysis": false,
  "music_recognition": false,
  "computer_use": false
}}


Only use tools asked for.
User request: {prompt}
"""

        try:
            resp = requests.post(
                OLLAMA_API_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": routing_prompt,
                    "stream": False,
                    "options": {"temperature": 0}
                },
                timeout=30
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()

            # Clean raw response: find the first '{' and last '}'
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                clean_json = match.group(0)
                return json.loads(clean_json)
            
            # Fallback keyword checks if JSON fails
            code_keywords = ['write', 'make', 'create', 'code', 'python', 'script', 'program']
            if any(kw in prompt.lower() for kw in code_keywords):
                return {"code_generation": True}

            # Computer use fallback
            from ai.computer_use import should_use_computer
            if should_use_computer(prompt):
                return {"computer_use": True}
                
            return {}

        except Exception as e:
            print(f"⚠ Routing failed: {e}")
            return {}

    def decide_and_execute(self, prompt: str, context: str) -> Dict[str, any]:
        actions = {
            'thinking_used': False, 'web_used': False, 'research_used': False,
            'vision_used': False, 'image_generated': False, 'code_generated': False,
            'face_recognized': False, 'thinking_result': '', 'web_result': '',
            'research_result': '', 'vision_result': '', 'image_result': '',
            'code_result': {}, 'face_result': {},
            'computer_used': False, 'computer_result': ''
        }

        # Fast-path: check computer use trigger patterns first (no LLM call needed)
        from ai.computer_use import should_use_computer
        if should_use_computer(prompt):
            route = {"computer_use": True}
        else:
            route = self.ai_route(prompt, context)

        # ── Computer Use ──────────────────────────────────────
        if route.get("computer_use"):
            print("🖥️  Activating computer use...")
            try:
                from ai.computer_use import get_computer_agent
                agent = get_computer_agent()
                result = agent.run(prompt)
                actions['computer_used'] = True
                actions['computer_result'] = result
            except Exception as e:
                actions['computer_used'] = True
                actions['computer_result'] = f"Computer use failed: {e}"
            return actions   # short-circuit — don't run other tools

        # ── Code Generation ───────────────────────────────────
        if route.get("code_generation") and self.coding:
            print("💻 AI decided to generate code...")
            code_result = self.coding.generate_and_save(prompt, context)
            actions['code_generated'] = True
            actions['code_result'] = code_result

        # ── Web Search ────────────────────────────────────────
        if route.get("web_search"):
            print("🌐 AI decided to use web search...")
            actions['web_used'] = True
            actions['web_result'] = self.tools.web_search(prompt)

        # ── Deep Research ─────────────────────────────────────
        if route.get("deep_research"):
            print("📚 AI decided to perform deep research...")
            actions['research_used'] = True
            actions['research_result'] = self.tools.deep_research(prompt)

        # ── Deep Thinking ─────────────────────────────────────
        if route.get("deep_thinking"):
            print("🧠 AI decided deep thinking is required...")
            thinking_process, conclusion = self.thinking.deep_think(prompt, context)
            actions['thinking_used'] = True
            actions['thinking_result'] = conclusion

        # ── Image Generation ──────────────────────────────────
        if route.get("image_generation"):
            print("🎨 AI decided to generate image...")
            actions['image_generated'] = True
            actions['image_result'] = self.tools.generate_image_local(prompt)[0]

        # ── Vision Analysis ───────────────────────────────────
        if route.get("vision_analysis"):
            from ai.vision import get_visual_context
            print("📷 AI requested visual context...")
            actions['vision_used'] = True
            actions['vision_result'] = get_visual_context(force=True)

        # ── Music Recognition ─────────────────────────────────
        if route.get("music_recognition") and hasattr(self, "music_system"):
            print("🎵 AI activated music recognition mode...")
            result = self.music_system.recognize()
            actions['music_used'] = True
            actions['music_result'] = result    
 
        return actions