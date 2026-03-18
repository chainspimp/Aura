# =============================================================================
# FILE: telegram_bot.py
# AURA Telegram Bot — Remote Interface
#
# Lets you talk to AURA from your phone via Telegram.
# Supports: text messages, voice notes, photos (vision), commands.
#
# Setup:
#   1. Message @BotFather on Telegram → /newbot → copy the token
#   2. Add TELEGRAM_TOKEN=<your_token> to your .env file
#   3. Add TELEGRAM_ALLOWED_IDS=123456789 (your Telegram user ID, comma-sep)
#   4. Run:  python telegram_bot.py
#      Or start alongside AURA: set TELEGRAM_BOT_ENABLED=true in .env
#
# Requirements:
#   pip install python-telegram-bot
# =============================================================================

import os
import sys
import io
import logging
import asyncio
import tempfile
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Try to import python-telegram-bot ────────────────────────────────────────
try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        filters, ContextTypes
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not installed. Run: pip install python-telegram-bot")


# ── Config ────────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

# Comma-separated list of allowed Telegram user IDs (leave empty to allow all)
_raw_ids = os.environ.get("TELEGRAM_ALLOWED_IDS", "")
ALLOWED_IDS: set[int] = (
    {int(x.strip()) for x in _raw_ids.split(",") if x.strip()}
    if _raw_ids else set()
)


# =============================================================================
# BOT HANDLERS
# =============================================================================

