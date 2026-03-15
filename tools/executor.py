import time
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class ToolExecutor:
    """Executes tools that the AI decides to use"""
    def __init__(self):
        self.execution_history = []
        self.image_count = 0
    
    def execute_tool(self, tool_name: str, **kwargs) -> str:
        """Execute a tool by name"""
        start = time.time()
        try:
            if tool_name == "web_search":
                from tools.web_search import web_search
                result = web_search(kwargs.get('query', ''))
            elif tool_name == "deep_research":
                from tools.web_search import deep_research
                result = deep_research(kwargs.get('topic', ''), kwargs.get('num_queries', 3))
            elif tool_name == "calculate":
                from tools.calculator import calculate
                result = calculate(kwargs.get('expression', ''))
            elif tool_name == "vision":
                from ai.vision import get_visual_context
                result = get_visual_context(force=True)
            elif tool_name == "image_generation":
                result, image_path = self.generate_image_local(kwargs.get('prompt', ''))
                return result
            elif tool_name == "memory_search":
                result = "Memory search handled separately"
            else:
                result = f"Unknown tool: {tool_name}"
            
            self.execution_history.append({
                "tool": tool_name,
                "kwargs": kwargs,
                "result": result[:200],
                "time": time.time()
            })
            return result
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return f"Tool error: {str(e)}"
    
    def generate_image_local(self, prompt: str) -> Tuple[str, Optional[str]]:
        """Generate images locally using SDXL-Turbo"""
        from tools.image_gen import generate_image_local, display_image
        self.image_count += 1
        result, image_path = generate_image_local(prompt, self.image_count)
        if image_path:
            display_image(image_path, prompt)
        return result, image_path
    
    def web_search(self, query: str) -> str:
        """Search DuckDuckGo for information"""
        from tools.web_search import web_search
        return web_search(query)
    
    def deep_research(self, topic: str, num_queries: int = 3) -> str:
        """Perform multi-step research"""
        from tools.web_search import deep_research
        return deep_research(topic, num_queries)
    
    def calculate(self, expression: str) -> str:
        """Safely evaluate math expressions"""
        from tools.calculator import calculate
        return calculate(expression)
