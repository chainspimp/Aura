# ============================================
# FILE: ai/vm_runner.py
# ============================================

import re
import sys
import os
import subprocess

VM_TRIGGERS = [
    r'\bvm mode\b',
    r'\bvm\b',
    r'\bcode mode\b',
    r'\bide mode\b',
    r'\bbuild mode\b',
    r'\bopen.*?(ide|editor|coding)\b',
    r'\blaunch.*?(ide|editor|coding)\b',
]

def should_launch_vm(text: str) -> bool:
    low = text.lower().strip()
    for pat in VM_TRIGGERS:
        if re.search(pat, low):
            return True
    return False


def launch_vm_mode(blocking: bool = False) -> str:
    print("\n" + "=" * 55)
    print("  AURA VM MODE — LAUNCHING IDE")
    print("=" * 55 + "\n")

    try:
        base     = os.path.dirname(os.path.abspath(__file__))
        launcher = os.path.normpath(os.path.join(base, "..", "ui", "vm_launch.py"))

        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE

        subprocess.Popen([sys.executable, launcher], **kwargs)
        print("  VM IDE window opening...")
        return "VM IDE opened."
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"VM launch error: {e}", exc_info=True)
        return f"Could not open VM IDE: {e}"