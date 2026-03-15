# ============================================
# FILE: ai/hacker_runner.py
# Detects when the user wants hacker mode
# and launches the terminal GUI
# ============================================

import re

# Phrases that mean "open hacker mode"
HACKER_TRIGGERS = [
    r'\bhack(er)? mode\b',
    r'\bpentest\b',
    r'\bpenetration test\b',
    r'\bsecurity (scan|test|audit|check)\b',
    r'\bport scan\b',
    r'\bnmap\b',
    r'\bvuln(erability)? scan\b',
    r'\brecon(naissance)?\b',
    r'\bopen.*terminal.*hack\b',
    r'\bhacking (mode|terminal|tools)\b',
    r'\bspin up.*(kali|hack|security|terminal)\b',
    r'\blaunch.*(security|hack|pentest)\b',
    r'\bctf\b',
    r'\bcapture the flag\b',
    r'\bbug bounty\b',
    r'\b(test|scan|audit|check) (my|this|the) (server|network|site|host|box|machine|ip)\b',
    r'\bfind (open ports|vulnerabilities|vulns|services)\b',
    r'\bsecurity agent\b',
    r'\bsec mode\b',
]

# Phrases that look similar but aren't hacker mode
HACKER_EXCLUDE = [
    r'\bhow (do|does|to)\b',
    r'\bwhat is\b',
    r'\bexplain\b',
    r'\bdefine\b',
]


def should_launch_hacker(text: str) -> bool:
    low = text.lower().strip()
    for pat in HACKER_EXCLUDE:
        if re.search(pat, low):
            return False
    for pat in HACKER_TRIGGERS:
        if re.search(pat, low):
            return True
    return False


def extract_task(text: str) -> str:
    """
    If the user said something like 'pentest 192.168.1.1'
    pull that out as the initial task so the GUI pre-fills it.
    """
    low = text.lower().strip()
    # Strip trigger words to get the actual task
    clean = re.sub(
        r'\b(hack(er)?( mode)?|pentest|security (scan|test|audit)|'
        r'port scan|vuln(erability)? scan|recon|hacking (mode|tools|terminal)|'
        r'launch|spin up|open|activate|sec mode|security agent)\b',
        '', text, flags=re.IGNORECASE
    ).strip(' :-')
    return clean if len(clean) > 3 else ""


def _probe_environment() -> str:
    """
    Returns a short string describing the shell that will be used.
    Mirrors the priority in _find_shell() so the GUI can show it.
    """
    import sys, subprocess
    if sys.platform != "win32":
        return "bash (Linux/macOS)"
    # WSL
    try:
        r = subprocess.run(["wsl", "echo", "ok"], capture_output=True, text=True, timeout=5)
        if "ok" in r.stdout:
            distro = subprocess.run(
                ["wsl", "bash", "-c", "cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'"],
                capture_output=True, text=True, timeout=5
            ).stdout.strip() or "WSL Linux"
            return f"WSL — {distro}"
    except Exception:
        pass
    # Git Bash
    import os
    for p in [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Git\bin\bash.exe"),
    ]:
        if os.path.exists(p):
            return "Git Bash"
    # PowerShell
    try:
        r = subprocess.run(["pwsh", "-Version"], capture_output=True, timeout=3)
        if r.returncode == 0:
            return "PowerShell Core (pwsh)"
    except Exception:
        pass
    try:
        r = subprocess.run(["powershell", "-Command", "echo ok"], capture_output=True, text=True, timeout=3)
        if "ok" in r.stdout:
            return "Windows PowerShell"
    except Exception:
        pass
    return "Windows CMD (Python emulator fallback)"


def launch_hacker_mode(text: str = "", blocking: bool = True):
    """Called from main.py when hacker intent detected."""
    task    = extract_task(text)
    env_str = _probe_environment()

    print("\n" + "=" * 55)
    print("  AURA SECURITY AGENT — INITIALISING")
    print(f"  Shell environment: {env_str}")
    if task:
        print(f"  Task detected: {task}")
    print("=" * 55 + "\n")

    try:
        from ui.hacker_gui import HackerTerminalGUI
        from ai.hacker_agent import get_hacker_agent

        agent = get_hacker_agent()

        gui = HackerTerminalGUI(agent=agent, env_label=env_str)

        # Wire GUI permission dialog to agent BEFORE session starts
        agent.set_permission_callback(gui.ask_tool_permission)

        # Pre-fill task if we extracted one
        if task:
            gui.task_entry.delete("1.0", "end")
            gui.task_entry.config(fg="#e0ffe0")
            gui.task_entry.insert("1.0", task)

        if blocking:
            gui.show()
        else:
            gui.show_nonblocking()

        return "Security terminal closed."

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Hacker GUI error: {e}", exc_info=True)
        return f"Could not open security terminal: {e}"