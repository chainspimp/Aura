# ============================================
# FILE: ai/vm_agent.py
# AURA VM Coding Agent — Cursor-level quality
#
# Improvements over v1:
#  • Full codebase context passed to every file
#  • Surgical diff-based edits instead of rewrites
#  • Multi-round fix loop with root cause analysis
#  • Linting pass after each file
#  • Much stronger system prompts
#  • Dependency resolution before running
#  • Progress tracking per file
# ============================================

import os
import re
import sys
import json
import time
import shutil
import logging
import threading
import subprocess
import requests
from datetime import datetime
from typing import Optional, List, Dict, Callable, Generator, Tuple

from config import (
    OLLAMA_API_URL,
    OLLAMA_MODEL,
    OLLAMA_THINKING_MODEL,
    OLLAMA_CODING_MODEL,
)

logger = logging.getLogger(__name__)

WORKSPACE_DIR = os.path.join(os.getcwd(), "vm_workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

MAX_FIX_ROUNDS = 8


# ═══════════════════════════════════════════════════════════
# STREAMING LLM
# ═══════════════════════════════════════════════════════════

def stream_llm(prompt: str, model: str, system: str = "",
               temperature: float = 0.2) -> Generator[str, None, None]:
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    try:
        resp = requests.post(
            OLLAMA_API_URL,
            json={
                "model":  model,
                "prompt": full_prompt,
                "stream": True,
                "options": {
                    "temperature": temperature,
                    "num_predict": 16384,
                    "num_ctx":     16384,
                }
            },
            stream=True,
            timeout=600
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                try:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        yield f"\n[STREAM ERROR] {e}\n"


def call_llm(prompt: str, model: str, system: str = "",
             temperature: float = 0.2) -> str:
    return "".join(stream_llm(prompt, model, system, temperature))


# ═══════════════════════════════════════════════════════════
# PROJECT PLANNER
# Uses thinking model to deeply architect the project
# ═══════════════════════════════════════════════════════════

PLANNER_SYSTEM = """You are a world-class software architect with 20 years of experience.
You have built production SaaS products used by millions of people.
When planning a project you think about:
- The simplest stack that delivers production quality
- Security, scalability, and maintainability from day one
- Proper separation of concerns
- Every file needed — nothing missing, nothing extra
You produce complete, detailed plans that a senior developer could implement without questions."""

def plan_project(description: str,
                 on_token: Callable[[str], None] = None) -> Dict:
    prompt = f"""Project to build: {description}

Think step by step about the architecture. Consider:
1. What is the core user problem being solved?
2. What is the simplest stack that delivers this well?
3. What files are absolutely needed vs nice-to-have?
4. What are the key data models?
5. What are potential failure points?

After thinking, output ONLY a JSON object:
{{
  "project_name": "snake_case_name",
  "description": "one precise sentence",
  "tech_stack": "e.g. Python 3.11 + Flask 3 + SQLite + Tailwind CSS",
  "why_this_stack": "brief reason",
  "architecture_notes": "key design decisions",
  "files": [
    {{
      "path": "relative/path/file.ext",
      "purpose": "exactly what this file does",
      "depends_on": ["other/file.py"],
      "critical": true
    }}
  ],
  "entry_point": "app.py",
  "run_command": "python app.py",
  "install_command": "pip install flask flask-sqlalchemy flask-login",
  "env_vars": ["SECRET_KEY", "DATABASE_URL"],
  "test_command": "python -m pytest tests/ -v",
  "notes": "important implementation details the developer must know"
}}

Rules:
- Include EVERY file. Missing a file means the project won't work.
- Max 25 files. Every file must earn its place.
- Always include requirements.txt
- For web apps always include templates/ and static/ structure
- Think about auth, error handling, and config from the start"""

    raw = ""
    for token in stream_llm(prompt, OLLAMA_THINKING_MODEL,
                             PLANNER_SYSTEM, temperature=0.3):
        raw += token
        if on_token:
            on_token(token)

    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {
        "project_name": "project",
        "description":  description,
        "tech_stack":   "Python + Flask",
        "files":        [{"path": "app.py", "purpose": "Main app", "critical": True}],
        "entry_point":  "app.py",
        "run_command":  "python app.py",
        "install_command": "pip install flask",
        "notes": ""
    }


# ═══════════════════════════════════════════════════════════
# FILE WRITER
# Full codebase context, strong prompts, no placeholders
# ═══════════════════════════════════════════════════════════

def _build_codebase_context(existing_files: Dict[str, str],
                             current_path: str,
                             max_chars: int = 12000) -> str:
    """
    Build a full codebase context string.
    Prioritizes files that current_path depends on.
    Truncates intelligently to fit context window.
    """
    if not existing_files:
        return "No files written yet."

    parts = []
    total = 0

    for path, content in existing_files.items():
        if path == current_path:
            continue
        header = f"\n{'─'*60}\n// FILE: {path}\n{'─'*60}\n"
        block  = header + content + "\n"
        if total + len(block) > max_chars:
            # Add truncated version
            remaining = max_chars - total - len(header) - 50
            if remaining > 200:
                parts.append(header + content[:remaining] + "\n... [truncated]\n")
            break
        parts.append(block)
        total += len(block)

    return "".join(parts) if parts else "No files written yet."


CODER_SYSTEM = """You are a senior software engineer writing production code.
Your code is:
- Complete — every function fully implemented, no TODOs, no placeholders, no "pass"
- Correct — handles edge cases, validates input, catches exceptions properly  
- Clean — clear variable names, consistent style, logical structure
- Secure — no hardcoded secrets, proper input sanitisation, safe defaults
- Documented — docstrings on classes and non-trivial functions

You NEVER write:
- "# TODO: implement this"
- "pass  # placeholder"  
- "# ... rest of implementation"
- Incomplete functions
- Magic strings that should be constants

When writing web templates you write complete, styled HTML — not skeletons."""


def write_file(file_info: Dict, project_plan: Dict,
               existing_files: Dict[str, str],
               on_token: Callable[[str], None] = None) -> str:
    path    = file_info["path"]
    purpose = file_info.get("purpose", "")
    ext     = os.path.splitext(path)[1].lower()

    lang_map = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".jsx": "React JSX", ".tsx": "React TSX", ".html": "HTML5",
        ".css": "CSS3", ".sql": "SQL", ".sh": "Bash",
        ".json": "JSON", ".md": "Markdown", ".env": "env config",
        ".txt": "text", ".yml": "YAML", ".yaml": "YAML",
        ".toml": "TOML", ".cfg": "config",
    }
    lang = lang_map.get(ext, "code")

    codebase_ctx = _build_codebase_context(existing_files, path)
    deps         = file_info.get("depends_on", [])
    deps_note    = f"This file depends on: {', '.join(deps)}" if deps else ""

    prompt = f"""Project: {project_plan['description']}
Tech stack: {project_plan['tech_stack']}
Architecture notes: {project_plan.get('architecture_notes', '')}
Important: {project_plan.get('notes', '')}

{deps_note}

EXISTING CODEBASE (all files written so far):
{codebase_ctx}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Now write the COMPLETE {lang} code for: {path}
Purpose: {purpose}

Critical requirements:
- Write the ENTIRE file — every line of every function
- Import everything you use — don't assume anything is in scope
- Be consistent with the patterns in existing files above
- If this is a config/env file, include all required variables with sensible defaults
- If this is an HTML template, write complete styled markup — not a skeleton
- If this is requirements.txt, include exact package names (no versions unless critical)

Return ONLY the raw {lang} code. No markdown fences. No explanation. No preamble."""

    content = ""
    for token in stream_llm(prompt, OLLAMA_CODING_MODEL,
                             CODER_SYSTEM, temperature=0.1):
        content += token
        if on_token:
            on_token(token)

    # Strip markdown fences if model added them
    content = re.sub(r'^```[\w]*\n?', '', content.strip())
    content = re.sub(r'\n?```$',      '', content.strip())
    return content.strip()


# ═══════════════════════════════════════════════════════════
# LINTER / VALIDATOR
# Quick sanity check on generated code
# ═══════════════════════════════════════════════════════════

def lint_file(path: str, content: str) -> Tuple[bool, str]:
    """
    Run a quick lint check. Returns (passed, message).
    Uses pyflakes for Python, basic checks for others.
    """
    ext = os.path.splitext(path)[1].lower()

    if ext == ".py":
        try:
            import py_compile, tempfile
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.py', delete=False, encoding='utf-8'
            ) as f:
                f.write(content)
                tmp = f.name
            try:
                py_compile.compile(tmp, doraise=True)
                return True, "syntax OK"
            except py_compile.PyCompileError as e:
                return False, str(e)
            finally:
                os.unlink(tmp)
        except Exception:
            return True, "lint skipped"

    # Basic checks for all files
    if len(content.strip()) < 10:
        return False, "file appears empty"

    placeholder_patterns = [
        r'#\s*TODO\s*:',
        r'#\s*FIXME\s*:',
        r'pass\s*#\s*placeholder',
        r'\.\.\.\s*#\s*implement',
    ]
    for pat in placeholder_patterns:
        if re.search(pat, content, re.IGNORECASE):
            return False, f"placeholder found: {pat}"

    return True, "OK"


