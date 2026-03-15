"""
Tool implementations for AURA
"""

from tools.executor import ToolExecutor
from tools.web_search import web_search, deep_research
from tools.calculator import calculate
from tools.image_gen import generate_image_local, display_image
from tools.system_control import SystemController, decide_system_action, execute_system_action

__all__ = [
    'ToolExecutor',
    'web_search',
    'deep_research',
    'calculate',
    'generate_image_local',
    'display_image',
    'SystemController',
    'decide_system_action',
    'execute_system_action'
]