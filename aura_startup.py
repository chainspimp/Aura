# =============================================================================
# FILE: aura_startup.py
# AURA System Bootstrap — wires all new systems into AURA on launch
#
# USAGE:  Add this to the top of your main_gui.py:
#
#   from aura_startup import bootstrap_aura
#   bootstrap_aura(aura_respond_fn)   # pass your existing respond function
#
# Or call each function individually if you prefer finer control.
# =============================================================================

import os
import sys
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


def bootstrap_aura(aura_respond_fn=None):
    """
    Full AURA bootstrap:
      1. Print platform dependency report
      2. Load all skills
      3. Start proactive scheduler
      4. Start Telegram bot (if configured)
      5. Wire browser tool into tool executor

    aura_respond_fn: callable(text: str, context: str) -> str
                     Your existing AURA response handler.
                     Needed for scheduler job callbacks and Telegram.
    """
    from config import load_config
    cfg = load_config()

    # 1. Platform check (non-blocking, just logs)
    _check_platform()

    # 2. Load skills
    if cfg.get("enable_skills", True):
        _load_skills()

    # 3. Start scheduler
    if cfg.get("enable_scheduler", True):
        _start_scheduler(aura_respond_fn)

    # 4. Start Telegram bot
    if cfg.get("enable_telegram_bot", False) and aura_respond_fn:
        _start_telegram(aura_respond_fn)

    # 5. Warm up browser (lazy — only starts when first used)
    if cfg.get("enable_browser", True):
        _register_browser()

    logger.info("✅ AURA bootstrap complete")


# ── 1. Platform check ─────────────────────────────────────────────────────────

def _check_platform():
    try:
        from platform_compat import check_platform_deps, SYSTEM
        deps   = check_platform_deps()
        failed = [k for k, v in deps.items() if not v]
        if failed:
            logger.warning(f"Missing optional deps: {', '.join(failed)}")
        logger.info(f"Platform: {SYSTEM} — {len(deps) - len(failed)}/{len(deps)} deps OK")
    except Exception as e:
        logger.debug(f"Platform check skipped: {e}")


# ── 2. Skills ─────────────────────────────────────────────────────────────────

def _load_skills():
    try:
        from skills.skill_loader import get_registry
        registry = get_registry()
        n = len(registry.list_skills())
        logger.info(f"🔧 Skills loaded: {n} skill(s) active")
    except Exception as e:
        logger.warning(f"Skills load failed: {e}")


# ── 3. Scheduler ──────────────────────────────────────────────────────────────

def _start_scheduler(aura_respond_fn=None):
    try:
        from scheduler import get_scheduler

        def on_job_fire(job):
            """Called when a scheduled job triggers."""
            logger.info(f"⏰ Scheduled task: {job.name}")
            if not aura_respond_fn:
                return
            try:
                response = aura_respond_fn(job.task, context="scheduled_task")
                logger.info(f"Scheduler response: {response[:200]}")
            except Exception as e:
                logger.error(f"Scheduler job execution error: {e}")

        sched = get_scheduler(on_trigger=on_job_fire)
        sched.start()
        logger.info("📅 Scheduler started")
    except Exception as e:
        logger.warning(f"Scheduler start failed: {e}")


# ── 4. Telegram ───────────────────────────────────────────────────────────────

def _start_telegram(aura_respond_fn):
    telegram_token = os.environ.get("TELEGRAM_TOKEN", "")
    if not telegram_token:
        logger.info("Telegram bot disabled (TELEGRAM_TOKEN not set)")
        return
    try:
        from telegram_bot import AuraTelegramBot
        bot = AuraTelegramBot(aura_respond_fn)
        if bot.start():
            logger.info("🤖 Telegram bot started")
        else:
            logger.warning("Telegram bot failed to start")
    except Exception as e:
        logger.warning(f"Telegram bot start failed: {e}")


# ── 5. Browser ────────────────────────────────────────────────────────────────

def _register_browser():
    try:
        from tools.browser import PLAYWRIGHT_AVAILABLE
        if PLAYWRIGHT_AVAILABLE:
            logger.info("🌐 Browser tool ready (Playwright available)")
        else:
            logger.info("🌐 Browser tool disabled (install playwright)")
    except Exception as e:
        logger.debug(f"Browser check skipped: {e}")


# =============================================================================
# REQUIREMENTS  (add these to your requirements.txt)
# =============================================================================

NEW_REQUIREMENTS = """
# ── AURA v2 new dependencies ──────────────────────────────────────────────────

# Skills system (no extra deps — stdlib only)

# Telegram bot remote interface
python-telegram-bot>=20.0

# Browser automation (cross-platform, replaces fragile screenshot→click)
playwright>=1.40.0
# After installing: playwright install chromium

# Proactive scheduler daemon
APScheduler>=3.10.0

# Cross-platform TTS fallbacks (Linux)
# sudo apt install espeak-ng   (Debian/Ubuntu)
# brew install espeak           (macOS)

# Cross-platform screenshot (Linux fallback)
# sudo apt install scrot        (Debian/Ubuntu)
"""
