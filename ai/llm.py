# ============================================
# FILE: llm.py
# Core with Short-Circuiting for Code Generation
# and Computer Use
# ============================================

import time
import requests
import logging
from config import OLLAMA_API_URL, OLLAMA_MODEL
from core.memory import get_context
from core.utils import get_time_context

logger = logging.getLogger(__name__)

def build_prompt(usr, hist, tool_results=None):
    base = f"You are AURA, an advanced AI assistant created by Channing Roe.\n\n"
    base += f"Current Context:\n{get_time_context()}\n\n"
    base += f"Recent conversation:\n{get_context(hist, usr)}\n"

    if tool_results:
        if tool_results.get('thinking_used'):
            base += f"\n[Deep Thinking Result]\n{tool_results['thinking_result']}\n"
        if tool_results.get('web_used'):
            base += f"\n[Web Search Results]\n{tool_results['web_result']}\n"
        if tool_results.get('research_used'):
            base += f"\n[Research Results]\n{tool_results['research_result']}\n"
        if tool_results.get('vision_used'):
            base += f"\n[Vision Context]\n{tool_results['vision_result']}\n"

    base += f"\nUser: {usr}\nAURA:"
    return base

def get_response(prompt, hist, service_mgr=None, rate_limiter=None,
                 decision_system=None, app_config=None, vision_system=None):

    start = time.time()
    meta = {"response_time": 0, "tools_used": [], "thinking_used": False,
            "code_result": None, "computer_result": None}

    try:
        tool_results = None
        if decision_system:
            tool_results = decision_system.decide_and_execute(prompt, get_context(hist, prompt))
            meta['tools_used'] = [k for k, v in tool_results.items() if k.endswith('_used') and v]
            meta['code_result']     = tool_results.get('code_result')
            meta['computer_result'] = tool_results.get('computer_result')

        # ── SHORT-CIRCUIT: Computer Use ──
        if tool_results and tool_results.get('computer_used'):
            meta["response_time"] = time.time() - start
            result = tool_results.get('computer_result', '')
            if result and not result.startswith("Computer use failed"):
                # Extract just the action summary for the spoken response
                lines = result.split('\n')
                summary_line = next((l for l in lines if l.startswith('Task:')), lines[0] if lines else '')
                return f"✅ Done! {summary_line}", meta
            else:
                return f"⚠️ {result}", meta

        # ── SHORT-CIRCUIT: Code Generation ──
        if tool_results and tool_results.get('code_generated'):
            res = tool_results.get('code_result', {})
            meta["response_time"] = time.time() - start
            if res.get('success'):
                summary = (f"✅ Code generated successfully using {res['language'].upper()}.\n"
                          f"Saved as: {res['filename']}\n"
                          f"Path: {res['filepath']}\n"
                          f"Total Lines: {res['total_lines']}")
                return summary, meta
            else:
                return f"❌ Code generation failed: {res.get('error')}", meta

        # ── Normal conversation flow ──
        full_prompt = build_prompt(prompt, hist, tool_results)
        resp = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 400}
            },
            timeout=200
        )
        resp.raise_for_status()
        result = resp.json().get("response", "").strip()
        meta["response_time"] = time.time() - start
        return result, meta

    except Exception as e:
        logger.error(f"Error in get_response: {e}")
        return "I'm having trouble connecting to my brain right now.", meta