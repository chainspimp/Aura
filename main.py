# ============================================
# FILE: main.py
# AURA entry point — CLI mode
# ============================================

import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler

# ── Logging setup (root logger — catches everything) ──────────────────────────
_log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_file_handler  = RotatingFileHandler('aura.log', maxBytes=10*1024*1024, backupCount=5)
_file_handler.setFormatter(_log_formatter)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), _file_handler]
)
logger = logging.getLogger(__name__)

# ── First-time setup wizard ────────────────────────────────────────────────────
# Runs before config.py so the .env is written before any paths are read
from ui.setup_wizard import run_setup_if_needed
run_setup_if_needed()

# ── Imports ────────────────────────────────────────────────────────────────────
from config import load_config, save_config
from core.audio import InterruptibleTTS
from core.audio import cleanup_stale_wavs
from core.speech import listen
from core.memory import (
    load_memory, add_session_turn, log_conversation,
    get_context, clear_session, memory_stats
)
from core.utils import get_time_str
from services.performance import PerformanceMonitor
from services.rate_limiter import RateLimiter
from services.service_manager import ServiceManager
from ai.llm import get_response
from ai.llm_client import is_ollama_running, llm_stats
from ai.thinking import ThinkingSystem
from ai.decision import DecisionSystem
from ai.coding import CodingSystem
from ai.realtime_vision import RealTimeVision
from ai.music_recognition import MusicRecognitionSystem
from ai.agent import AutonomousAgent
from ai.hacker_runner import should_launch_hacker, launch_hacker_mode
from ai.vm_runner import should_launch_vm, launch_vm_mode
from tools.osint_runner import should_launch_osint, run_osint_gui
from tools.executor import ToolExecutor
from tools.system_control import decide_system_action, execute_system_action
from ui.spotify_gui import SpotifyPlaylistSelector

# ── Config & services ──────────────────────────────────────────────────────────
app_config  = load_config()
perf_mon    = PerformanceMonitor()
rate_limiter = RateLimiter(60, 60)
service_mgr  = ServiceManager()

# ── AI systems ─────────────────────────────────────────────────────────────────
interruptible_tts = InterruptibleTTS()
music_system      = MusicRecognitionSystem()
tool_executor     = ToolExecutor()
thinking_system   = ThinkingSystem()
coding_system     = CodingSystem()
vision_system     = RealTimeVision()
decision_system   = DecisionSystem(
    tool_executor, thinking_system, coding_system, None, music_system
)
agent = AutonomousAgent(tool_executor, thinking_system, coding_system)

# ── System control keyword triggers ───────────────────────────────────────────
_SYSTEM_KEYWORDS = [
    'open', 'close', 'launch', 'start', 'kill', 'type',
    'click', 'run', 'execute', 'app', 'program', 'application', 'window'
]


def _looks_like_system_command(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _SYSTEM_KEYWORDS)


# ── Startup checks ─────────────────────────────────────────────────────────────

def _startup_checks():
    """Validate environment before starting the main loop."""
    issues = []

    # Ollama
    if not is_ollama_running():
        issues.append("⚠️  Ollama is not running — start it with: ollama serve")

    # Piper TTS
    piper_path = os.environ.get("PIPER_PATH", "")
    if app_config.get("voice_enabled") and piper_path and not os.path.exists(piper_path):
        issues.append(f"⚠️  Piper TTS not found at: {piper_path}  — update PIPER_PATH in .env")

    # Vosk model
    vosk_path = os.environ.get("VOSK_MODEL_PATH", "")
    if vosk_path and not os.path.exists(vosk_path):
        issues.append(f"⚠️  Vosk model not found at: {vosk_path}  — update VOSK_MODEL_PATH in .env")

    if issues:
        print("\n" + "─" * 60)
        for issue in issues:
            print(issue)
        print("─" * 60 + "\n")

    return len(issues) == 0


# ── Input ──────────────────────────────────────────────────────────────────────

