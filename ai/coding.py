# ============================================
# FILE: coding.py
# Fixed: _ai_plan timeout raised to 90s, smarter keyword-based fallback filename/description
# ============================================
import os
import json
import requests
import logging
import re
from typing import Dict
from config import OLLAMA_API_URL, OLLAMA_CODING_MODEL, CODE_OUTPUT_DIR

logger = logging.getLogger(__name__)


class CodingSystem:
    def __init__(self, output_dir=CODE_OUTPUT_DIR):
        self.output_dir = output_dir
        self.created_files = []
        os.makedirs(output_dir, exist_ok=True)

    def generate_and_save(self, prompt: str, context: str = "") -> Dict[str, any]:
        try:
            meta = self._ai_plan(prompt, context)
            language    = meta.get("language", "python")
            filename    = meta.get("filename", "output.py")
            description = meta.get("description", prompt)

            logger.info(f"AI planned: language={language}, filename={filename}")

            coding_prompt = f"""You are an expert {language} developer.
Write a complete, production-quality {language} implementation for the following task:

TASK: {description}

CONTEXT: {context}

Rules:
- Write ALL the code needed. Do not truncate, summarise, or leave placeholders like "# TODO" or "...".
- Use best practices: proper error handling, type hints (if applicable), docstrings, and clear variable names.
- If the task is complex, split it into well-organised functions or classes.
- Include any necessary imports at the top.
- Return ONLY the raw code inside a single markdown code block. No explanations outside the block.

```{language}
<your complete code here>
```"""

            resp = requests.post(
                OLLAMA_API_URL,
                json={
                    "model": OLLAMA_CODING_MODEL,
                    "prompt": coding_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.15,
                        "num_predict": -1,
                    }
                },
                timeout=600
            )
            resp.raise_for_status()
            raw_output = resp.json().get("response", "")

            code_match = re.search(r"```(?:\w+)?\n(.*?)\n```", raw_output, re.DOTALL)
            code = code_match.group(1).strip() if code_match else raw_output.strip()

            filename = self._sanitise_filename(filename, language)
            filepath = os.path.join(self.output_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)

            self.created_files.append(filepath)
            total_lines = len(code.splitlines())
            logger.info(f"Saved {total_lines} lines -> {filepath}")

            return {
                'success': True,
                'filename': filename,
                'filepath': filepath,
                'language': language,
                'total_lines': total_lines,
            }

        except Exception as e:
            logger.error(f"Coding Error: {e}")
            return {'success': False, 'error': str(e)}

    def _ai_plan(self, prompt: str, context: str) -> Dict[str, str]:
        """Ask the LLM to decide the best language and a sensible filename."""
        plan_prompt = f"""You are a senior software architect.
Given the user request below, decide:
1. The best programming language to use (e.g. python, javascript, typescript, bash, go, rust, html, sql).
2. A short, descriptive snake_case filename (with the correct extension, no path).
3. A one-sentence clarified description of exactly what the code should do.

User request: {prompt}
Context: {context}

Respond ONLY with a raw JSON object - no markdown, no explanation:
{{
  "language": "<language>",
  "filename": "<filename.ext>",
  "description": "<one sentence>"
}}"""

        try:
            resp = requests.post(
                OLLAMA_API_URL,
                json={
                    "model": OLLAMA_CODING_MODEL,
                    "prompt": plan_prompt,
                    "stream": False,
                    "options": {"temperature": 0}
                },
                timeout=90  # raised from 30s - local Ollama needs more time
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()

            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            logger.warning(f"AI planning failed, using keyword fallback: {e}")

        # Smart keyword fallback instead of truncated prompt as filename
        return self._keyword_fallback(prompt)

    def _keyword_fallback(self, prompt: str) -> Dict[str, str]:
        """
        Derive a sensible language, filename, and description from keywords
        when the LLM planning call times out.
        """
        low = prompt.lower()

        # Detect language
        if any(w in low for w in ['javascript', 'js', 'node', 'react', 'vue']):
            language = 'javascript'
            ext = '.js'
        elif any(w in low for w in ['html', 'webpage', 'web page', 'website']):
            language = 'html'
            ext = '.html'
        elif any(w in low for w in ['bash', 'shell', 'script']):
            language = 'bash'
            ext = '.sh'
        elif any(w in low for w in ['sql', 'database', 'query']):
            language = 'sql'
            ext = '.sql'
        else:
            language = 'python'
            ext = '.py'

        # Detect meaningful name from common project keywords
        name_map = {
            'snake game': 'snake_game',
            'snake':      'snake_game',
            'calculator': 'calculator',
            'todo':       'todo_app',
            'to-do':      'todo_app',
            'chat':       'chat_app',
            'weather':    'weather_app',
            'scraper':    'web_scraper',
            'sort':       'sorting_algorithms',
            'sorting':    'sorting_algorithms',
            'fibonacci':  'fibonacci',
            'prime':      'prime_numbers',
            'clock':      'clock',
            'timer':      'timer',
            'password':   'password_generator',
            'encrypt':    'encryption_tool',
            'api':        'api_client',
            'gui':        'gui_app',
            'image':      'image_processor',
        }

        filename_base = 'output'
        for keyword, name in name_map.items():
            if keyword in low:
                filename_base = name
                break

        return {
            "language": language,
            "filename": f"{filename_base}{ext}",
            "description": prompt,
        }

    def _sanitise_filename(self, filename: str, language: str) -> str:
        filename = os.path.basename(filename)
        filename = re.sub(r'[^a-zA-Z0-9_\-.]', '_', filename)
        if '.' not in filename:
            ext_map = {
                'python': '.py', 'javascript': '.js', 'typescript': '.ts',
                'html': '.html', 'css': '.css', 'bash': '.sh', 'shell': '.sh',
                'go': '.go', 'rust': '.rs', 'java': '.java', 'sql': '.sql',
                'ruby': '.rb', 'php': '.php', 'c': '.c', 'cpp': '.cpp',
            }
            filename += ext_map.get(language.lower(), '.py')
        return filename

    def list_created_files(self):
        return self.created_files