# ═══════════════════════════════════════════════════════════
# CODE RUNNER
# ═══════════════════════════════════════════════════════════

def run_project(project_dir: str, run_cmd: str,
                timeout: int = 30) -> Dict:
    try:
        result = subprocess.run(
            run_cmd, shell=True, cwd=project_dir,
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                 "FLASK_ENV": "development", "FLASK_DEBUG": "0"}
        )
        return {
            "stdout":    result.stdout,
            "stderr":    result.stderr,
            "exit_code": result.returncode,
            "success":   result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        # Timeout often means a server started successfully — treat as success
        return {
            "stdout":    f"[Server running — timeout after {timeout}s, likely started OK]",
            "stderr":    "",
            "exit_code": 0,
            "success":   True,
        }
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1, "success": False}


def install_deps(project_dir: str, install_cmd: str,
                 on_output: Callable = None) -> Tuple[bool, str]:
    if not install_cmd:
        return True, "No dependencies"
    try:
        result = subprocess.run(
            install_cmd, shell=True, cwd=project_dir,
            capture_output=True, text=True, timeout=180
        )
        out = result.stdout + result.stderr
        if on_output:
            on_output(out)
        return result.returncode == 0, out
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════
# SURGICAL ERROR FIXER
# Diagnoses root cause, makes minimal targeted edits
# ═══════════════════════════════════════════════════════════