def _make_handlers(aura_respond):
    """
    Build all Telegram handlers.
    aura_respond(text, context_hint) → str
    is injected at runtime so this module stays decoupled from AURA core.
    """

    # ── Auth gate ─────────────────────────────────────────────────────────────

    def _is_allowed(user_id: int) -> bool:
        return (not ALLOWED_IDS) or (user_id in ALLOWED_IDS)

    async def _deny(update: Update):
        await update.message.reply_text(
            "⛔ You are not authorised to use this AURA instance.\n"
            f"Your ID: `{update.effective_user.id}`",
            parse_mode="Markdown"
        )

    # ── /start ────────────────────────────────────────────────────────────────

    async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_allowed(update.effective_user.id):
            return await _deny(update)
        await update.message.reply_text(
            "👋 *AURA is online.*\n\n"
            "Send any message to talk to your assistant.\n\n"
            "*Commands:*\n"
            "/skills — list loaded skills\n"
            "/memory — show what AURA remembers about you\n"
            "/schedule — show scheduled tasks\n"
            "/status — system status\n"
            "/help — this message",
            parse_mode="Markdown"
        )

    # ── /help ─────────────────────────────────────────────────────────────────

    async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await cmd_start(update, ctx)

    # ── /skills ───────────────────────────────────────────────────────────────

    async def cmd_skills(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_allowed(update.effective_user.id):
            return await _deny(update)
        try:
            from skills.skill_loader import get_registry
            skills = get_registry().list_skills()
            if not skills:
                return await update.message.reply_text("No skills loaded.")
            lines = ["*🔧 Loaded Skills:*\n"]
            for s in skills:
                lines.append(f"{s.icon} *{s.name}* v{s.version}\n  _{s.description}_")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"Error listing skills: {e}")

    # ── /schedule ─────────────────────────────────────────────────────────────

    async def cmd_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_allowed(update.effective_user.id):
            return await _deny(update)
        try:
            from scheduler import get_scheduler
            sched = get_scheduler()
            jobs  = sched.list_jobs()
            if not jobs:
                return await update.message.reply_text("No scheduled tasks.")
            lines = ["*📅 Scheduled Tasks:*\n"]
            for j in jobs:
                lines.append(
                    f"• *{j['name']}*\n"
                    f"  `{j['trigger']}` — next: {j.get('next_run', '?')}"
                )
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"Scheduler not available: {e}")

    # ── /memory ───────────────────────────────────────────────────────────────

    async def cmd_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_allowed(update.effective_user.id):
            return await _deny(update)
        try:
            from core.memory import list_knowledge
            facts = list_knowledge()
            if not facts:
                return await update.message.reply_text("AURA has no stored facts yet.")
            lines = ["*🧠 What AURA knows:*\n"]
            for f in facts[:20]:  # cap at 20 for Telegram
                lines.append(f"• [{f.get('category','?')}] {f['text']}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"Memory unavailable: {e}")

    # ── /status ───────────────────────────────────────────────────────────────

    async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_allowed(update.effective_user.id):
            return await _deny(update)
        import platform
        import psutil
        cpu  = psutil.cpu_percent(interval=0.5)
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        await update.message.reply_text(
            f"*🖥️ AURA System Status*\n\n"
            f"OS: `{platform.system()} {platform.release()}`\n"
            f"CPU: `{cpu}%`\n"
            f"RAM: `{ram.percent}%` used ({ram.used // (1024**3):.1f} / {ram.total // (1024**3):.1f} GB)\n"
            f"Disk: `{disk.percent}%` used",
            parse_mode="Markdown"
        )

    # ── Text message ──────────────────────────────────────────────────────────

    async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_allowed(update.effective_user.id):
            return await _deny(update)

        user_msg = update.message.text.strip()
        if not user_msg:
            return

        # Show typing indicator
        await update.message.chat.send_action("typing")

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: aura_respond(user_msg, "telegram")
            )
            # Telegram has a 4096-char limit — split if needed
            for chunk in _split_message(response):
                await update.message.reply_text(chunk)
        except Exception as e:
            logger.error(f"Telegram text handler error: {e}", exc_info=True)
            await update.message.reply_text(f"⚠️ Error: {e}")

    # ── Voice note ────────────────────────────────────────────────────────────

    async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_allowed(update.effective_user.id):
            return await _deny(update)

        await update.message.reply_text("🎙️ Transcribing voice note...")
        try:
            voice_file = await update.message.voice.get_file()
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                await voice_file.download_to_drive(tmp.name)
                tmp_path = tmp.name

            # Transcribe with Vosk or fallback message
            transcript = _transcribe_voice(tmp_path)
            os.unlink(tmp_path)

            if not transcript:
                return await update.message.reply_text("⚠️ Could not transcribe audio.")

            await update.message.reply_text(f"📝 Heard: _{transcript}_", parse_mode="Markdown")
            await update.message.chat.send_action("typing")

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: aura_respond(transcript, "telegram_voice")
            )
            for chunk in _split_message(response):
                await update.message.reply_text(chunk)

        except Exception as e:
            await update.message.reply_text(f"Voice error: {e}")

    # ── Photo (vision) ────────────────────────────────────────────────────────

    async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_allowed(update.effective_user.id):
            return await _deny(update)

        caption = update.message.caption or "Describe this image."
        await update.message.reply_text("👁️ Analysing image...")
        try:
            photo   = update.message.photo[-1]   # largest size
            p_file  = await photo.get_file()
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                await p_file.download_to_drive(tmp.name)
                tmp_path = tmp.name

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: aura_respond(
                    f"[IMAGE ATTACHED] {caption}",
                    f"image_path:{tmp_path}"
                )
            )
            os.unlink(tmp_path)
            for chunk in _split_message(response):
                await update.message.reply_text(chunk)
        except Exception as e:
            await update.message.reply_text(f"Image error: {e}")

    return {
        "start":   cmd_start,
        "help":    cmd_help,
        "skills":  cmd_skills,
        "schedule": cmd_schedule,
        "memory":  cmd_memory,
        "status":  cmd_status,
        "text":    handle_text,
        "voice":   handle_voice,
        "photo":   handle_photo,
    }


# =============================================================================
# HELPERS
# =============================================================================

