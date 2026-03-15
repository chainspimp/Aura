# ============================================
# FILE: ai/planner.py
# Fixed: timeout raised to 120s, smart keyword fallback plan on timeout
# ============================================

import requests
import json
import re
import logging
from config import OLLAMA_API_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

MAX_STEPS = 8

def create_plan(user_prompt: str, context: str = "") -> list:
    planner_prompt = f"""You are an AI task planner. Break the user's request into a sequence of tool-based steps.

Available tools:
- web_search       : search the web for current information
- deep_research    : do thorough multi-query research on a topic
- thinking         : use deep reasoning to analyse or solve a problem
- code_generation  : write and save a code file
- image_generation : generate an image from a description
- vision           : analyse the current camera view
- save_doc         : write and save a Word (.docx) report from all gathered info
- save_txt         : write and save a plain text file from all gathered info
- final_answer     : produce the final spoken/text response to the user

Respond ONLY in valid JSON:
{{
  "steps": [
    {{"tool": "tool_name", "input": "what to pass to this tool"}},
    ...
  ]
}}

Rules:
- Always end with either "save_doc", "save_txt", or "final_answer"
- Use "save_doc" when the user wants a report, document, or Word file
- Use "save_txt" when the user wants a saved text output but not a Word doc
- Use "final_answer" when no file saving is needed
- Maximum {MAX_STEPS} steps
- No explanations. JSON only.

User Request: {user_prompt}

Context: {context}
"""

    try:
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": planner_prompt,
                "stream": False,
                "options": {"temperature": 0.2}
            },
            timeout=120  # raised from 60 — local Ollama can be slow
        )
        response.raise_for_status()
        raw = response.json().get("response", "").strip()

        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            if "steps" in parsed and isinstance(parsed["steps"], list):
                return parsed["steps"][:MAX_STEPS]
    except Exception as e:
        logger.warning(f"Planner LLM failed ({e}), using keyword fallback plan...")
        print(f"   Planner timed out, building plan from keywords instead...")

    return _keyword_fallback_plan(user_prompt)


def _keyword_fallback_plan(prompt: str) -> list:
    """
    Build a sensible plan from keywords when the LLM planner times out.
    Ensures agent mode still does real work even if planning fails.
    """
    low = prompt.lower()
    steps = []

    # Research
    if any(w in low for w in ['research', 'find', 'search', 'look up', 'latest', 'news', 'what is', 'who is']):
        steps.append({"tool": "deep_research", "input": prompt})
    elif any(w in low for w in ['web', 'internet', 'online', 'current']):
        steps.append({"tool": "web_search", "input": prompt})

    # Code
    if any(w in low for w in ['code', 'script', 'program', 'write', 'build', 'create', 'game', 'app', 'function', 'snake', 'calculator', 'tool']):
        steps.append({"tool": "code_generation", "input": prompt})

    # Image
    if any(w in low for w in ['image', 'picture', 'screenshot', 'photo', 'draw', 'generate image', 'visualise', 'visual', 'concept art']):
        steps.append({"tool": "image_generation", "input": prompt})

    # Reasoning
    if any(w in low for w in ['analyse', 'analyze', 'explain', 'compare', 'think', 'reason', 'why', 'how does']):
        steps.append({"tool": "thinking", "input": prompt})

    # Document saving
    if any(w in low for w in ['report', 'document', 'word', 'docx', 'save report', 'write up']):
        steps.append({"tool": "save_doc", "input": prompt})

    # Always end with final_answer
    steps.append({"tool": "final_answer", "input": prompt})

    tools = [s['tool'] for s in steps]
    print(f"   Keyword fallback plan: {tools}")
    return steps