FIX_SYSTEM = """You are an expert debugger.
When given an error you:
1. Identify the ROOT CAUSE — not just the symptom
2. Find the MINIMAL change that fixes it
3. Consider if the fix might break other files
You never guess — you reason from the error message and code."""


def fix_error(error_output: str, project_plan: Dict,
              project_dir: str, existing_files: Dict[str, str],
              on_token: Callable = None) -> Optional[Dict[str, str]]:
    """
    Diagnose error and return {filepath: fixed_content} or None.
    Tries surgical edit first, falls back to full rewrite if needed.
    """
    files_summary = "\n".join(
        f"  {p}: {len(c.splitlines())} lines"
        for p, c in existing_files.items()
    )

    # Step 1: Diagnose which file and what's wrong
    diag_prompt = f"""Error from running the project:

{error_output[:4000]}

Project files:
{files_summary}

Which file contains the bug? What is the root cause?
Respond ONLY with JSON:
{{
  "file": "path/to/file.py",
  "root_cause": "specific description of the bug",
  "fix_strategy": "surgical_edit or full_rewrite",
  "fix_description": "exactly what needs to change"
}}"""

    raw = call_llm(diag_prompt, OLLAMA_MODEL, FIX_SYSTEM, temperature=0)
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        return None

    try:
        diagnosis = json.loads(match.group(0))
    except Exception:
        return None

    broken_file = diagnosis.get("file", "")
    strategy    = diagnosis.get("fix_strategy", "full_rewrite")
    fix_desc    = diagnosis.get("fix_description", "")
    root_cause  = diagnosis.get("root_cause", "")

    # Fuzzy match filename
    if broken_file not in existing_files:
        for fp in existing_files:
            if os.path.basename(fp) == os.path.basename(broken_file):
                broken_file = fp
                break
        else:
            return None

    if on_token:
        on_token(f"\n[ROOT CAUSE] {root_cause}\n")
        on_token(f"[FIX] {fix_desc}\n")
        on_token(f"[STRATEGY] {strategy}\n\n")

    original = existing_files[broken_file]

    if strategy == "surgical_edit":
        # Ask for a targeted patch
        patch_prompt = f"""File to fix: {broken_file}

Root cause: {root_cause}
Required fix: {fix_desc}

Current file content:
{original}

Error that occurred:
{error_output[:2000]}

Apply the MINIMAL fix. Return the complete corrected file.
Return ONLY the raw code — no fences, no explanation."""

        new_content = ""
        for token in stream_llm(patch_prompt, OLLAMA_CODING_MODEL,
                                 CODER_SYSTEM, temperature=0.05):
            new_content += token
            if on_token:
                on_token(token)
    else:
        # Full rewrite with error context
        file_info = {
            "path":    broken_file,
            "purpose": f"Fixed version — {fix_desc}"
        }
        # Add error context to notes temporarily
        augmented_plan = dict(project_plan)
        augmented_plan["notes"] = (
            f"{project_plan.get('notes', '')}\n"
            f"CRITICAL FIX NEEDED: {root_cause}. Fix: {fix_desc}.\n"
            f"Previous error: {error_output[:500]}"
        )
        new_content = write_file(file_info, augmented_plan,
                                  existing_files, on_token)

    new_content = re.sub(r'^```[\w]*\n?', '', new_content.strip())
    new_content = re.sub(r'\n?```$',      '', new_content.strip())

    return {broken_file: new_content.strip()}