def get_input():
    try:
        import keyboard
        if keyboard.is_pressed("shift"):
            print("[Shift] 🎤 Listening...")
            txt, ok = listen()
            if ok and txt:
                print(f"You (speech): {txt}")
                return txt, "speech"
            print("No speech detected. Type instead:")
            return input("You: ").strip(), "text"
    except Exception:
        pass
    return input("You: ").strip(), "text"


# ── Agent task runner ──────────────────────────────────────────────────────────

def run_agent_task(usr: str):
    """Run an autonomous multi-step agent task and display results."""
    print("\n🤖 Starting autonomous agent task...")

    context = get_context(usr)

    def on_step(step_num, tool, msg):
        print(f"   [{step_num}] {msg}")

    result = agent.run(usr, context=context, on_step=on_step)

    print(f"\n{'='*60}")
    print(result.summary())
    print(f"{'='*60}\n")

    if result.final_answer:
        print(f"AURA: {result.final_answer}")
        if app_config.get('voice_enabled', True):
            try:
                interruptible_tts.speak(result.final_answer, app_config)
            except Exception as e:
                logger.error(f"TTS error in agent task: {e}")

    # Save to new memory system
    add_session_turn(usr, result.final_answer or "(agent task completed)", {
        "agent_mode": True
    })
    log_conversation(usr, result.final_answer or "(agent task completed)")


# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    print(f"\n🤖 AURA v3.0 — Advanced AI Assistant — {time.ctime()}")
    print("=" * 60)
    print("🛠️  Systems: Web Search · Vision · Deep Thinking · Calculator")
    print("           Image Gen · Code Gen · System Control · Agent Mode")
    print("           Security Agent · OSINT · VM Coding IDE")
    print("=" * 60)

    # Clear session so old conversations never bleed through
    clear_session()

    # Delete any leftover WAV files from previous crashed runs
    cleanup_stale_wavs()

    # Run startup checks (non-fatal — warn but continue)
    _startup_checks()

    agent_mode = False

    print("\nAURA: Ready.")

    print("\n📝 Commands:")
    print("   • Type or hold Shift to speak")
    print("   • Press Escape to stop speech")
    print("   • 'exit' / 'quit' to quit")
    print("   • 'stats'         — performance metrics")
    print("   • 'memory stats'  — knowledge store info")
    print("   • 'config'        — current settings")
    print("   • 'files'         — list generated code files")
    print("   • 'agent mode on/off'  — toggle autonomous mode")
    print("   • 'agent: <task>'      — run one agent task now")
    print("   • 'agent outputs'      — list agent output files\n")

    # Hotkeys
    try:
        import keyboard
        keyboard.add_hotkey('escape', interruptible_tts.interrupt)
    except Exception as e:
        logger.warning(f"Could not register hotkeys: {e}")

    interaction_count = 0

    while True:
        try:
            prompt_str = "You [AGENT MODE]: " if agent_mode else None
            if prompt_str:
                usr    = input(prompt_str).strip()
                method = "text"
            else:
                usr, method = get_input()

            if not usr:
                continue

            usr_lower = usr.lower().strip()

            # ── Vision controls ───────────────────────────────────────────
            if usr_lower in ("activate vision", "vision mode", "live vision on"):
                vision_system.start()
                continue
            if usr_lower in ("vision off", "stop vision", "disable vision"):
                vision_system.stop()
                continue

            # ── Exit ──────────────────────────────────────────────────────
            if usr_lower in ('exit', 'quit', 'bye', 'goodbye'):
                print("\n👋 Goodbye! Shutting down...")
                break

            # ── Hacker / Security mode ────────────────────────────────────
            if should_launch_hacker(usr):
                interaction_count += 1
                msg = "Launching security terminal..."
                print(f"\n  {msg}")
                if app_config.get('voice_enabled', True):
                    interruptible_tts.speak(msg, app_config)
                result = launch_hacker_mode(usr, blocking=True)
                print(f"\nAURA: {result}")
                add_session_turn(usr, result)
                log_conversation(usr, result)
                continue

            # ── VM / Coding IDE mode ──────────────────────────────────────
            if should_launch_vm(usr):
                interaction_count += 1
                msg = "Launching VM coding IDE..."
                print(f"\n  {msg}")
                if app_config.get('voice_enabled', True):
                    interruptible_tts.speak(msg, app_config)
                result = launch_vm_mode(blocking=False)
                print(f"\nAURA: {result}")
                add_session_turn(usr, result)
                log_conversation(usr, result)
                continue

            # ── OSINT ─────────────────────────────────────────────────────
            if should_launch_osint(usr):
                interaction_count += 1
                print("\n  Launching OSINT engine...")
                interruptible_tts.speak("Opening OSINT scanner.", app_config)
                try:
                    from tools.web_search import web_search as _ws
                    result = run_osint_gui(usr, web_search_fn=_ws)
                except Exception:
                    result = run_osint_gui(usr, web_search_fn=None)
                print(f"\nAURA: {result}")
                interruptible_tts.speak(result, app_config)
                add_session_turn(usr, result)
                log_conversation(usr, result)
                continue

            # ── Agent mode toggle ─────────────────────────────────────────
            if usr_lower == 'agent mode on':
                agent_mode = True
                msg = "🤖 Agent mode ON — every message runs as a full autonomous task."
                print(f"\n{msg}")
                interruptible_tts.speak(msg, app_config)
                continue

            if usr_lower == 'agent mode off':
                agent_mode = False
                msg = "💬 Agent mode OFF — back to normal conversation."
                print(f"\n{msg}")
                interruptible_tts.speak(msg, app_config)
                continue

            # ── Agent outputs listing ─────────────────────────────────────
            if usr_lower == 'agent outputs':
                out_dir = agent.output_dir
                if os.path.exists(out_dir):
                    files = os.listdir(out_dir)
                    if files:
                        print(f"\n📁 Agent outputs ({out_dir}):")
                        for i, f in enumerate(sorted(files), 1):
                            print(f"   {i}. {f}")
                    else:
                        print("\n📁 No agent output files yet.")
                continue

            # ── Single agent task via prefix ──────────────────────────────
            if usr_lower.startswith('agent:'):
                task = usr[6:].strip()
                if task:
                    interaction_count += 1
                    run_agent_task(task)
                else:
                    print("Usage: agent: <describe your task>")
                continue

            # ── Persistent agent mode ─────────────────────────────────────
            if agent_mode:
                interaction_count += 1
                run_agent_task(usr)
                continue

            # ── Built-in utility commands ─────────────────────────────────
            if usr_lower == 'stats':
                stats = perf_mon.stats()
                ai    = llm_stats()
                print("\n📊 Performance Statistics:")
                print("=" * 50)
                for k, v in stats.items():
                    if isinstance(v, dict):
                        print(f"  {k}:  avg={v['avg']:.2f}s  max={v['max']:.2f}s  n={v['count']}")
                    else:
                        print(f"  {k}: {v:.2f}s")
                print(f"\n  LLM calls:      {ai['total_calls']}")
                print(f"  Success rate:   {ai['success_rate']}%")
                print(f"  Avg resp time:  {ai['avg_response_time_s']}s")
                print(f"  Tokens/sec:     {ai['tokens_per_sec']}")
                print("=" * 50)
                continue

            if usr_lower == 'memory stats':
                ms = memory_stats()
                print("\n🧠 Memory Statistics:")
                print("=" * 50)
                print(f"  Knowledge facts:   {ms['knowledge_facts']}")
                print(f"  Facts by category: {ms['facts_by_category']}")
                print(f"  Session turns:     {ms['session_turns']}")
                print(f"  Log entries:       {ms['log_entries']}")
                print(f"  Embeddings loaded: {ms['has_embeddings']}")
                if ms.get('top_accessed'):
                    print("\n  Most accessed facts:")
                    for f in ms['top_accessed']:
                        print(f"    [{f.get('access_count',0)}x] {f['text'][:60]}")
                print("=" * 50)
                continue

            if usr_lower == 'config':
                print("\n⚙️  Current Configuration:")
                print("=" * 50)
                for k, v in app_config.items():
                    print(f"  {k}: {v}")
                print("=" * 50)
                continue

            if usr_lower == 'files':
                files = coding_system.list_created_files()
                if files:
                    print(f"\n📁 Generated Code Files ({len(files)}):")
                    print("=" * 50)
                    for i, f in enumerate(files, 1):
                        print(f"  {i}. {f}")
                    print("=" * 50)
                else:
                    print("\n📁 No code files generated yet.")
                continue

            # ── Normal conversation ───────────────────────────────────────
            interaction_count += 1
            print(f"\n🤔 Processing... [{get_time_str()}]")

            resp, meta = get_response(
                usr,
                None,   # hist no longer needed — memory handled internally
                service_mgr=service_mgr,
                rate_limiter=rate_limiter,
                decision_system=decision_system,
                app_config=app_config,
                vision_system=vision_system
            )

            # ── Music recognition result ──────────────────────────────────
            if meta.get('music_used') and meta.get('music_result'):
                music = meta['music_result']
                if isinstance(music, dict):
                    print(f"🎵 Identified: {music.get('title','?')} by {music.get('artist','?')}")
                    if app_config.get('voice_enabled', True):
                        interruptible_tts.speak(music.get('title', ''), app_config)
                    try:
                        SpotifyPlaylistSelector(music).show()
                    except Exception as e:
                        logger.error(f"Spotify GUI error: {e}")
                    add_session_turn(usr, str(music))
                    log_conversation(usr, str(music))
                    continue

            # ── System control (only for relevant input) ──────────────────
            if _looks_like_system_command(usr):
                try:
                    action_json = decide_system_action(usr)
                    sys_result  = execute_system_action(action_json)
                    if sys_result:
                        print(f"\n[SYSTEM] {sys_result}")
                except Exception as e:
                    logger.error(f"System control error: {e}")

            # ── Print response ────────────────────────────────────────────
            print(f"\nAURA: {resp}")

            # Code result details
            if meta.get('code_result') and meta['code_result'].get('success'):
                cr = meta['code_result']
                print(f"\n{'='*60}")
                print(f"💾 Saved:    {cr['filepath']}")
                print(f"🔤 Language: {cr['language'].upper()}")
                print(f"📊 Lines:    {cr['total_lines']}")
                print(f"{'='*60}")
            elif meta.get('code_result') and not meta['code_result'].get('success'):
                print(f"\n❌ {meta['code_result'].get('error', 'Code generation failed')}")

            # Tools used
            if meta.get('tools_used'):
                icons = {
                    'thinking_used':   '🧠 Thinking',
                    'web_used':        '🌐 Web Search',
                    'research_used':   '📚 Research',
                    'vision_used':     '👁️ Vision',
                    'image_generated': '🎨 Image Gen',
                    'code_generated':  '💻 Code Gen',
                }
                used = [icons.get(t, f'🔧 {t}') for t in meta['tools_used']]
                print(f"\n[Tools: {', '.join(used)}]")

            if meta.get('response_time'):
                print(f"[{meta['response_time']:.2f}s]")

            # TTS
            if app_config.get('voice_enabled', True):
                try:
                    interruptible_tts.speak(resp, app_config)
                except Exception as e:
                    logger.error(f"TTS error: {e}")

            # Save to memory
            add_session_turn(usr, resp, meta)
            log_conversation(usr, resp, meta)

            perf_mon.log('response_times', meta.get('response_time', 0))

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted — type 'exit' to quit or press Enter to continue")
        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)
            print(f"\n⚠️  Something went wrong: {e}")
            print("Type anything to continue or 'exit' to quit.")

    # ── Shutdown ───────────────────────────────────────────────────────────────
    print(f"\n📊 Session Summary:")
    print(f"   Interactions:  {interaction_count}")
    print(f"   Code files:    {len(coding_system.list_created_files())}")
    print(f"   Uptime:        {perf_mon.stats()['uptime']:.0f}s")
    print("\n🔄 Shutting down...")

    try:
        import keyboard
        keyboard.remove_hotkey('escape')
    except Exception:
        pass

    vision_system.stop()

    try:
        import pygame
        if hasattr(pygame, 'mixer') and pygame.mixer.get_init():
            pygame.mixer.quit()
    except Exception:
        pass

    print("✅ Goodbye!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal startup error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        print("Check aura.log for details.")
        sys.exit(1)