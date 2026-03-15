# ============================================
# FILE: self_improvement.py
# Fixed: syntax validation before overwrite, confirmation prompt, scoped file list
# ============================================

import os
import ast
import shutil
import requests
import json
import logging
import re
from config import OLLAMA_API_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.getcwd()
BACKUP_DIR = os.path.join(PROJECT_ROOT, "self_improve_backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

# Files that should never be auto-improved (high risk)
_SKIP_FILES = {"self_improvement.py"}


def list_python_files():
    files = []
    for root, dirs, filenames in os.walk(PROJECT_ROOT):
        # Skip backup directory and hidden folders
        dirs[:] = [d for d in dirs if d != "self_improve_backups" and not d.startswith('.')]
        for f in filenames:
            if f.endswith(".py") and f not in _SKIP_FILES:
                files.append(os.path.join(root, f))
    return files


def backup_file(filepath: str) -> str:
    filename = os.path.basename(filepath)
    backup_path = os.path.join(BACKUP_DIR, filename)
    shutil.copy(filepath, backup_path)
    return backup_path


def _validate_python_syntax(code: str) -> tuple[bool, str]:
    """Return (is_valid, error_message). Empty error means valid."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"


def _extract_code(raw: str) -> str:
    """Strip markdown code fences if the model wraps output in them."""
    match = re.search(r"```(?:python)?\n(.*?)\n```", raw, re.DOTALL)
    return match.group(1).strip() if match else raw.strip()


def improve_file(filepath: str, confirm: bool = True) -> dict:
    """
    Improve a single file.
    - confirm=True  → ask user before overwriting (interactive use)
    - confirm=False → overwrite automatically (batch/test use)
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            original_code = f.read()
    except OSError as e:
        return {"success": False, "file": filepath, "error": str(e)}

    improvement_prompt = f"""You are an AI code optimizer.

Improve the following Python file:
- Increase performance where possible
- Improve readability and naming
- Reduce code duplication
- Improve error handling
- Do NOT remove any existing functionality
- Do NOT add explanations or comments beyond what is already there
- Output ONLY the complete improved Python source code inside a single markdown code block

FILE:
{original_code}
"""

    try:
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": improvement_prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": -1}
            },
            timeout=180
        )
        response.raise_for_status()
        raw = response.json().get("response", "").strip()
    except Exception as e:
        return {"success": False, "file": filepath, "error": f"LLM request failed: {e}"}

    improved_code = _extract_code(raw)

    if len(improved_code) < 50:
        return {"success": False, "file": filepath, "error": "Model returned suspiciously short output; skipping."}

    # ── Syntax validation ──────────────────────────────────────────────────────
    valid, syntax_error = _validate_python_syntax(improved_code)
    if not valid:
        logger.error(f"Syntax error in improved code for {filepath}: {syntax_error}")
        return {
            "success": False,
            "file": filepath,
            "error": f"Generated code has syntax errors ({syntax_error}); original file untouched.",
        }

    # ── Optional confirmation ──────────────────────────────────────────────────
    if confirm:
        print(f"\n--- Proposed improvement for: {os.path.basename(filepath)} ---")
        print(improved_code[:800] + (" ..." if len(improved_code) > 800 else ""))
        answer = input("\nApply this improvement? [y/N]: ").strip().lower()
        if answer != 'y':
            return {"success": False, "file": filepath, "error": "Skipped by user."}

    backup_path = backup_file(filepath)
    logger.info(f"Backed up {filepath} → {backup_path}")

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(improved_code)
    except OSError as e:
        # Restore backup on write failure
        shutil.copy(backup_path, filepath)
        return {"success": False, "file": filepath, "error": f"Write failed, original restored: {e}"}

    return {"success": True, "file": filepath, "backup": backup_path}


def self_improve_project(confirm: bool = True) -> list[dict]:
    """Improve all eligible Python files in the project."""
    results = []
    files = list_python_files()
    logger.info(f"Self-improvement starting on {len(files)} files")

    for filepath in files:
        print(f"\n🔧 Improving: {filepath}")
        result = improve_file(filepath, confirm=confirm)
        results.append(result)

        if result["success"]:
            print(f"  ✅ Improved and saved ({result['backup']})")
        else:
            print(f"  ❌ Skipped: {result['error']}")

    return results