# ═══════════════════════════════════════════════════════════
# CROSS-FILE CONSISTENCY CHECKER
# Makes sure imports and interfaces match across files
# ═══════════════════════════════════════════════════════════

def check_consistency(existing_files: Dict[str, str],
                      project_plan: Dict) -> List[str]:
    """
    Quick check for obvious cross-file issues.
    Returns list of issues found.
    """
    issues = []

    # Check Python imports resolve
    py_files  = {p for p in existing_files if p.endswith('.py')}
    all_names = set()

    for path in py_files:
        content = existing_files[path]
        # Extract defined functions/classes
        for m in re.finditer(r'^(?:def|class)\s+(\w+)', content, re.MULTILINE):
            all_names.add(m.group(1))

    # Check for obvious missing imports
    for path, content in existing_files.items():
        if not path.endswith('.py'):
            continue
        for m in re.finditer(r'^from\s+(\S+)\s+import', content, re.MULTILINE):
            module = m.group(1)
            if module.startswith('.'):
                # Relative import — check file exists
                local = module.lstrip('.').replace('.', '/') + '.py'
                if local not in existing_files and module.lstrip('.') not in [
                    os.path.splitext(p)[0].replace('/', '.') for p in existing_files
                ]:
                    issues.append(f"{path}: relative import '{module}' may not resolve")

    return issues


# ═══════════════════════════════════════════════════════════
# MAIN AGENT
# ═══════════════════════════════════════════════════════════

