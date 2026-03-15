# ============================================
# FILE: ai/planner.py
# Task planner — now uses centralized LLMClient
# ============================================

import json
import re
import logging
from config import OLLAMA_MODEL
from ai.llm_client import plan_call

logger = logging.getLogger(__name__)

MAX_STEPS = 8

_PLANNER_SYSTEM = """You are an AI task planner. Break the user's request into a sequence of tool-based steps.
Respond ONLY in valid JSON. No markdown. No explanation."""

_TOOLS_DOC = """Available tools:
- web_search       : search the web for current information
- deep_research    : thorough multi-query research on a topic
- thinking         : deep reasoning to analyse or solve a problem
- code_generation  : write and save a code file
- image_generation : generate an image from a description
- vision           : analyse the current camera view
- save_doc         : write and save a Word (.docx) report
- save_txt         : write and save a plain text file
- final_answer     : produce the final response to the user"""


def create_plan(user_prompt: str, context: str = "") -> list:
    prompt = f"""{_TOOLS_DOC}

Respond ONLY with valid JSON:
{{
  "steps": [
    {{"tool": "tool_name", "input": "what to pass to this tool"}},
    ...
  ]
}}

Rules:
- Always end with "save_doc", "save_txt", or "final_answer"
- Maximum {MAX_STEPS} steps
- No explanations. JSON only.

User Request: {user_prompt}
Context: {context}"""

    raw = plan_call(OLLAMA_MODEL, prompt)

    if raw:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if "steps" in parsed and isinstance(parsed["steps"], list):
                    return parsed["steps"][:MAX_STEPS]
            except json.JSONDecodeError:
                pass

    logger.warning("Planner LLM failed — using keyword fallback")
    return _keyword_fallback(user_prompt)


def _keyword_fallback(prompt: str) -> list:
    low   = prompt.lower()
    steps = []

    if any(w in low for w in ['research', 'find', 'search', 'look up', 'latest', 'news']):
        steps.append({"tool": "deep_research", "input": prompt})
    elif any(w in low for w in ['web', 'internet', 'online', 'current']):
        steps.append({"tool": "web_search", "input": prompt})

    if any(w in low for w in ['code', 'script', 'program', 'write', 'build',
                               'create', 'game', 'app', 'function']):
        steps.append({"tool": "code_generation", "input": prompt})

    if any(w in low for w in ['image', 'picture', 'draw', 'generate image', 'visualise']):
        steps.append({"tool": "image_generation", "input": prompt})

    if any(w in low for w in ['analyse', 'analyze', 'explain', 'compare', 'think', 'why']):
        steps.append({"tool": "thinking", "input": prompt})

    if any(w in low for w in ['report', 'document', 'word', 'docx']):
        steps.append({"tool": "save_doc", "input": prompt})

    steps.append({"tool": "final_answer", "input": prompt})
    logger.info(f"Keyword fallback plan: {[s['tool'] for s in steps]}")
    return steps