def _split_message(text: str, limit: int = 4000) -> list[str]:
    """Split a long message into Telegram-safe chunks."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks


def _transcribe_voice(ogg_path: str) -> str:
    """
    Transcribe a .ogg voice note using Vosk.
    Falls back gracefully if Vosk is not configured.
    """
    try:
        import vosk
        import wave
        import json
        import subprocess

        # Convert ogg → wav
        wav_path = ogg_path.replace(".ogg", ".wav")
        subprocess.run(
            ["ffmpeg", "-i", ogg_path, "-ar", "16000", "-ac", "1", wav_path, "-y"],
            capture_output=True, timeout=15
        )
        if not os.path.exists(wav_path):
            return ""

        vosk_model_path = os.environ.get("VOSK_MODEL_PATH", "")
        if not vosk_model_path or not os.path.exists(vosk_model_path):
            return ""

        model = vosk.Model(vosk_model_path)
        rec   = vosk.KaldiRecognizer(model, 16000)

        with wave.open(wav_path, "rb") as wf:
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                rec.AcceptWaveform(data)

        result = json.loads(rec.FinalResult())
        os.unlink(wav_path)
        return result.get("text", "")
    except Exception as e:
        logger.warning(f"Voice transcription failed: {e}")
        return ""


# =============================================================================
# BOT RUNNER
# =============================================================================

class AuraTelegramBot:
    """
    Manages the Telegram bot lifecycle.

    Usage:
        def my_aura_respond(text, context): return "Hello!"
        bot = AuraTelegramBot(my_aura_respond)
        bot.start()          # runs in background thread
        ...
        bot.stop()
    """

    def __init__(self, aura_respond_fn):
        self._fn     = aura_respond_fn
        self._app    = None
        self._thread = None
        self._loop   = None

    def start(self) -> bool:
        if not TELEGRAM_AVAILABLE:
            logger.error("python-telegram-bot not installed.")
            return False
        if not TELEGRAM_TOKEN:
            logger.error("TELEGRAM_TOKEN not set in .env — bot disabled.")
            return False

        self._thread = threading.Thread(target=self._run, daemon=True, name="TelegramBot")
        self._thread.start()
        logger.info("🤖 Telegram bot started in background")
        return True

    def stop(self):
        if self._app and self._loop:
            asyncio.run_coroutine_threadsafe(self._app.stop(), self._loop)

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_run())

    async def _async_run(self):
        handlers = _make_handlers(self._fn)

        self._app = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .build()
        )

        # Register commands
        self._app.add_handler(CommandHandler("start",    handlers["start"]))
        self._app.add_handler(CommandHandler("help",     handlers["help"]))
        self._app.add_handler(CommandHandler("skills",   handlers["skills"]))
        self._app.add_handler(CommandHandler("schedule", handlers["schedule"]))
        self._app.add_handler(CommandHandler("memory",   handlers["memory"]))
        self._app.add_handler(CommandHandler("status",   handlers["status"]))

        # Register message handlers
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers["text"]))
        self._app.add_handler(MessageHandler(filters.VOICE, handlers["voice"]))
        self._app.add_handler(MessageHandler(filters.PHOTO, handlers["photo"]))

        # Set bot commands in Telegram UI
        await self._app.bot.set_my_commands([
            BotCommand("start",    "Start AURA"),
            BotCommand("skills",   "List loaded skills"),
            BotCommand("schedule", "View scheduled tasks"),
            BotCommand("memory",   "What AURA remembers"),
            BotCommand("status",   "System status"),
            BotCommand("help",     "Show help"),
        ])

        logger.info(f"Telegram bot polling (allowed IDs: {ALLOWED_IDS or 'all'})")
        await self._app.run_polling(drop_pending_updates=True)


# =============================================================================
# STANDALONE ENTRY POINT
# Run:  python telegram_bot.py
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Import AURA's real response function
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from ai.llm_client import call as llm_call
        from config import OLLAMA_MODEL

        def aura_respond(text: str, context: str = "") -> str:
            return llm_call(
                OLLAMA_MODEL,
                f"User: {text}\nContext: {context}\n\nRespond helpfully and concisely.",
                system="You are AURA, a helpful AI assistant.",
                max_tokens=800,
                timeout_key="chat"
            )
    except Exception as e:
        print(f"[WARN] Could not import AURA core ({e}) — using echo mode")
        def aura_respond(text: str, context: str = "") -> str:
            return f"Echo: {text}"

    bot = AuraTelegramBot(aura_respond)
    if not bot.start():
        sys.exit(1)

    print("Telegram bot running. Press Ctrl+C to stop.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot.stop()
        print("Bot stopped.")
