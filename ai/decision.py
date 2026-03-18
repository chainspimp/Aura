# =============================================================================
# FILE: ai/decision_v3.py  (replace ai/decision.py)
# AURA Decision System v3
#
# New in this version:
#   - Multi-agent routing (should_use_multi_agent check)
#   - Memory recall injection (cross-session recall in context)
# =============================================================================

import json
import re
import logging
from typing import Dict
from config import OLLAMA_MODEL
from ai.llm_client import route_call

logger = logging.getLogger(__name__)

_ROUTE_SYSTEM = """You are a tool router. Return ONLY a raw JSON object with no markdown, no explanation.
Set each tool to true only if the user explicitly needs it."""

_ROUTE_TEMPLATE = """{
  "code_generation":  false,
  "web_search":       false,
  "deep_research":    false,
  "deep_thinking":    false,
  "image_generation": false,
  "face_recognition": false,
  "vision_analysis":  false,
  "music_recognition":false,
  "computer_use":     false,
  "browser_use":      false,
  "schedule":         false,
  "multi_agent":      false
}"""

_SCHEDULE_KWS = [
    "remind me","schedule","every day","every hour","every week",
    "every monday","every morning","set an alarm","alert me","notify me",
    "in 10 minutes","in 30 minutes","every night","daily at","cron"
]
_BROWSER_KWS = [
    "go to","open website","browse to","visit","fill in the form",
    "log in to","click on","scrape","web automation","fill out"
]


class DecisionSystem:
    def __init__(self, tool_executor, thinking_system,
                 coding_system=None, face_system=None, music_system=None):
        self.tools        = tool_executor
        self.thinking     = thinking_system
        self.coding       = coding_system
        self.face         = face_system
        self.music_system = music_system

    def ai_route(self, prompt: str, context: str) -> Dict[str, bool]:
        routing_prompt = (
            f"{_ROUTE_TEMPLATE}\n\n"
            f"Only set tools to true if explicitly needed.\n"
            f"User request: {prompt}"
        )
        raw = route_call(OLLAMA_MODEL, routing_prompt)
        if raw:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        # Keyword fallback
        low = prompt.lower()
        if any(kw in low for kw in _SCHEDULE_KWS):
            return {"schedule": True}
        if any(kw in low for kw in _BROWSER_KWS):
            return {"browser_use": True}
        if any(kw in low for kw in ['write','make','create','code','python','script']):
            return {"code_generation": True}
        from ai.computer_use import should_use_computer
        if should_use_computer(prompt):
            return {"computer_use": True}
        return {}

    def decide_and_execute(self, prompt: str, context: str) -> Dict[str, any]:
        actions = {
            'thinking_used':False,'web_used':False,'research_used':False,
            'vision_used':False,'image_generated':False,'code_generated':False,
            'face_recognized':False,'thinking_result':'','web_result':'',
            'research_result':'','vision_result':'','image_result':'',
            'code_result':{},'face_result':{},'computer_used':False,
            'computer_result':'','skill_used':False,'skill_result':'',
            'browser_used':False,'browser_result':'','schedule_used':False,
            'schedule_result':'','multi_agent_used':False,'multi_agent_result':'',
            'recall_injected':False,'recall_context':'',
        }

        # ── 0. Cross-session memory recall injection ──────────────────────────
        try:
            from core.memory_enhanced import get_recall_context
            recall_ctx = get_recall_context(prompt)
            if recall_ctx:
                actions['recall_injected'] = True
                actions['recall_context']  = recall_ctx
                context = recall_ctx + "\n\n" + context
        except Exception as e:
            logger.debug(f"Recall skipped: {e}")

        # ── 1. Skills fast-path ───────────────────────────────────────────────
        try:
            from config import load_config
            cfg = load_config()
            if cfg.get("enable_skills", True):
                from skills.skill_loader import get_registry
                skill_result = get_registry().execute(prompt, context)
                if skill_result:
                    actions['skill_used']   = True
                    actions['skill_result'] = skill_result.output
                    return actions
        except Exception as e:
            logger.debug(f"Skills skipped: {e}")

        # ── 2. Scheduler ──────────────────────────────────────────────────────
        low = prompt.lower()
        if any(kw in low for kw in _SCHEDULE_KWS):
            try:
                from scheduler import get_scheduler
                sched = get_scheduler()
                if not sched._started:
                    sched.start()
                result = sched.schedule_from_text(prompt)
                actions['schedule_used']   = True
                actions['schedule_result'] = result
                return actions
            except Exception as e:
                logger.warning(f"Scheduler error: {e}")

        # ── 3. Multi-agent check ──────────────────────────────────────────────
        try:
            from ai.multi_agent import should_use_multi_agent, AgentCoordinator
            if should_use_multi_agent(prompt):
                coordinator = AgentCoordinator(self.tools, self.thinking, self.coding)
                ma_result   = coordinator.run(prompt, context)
                actions['multi_agent_used']   = True
                actions['multi_agent_result'] = ma_result.final_answer
                return actions
        except Exception as e:
            logger.warning(f"Multi-agent skipped: {e}")

        # ── 4. Normal LLM routing ─────────────────────────────────────────────
        from ai.computer_use import should_use_computer
        route = {"computer_use": True} if should_use_computer(prompt) \
            else self.ai_route(prompt, context)

        if route.get("browser_use"):
            try:
                from tools.browser import browser_task
                result = browser_task(prompt, context)
                actions['browser_used']   = True
                actions['browser_result'] = result.output
            except Exception as e:
                actions['browser_result'] = f"Browser error: {e}"
            return actions

        if route.get("computer_use"):
            try:
                from ai.computer_use import execute_computer_task
                actions['computer_result'] = execute_computer_task(prompt)
                actions['computer_used']   = True
            except Exception as e:
                actions['computer_result'] = f"Computer use error: {e}"
            return actions

        if route.get("web_search") and self.tools:
            try:
                from tools.web_search import web_search
                actions['web_result'] = web_search(prompt)
                actions['web_used']   = True
            except Exception as e:
                logger.warning(f"Web search error: {e}")

        if route.get("deep_research") and self.tools:
            try:
                from tools.web_search import deep_research
                actions['research_result'] = deep_research(prompt)
                actions['research_used']   = True
            except Exception as e:
                logger.warning(f"Deep research error: {e}")

        if route.get("deep_thinking") and self.thinking:
            try:
                actions['thinking_result'] = self.thinking.think(prompt)
                actions['thinking_used']   = True
            except Exception as e:
                logger.warning(f"Thinking error: {e}")

        if route.get("code_generation") and self.coding:
            try:
                actions['code_result']    = self.coding.generate(prompt)
                actions['code_generated'] = True
            except Exception as e:
                logger.warning(f"Code gen error: {e}")

        if route.get("image_generation") and self.tools:
            try:
                from tools.image_gen import generate_image_local
                actions['image_result']    = generate_image_local(prompt)
                actions['image_generated'] = True
            except Exception as e:
                logger.warning(f"Image gen error: {e}")

        if route.get("vision_analysis"):
            try:
                from ai.vision import capture_and_describe
                actions['vision_result'] = capture_and_describe()
                actions['vision_used']   = True
            except Exception as e:
                logger.warning(f"Vision error: {e}")

        if route.get("music_recognition") and self.music_system:
            try:
                result = self.music_system.recognize()
                if result:
                    actions['web_result'] = str(result)
                    actions['web_used']   = True
            except Exception as e:
                logger.warning(f"Music error: {e}")

        return actions