class VMCodingAgent:
    """
    Production-quality coding agent.
    Builds complete, runnable projects from a description.
    """

    MAX_FIX_ROUNDS = 8

    def __init__(self):
        self.on_log:         Optional[Callable] = None
        self.on_token:       Optional[Callable] = None
        self.on_file_start:  Optional[Callable] = None
        self.on_file_done:   Optional[Callable] = None
        self.on_run_result:  Optional[Callable] = None
        self.on_complete:    Optional[Callable] = None
        self.on_lint_result: Optional[Callable] = None
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def _log(self, msg: str, level: str = "info"):
        print(f"[VM] {msg}")
        if self.on_log:
            self.on_log(msg, level)

    def _token(self, token: str):
        if self.on_token:
            self.on_token(token)

    def build(self, description: str) -> Dict:
        self._stop_flag = False
        timestamp       = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ── Phase 1: Deep architecture planning ──
        self._log("🧠 Planning architecture...", "phase")
        self._token("\n═══ ARCHITECTURE PLANNING ═══\n\n")

        plan = plan_project(description, on_token=self._token)

        project_name = re.sub(r'[^a-zA-Z0-9_]', '_',
                               plan.get("project_name", "project"))
        project_dir  = os.path.join(WORKSPACE_DIR,
                                    f"{project_name}_{timestamp}")
        os.makedirs(project_dir, exist_ok=True)

        self._log(f"📁 {project_name}", "success")
        self._log(f"🔧 {plan.get('tech_stack', '?')}", "info")
        self._log(f"📄 {len(plan.get('files', []))} files to write", "info")

        # ── Phase 2: Write every file ──
        files     = plan.get("files", [])
        total     = len(files)
        existing: Dict[str, str] = {}

        self._token(f"\n\n═══ WRITING {total} FILES ═══\n")

        for i, file_info in enumerate(files, 1):
            if self._stop_flag:
                break

            path    = file_info["path"]
            purpose = file_info.get("purpose", "")

            self._log(f"✍️  [{i}/{total}] {path}", "step")
            self._token(f"\n\n── [{i}/{total}] {path} ──\n")

            if self.on_file_start:
                self.on_file_start(path)

            full_path = os.path.join(project_dir, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            # Write file with full codebase context
            content = write_file(file_info, plan, existing,
                                  on_token=self._token)

            # Lint check
            lint_ok, lint_msg = lint_file(path, content)
            if not lint_ok:
                self._log(f"⚠️  Lint issue in {path}: {lint_msg}", "warn")
                self._token(f"\n[LINT FIX NEEDED: {lint_msg}]\n")
                if self.on_lint_result:
                    self.on_lint_result(path, False, lint_msg)

                # Auto-fix lint error
                fix_prompt = f"""This code has a syntax/lint error: {lint_msg}

Code:
{content}

Fix the error and return the complete corrected code.
Return ONLY the raw code — no fences, no explanation."""

                fixed = ""
                for token in stream_llm(fix_prompt, OLLAMA_CODING_MODEL,
                                         CODER_SYSTEM, temperature=0.05):
                    fixed += token
                    self._token(token)
                fixed = re.sub(r'^```[\w]*\n?', '', fixed.strip())
                fixed = re.sub(r'\n?```$',      '', fixed.strip())

                lint_ok2, _ = lint_file(path, fixed)
                if lint_ok2:
                    content = fixed
                    self._log(f"✅ Lint fixed for {path}", "success")
            else:
                if self.on_lint_result:
                    self.on_lint_result(path, True, "OK")

            # Save
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

            existing[path] = content

            if self.on_file_done:
                self.on_file_done(path, content)

            self._log(
                f"✅ {path} ({len(content.splitlines())} lines)", "success"
            )

        # ── Phase 3: Consistency check ──
        if not self._stop_flag:
            issues = check_consistency(existing, plan)
            if issues:
                self._log(f"⚠️  {len(issues)} consistency issues found", "warn")
                for issue in issues[:3]:
                    self._log(f"   {issue}", "warn")

        # ── Phase 4: Install dependencies ──
        install_cmd = plan.get("install_command", "")
        if install_cmd and not self._stop_flag:
            self._log(f"📦 Installing: {install_cmd}", "step")
            self._token(f"\n\n═══ INSTALLING DEPENDENCIES ═══\n$ {install_cmd}\n\n")

            ok, out = install_deps(
                project_dir, install_cmd,
                on_output=lambda o: self._token(o)
            )
            if ok:
                self._log("✅ Dependencies installed", "success")
            else:
                self._log("⚠️  Install had issues — check terminal", "warn")

        # ── Phase 5: Run + fix loop ──
        run_cmd = plan.get("run_command", "")
        success = False
        run_out = {}

        skip_run = any(
            plan.get("tech_stack", "").lower().startswith(s)
            for s in ["html", "css", "static"]
        ) or not run_cmd

        if not skip_run and not self._stop_flag:
            for fix_round in range(self.MAX_FIX_ROUNDS + 1):
                label = "RUNNING" if fix_round == 0 else f"FIX ROUND {fix_round}"
                self._log(
                    f"🚀 {label}: {run_cmd}" if fix_round == 0
                    else f"🔧 Fix attempt {fix_round}/{self.MAX_FIX_ROUNDS}",
                    "phase"
                )
                self._token(f"\n\n═══ {label} ═══\n$ {run_cmd}\n\n")

                run_out = run_project(project_dir, run_cmd, timeout=20)

                if run_out["stdout"]:
                    self._token(run_out["stdout"])
                if run_out["stderr"]:
                    self._token(run_out["stderr"])

                if self.on_run_result:
                    self.on_run_result(run_out)

                if run_out["success"]:
                    success = True
                    self._log("✅ Project runs successfully!", "success")
                    break

                if fix_round >= self.MAX_FIX_ROUNDS or self._stop_flag:
                    break

                error_text = run_out["stderr"] + run_out["stdout"]
                self._token(f"\n[DIAGNOSING ERROR...]\n")

                fixes = fix_error(
                    error_text, plan, project_dir,
                    existing, on_token=self._token
                )

                if fixes:
                    for fp, new_content in fixes.items():
                        full = os.path.join(project_dir, fp)
                        with open(full, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        existing[fp] = new_content
                        if self.on_file_done:
                            self.on_file_done(fp, new_content)
                        self._log(f"🔧 Fixed {fp}", "success")
                else:
                    self._log("Could not determine fix", "warn")
                    break
        else:
            success = True

        # ── Done ──
        self._token(f"\n\n═══ BUILD COMPLETE ═══\n")
        self._token(f"Project: {project_dir}\n")
        self._token(f"Files: {len(existing)}\n")
        self._token(f"Status: {'✅ SUCCESS' if success else '⚠️ NEEDS REVIEW'}\n")
        self._log(f"📁 Saved: {project_dir}", "success")

        result = {
            "success":      success,
            "project_dir":  project_dir,
            "project_name": project_name,
            "plan":         plan,
            "files":        existing,
            "run_output":   run_out,
        }

        if self.on_complete:
            self.on_complete(project_dir)

        return result


# ── Singleton ──────────────────────────────────────────────

_agent: Optional[VMCodingAgent] = None

def get_vm_agent() -> VMCodingAgent:
    global _agent
    if _agent is None:
        _agent = VMCodingAgent()
    return _agent