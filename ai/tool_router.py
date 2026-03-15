import requests
import json
from config import OLLAMA_API_URL, OLLAMA_MODEL

AVAILABLE_TOOLS = [
    "thinking",
    "web_search",
    "deep_research",
    "image_generation",
    "code_generation",
    "face_recognition",
    "vision"
]

def route_tools(user_prompt: str, context: str = ""):
    routing_prompt = f"""
You are an AI tool router.

Your job is to decide which tools should be used to answer the user's request.

Available tools:
{", ".join(AVAILABLE_TOOLS)}

Respond ONLY in valid JSON like this:

{{
  "tools": [
    {{"name": "tool_name", "reason": "why it is needed"}}
  ]
}}

If no tools are required, return:
{{ "tools": [] }}

User request:
{user_prompt}

Context:
{context}
"""

    response = requests.post(
        OLLAMA_API_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": routing_prompt,
            "stream": False,
            "options": {"temperature": 0.1}
        },
        timeout=60
    )

    response.raise_for_status()
    raw = response.json().get("response", "").strip()

    try:
        return json.loads(raw)
    except:
        return {"tools": []}
