# ============================================
# FILE: tools/osint_runner.py
# Smart OSINT intent detector + GUI launcher
# ============================================

import re
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Phrases that clearly need OSINT (GUI launches)
OSINT_STRONG = [
    r'\bosint\b',
    r'find (everything|all|info|information|details) (on|about)',
    r'dig (up|into|on)',
    r'look into',
    r'background (check|on)',
    r'research (everything|everything i can|as much as) (on|about)',
    r'what can (you |i )?(find|dig up|discover) (on|about)',
    r'profile (on|of)',
    r'investigate',
    r'track down',
    r'search (for )?everything (on|about)',
    r'gather (info|intelligence|data) (on|about)',
    r'full report (on|about)',
    r'find out (everything|all|as much as possible) (about|on)',
    r'find (info|information|details|everything) about',
]

# Phrases that are just general questions - NO OSINT needed
OSINT_EXCLUDE = [
    r'^who is\b',
    r'^what is\b',
    r'^tell me about\b',
    r'^explain\b',
    r'^describe\b',
    r'wikipedia',
    r'(history|biography|born|death|age|career) of',
]


def should_launch_osint(text: str) -> bool:
    """
    Returns True if the user clearly wants an OSINT deep-dive.
    Returns False for general knowledge questions like 'who is X'.
    """
    low = text.lower().strip()

    # Hard exclude
    for pattern in OSINT_EXCLUDE:
        if re.search(pattern, low):
            return False

    # Hard include
    for pattern in OSINT_STRONG:
        if re.search(pattern, low):
            return True

    return False


def extract_prefill(text: str) -> dict:
    """
    Parse any identifiers mentioned in the user's message
    to pre-fill the GUI fields.
    """
    params = {"name": None, "username": None, "email": None, "location": None}

    # Email
    email_match = re.search(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', text)
    if email_match:
        params["email"] = email_match.group(0)

    # @username
    user_match = re.search(r'@([\w.-]+)', text)
    if user_match:
        params["username"] = user_match.group(1)

    # Location
    loc_match = re.search(
        r'\b(?:from|in)\s+([A-Z][a-zA-Z\s,]{3,30}?)(?:\s*$|,|\s+who|\s+that)', text
    )
    if loc_match:
        params["location"] = loc_match.group(1).strip()

    # Name from common patterns
    name_patterns = [
        r'(?:about|on|for|into|osint[:\s]+)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})(?:\s+from|\s+in|$|,)',
        r'(?:about|on|for|into|osint[:\s]+)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
    ]
    for pat in name_patterns:
        m = re.search(pat, text)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in ('everything', 'anyone', 'someone', 'this', 'that'):
                params["name"] = candidate
                break

    return params


def run_osint_gui(text: str, web_search_fn=None) -> str:
    """
    Launch the OSINT GUI, pre-filled with any info from the user's message.
    """
    prefill = extract_prefill(text)

    target = prefill.get("name") or prefill.get("username") or prefill.get("email")
    if target:
        print(f"\n  Detected target: {target}")
        print(f"  Pre-filling OSINT fields...")
    else:
        print(f"\n  Launching OSINT GUI...")

    try:
        from ui.osint_gui import launch_osint_gui
        launch_osint_gui(prefill=prefill, web_search_fn=web_search_fn, blocking=True)
        return "OSINT scan complete. Check osint_reports/ for the saved report."
    except Exception as e:
        logger.error(f"OSINT GUI failed: {e}", exc_info=True)
        # Fallback to terminal
        return _run_terminal_fallback(prefill, web_search_fn)


def _run_terminal_fallback(prefill: dict, web_search_fn=None) -> str:
    """Fallback terminal OSINT if GUI fails to open."""
    try:
        from tools.osint import OSINTEngine, generate_report
        import re as _re
        from datetime import datetime

        engine  = OSINTEngine(web_search_fn=web_search_fn)
        results = engine.investigate(**{k: v for k, v in prefill.items() if v})

        lines = ["OSINT SCAN COMPLETE", "=" * 40]
        for s in results.get("summary", []):
            lines.append(s)

        subject = (prefill.get("name") or prefill.get("username")
                   or prefill.get("email") or "target")
        safe = _re.sub(r'[^a-zA-Z0-9]', '_', subject)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("osint_reports", exist_ok=True)
        path = os.path.join("osint_reports", f"osint_{safe}_{ts}.docx")

        try:
            saved = generate_report(results, path)
            lines.append(f"\nReport saved: {saved}")
        except Exception as e:
            lines.append(f"\nReport save failed: {e}")

        return "\n".join(lines)
    except Exception as e:
        return f"OSINT failed: {e}"
