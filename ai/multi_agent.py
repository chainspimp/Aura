# =============================================================================
# FILE: ai/multi_agent.py
# AURA Multi-Agent Collaboration System
#
# Extends ai/agent.py to support:
#   - A Coordinator that decomposes big goals into parallel sub-tasks
#   - N Worker agents running concurrently in threads
#   - A shared result bus so workers can read each other's outputs
#   - A Synthesiser that merges all results into a final coherent answer
#
# Usage:
#   coordinator = AgentCoordinator(tool_executor, thinking_system, coding_system)
#   result = coordinator.run("research our top 3 competitors and write a report")
#   print(result.final_answer)
# =============================================================================

import os
import re
import json
import time
import logging
import threading
import requests
from datetime import datetime
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

from config import OLLAMA_API_URL, OLLAMA_MODEL, OLLAMA_THINKING_MODEL
from ai.agent import AutonomousAgent, AgentResult

logger = logging.getLogger(__name__)

MAX_PARALLEL_AGENTS = 4   # cap — more than this hammers Ollama
MAX_PLAN_STEPS      = 6   # per sub-agent


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SubTask:
    """A discrete unit of work assigned to one worker agent."""
    id:          str
    name:        str           # short label, e.g. "Research competitor A"
    goal:        str           # full instruction for this agent
    agent_type:  str = "general"   # general | researcher | coder | writer
    depends_on:  List[str] = field(default_factory=list)  # IDs of tasks whose output is needed


@dataclass
class SubTaskResult:
    task_id:   str
    name:      str
    success:   bool
    output:    str
    duration:  float
    steps_run: int


@dataclass
class MultiAgentResult:
    sub_results:   List[SubTaskResult] = field(default_factory=list)
    final_answer:  str = ""
    saved_files:   List[str] = field(default_factory=list)
    success:       bool = False
    total_time:    float = 0.0
    agents_used:   int = 0

    def summary(self) -> str:
        lines = [
            f"🤖 Multi-agent run: {self.agents_used} agents, "
            f"{self.total_time:.1f}s total\n"
        ]
        for r in self.sub_results:
            icon = "✅" if r.success else "❌"
            lines.append(
                f"  {icon} [{r.name}] — {r.steps_run} steps, {r.duration:.1f}s"
            )
        if self.saved_files:
            lines.append("\n📁 Files saved:")
            for f in self.saved_files:
                lines.append(f"   • {f}")
        return "\n".join(lines)


# =============================================================================
# SHARED RESULT BUS
# Thread-safe store agents use to publish and read each other's outputs
# =============================================================================

class ResultBus:
    """Thread-safe key-value store for inter-agent communication."""

    def __init__(self):
        self._data: Dict[str, str] = {}
        self._lock = threading.Lock()

    def publish(self, task_id: str, output: str):
        with self._lock:
            self._data[task_id] = output

    def get(self, task_id: str) -> Optional[str]:
        with self._lock:
            return self._data.get(task_id)

    def wait_for(self, task_id: str, timeout: float = 120.0) -> Optional[str]:
        """Block until a result is available or timeout expires."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.get(task_id)
            if result is not None:
                return result
            time.sleep(0.5)
        return None

    def all_results(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._data)


# =============================================================================
# WORKER AGENT
# Wraps AutonomousAgent for threaded execution with bus integration
# =============================================================================

class WorkerAgent:
    """
    Runs a SubTask in its own thread.
    Reads dependency outputs from the bus before starting,
    publishes its own output when done.
    """

    def __init__(
        self,
        task:          SubTask,
        bus:           ResultBus,
        tool_executor,
        thinking_system=None,
        coding_system=None,
        on_update:     Optional[Callable] = None,
    ):
        self.task     = task
        self.bus      = bus
        self.on_update = on_update
        self._agent   = AutonomousAgent(tool_executor, thinking_system, coding_system)
        self._result: Optional[SubTaskResult] = None
        self._thread  = threading.Thread(
            target=self._run,
            name=f"Worker-{task.id}",
            daemon=True
        )

    def start(self):
        self._thread.start()

    def join(self, timeout: float = 300.0):
        self._thread.join(timeout=timeout)

    @property
    def result(self) -> Optional[SubTaskResult]:
        return self._result

    def _run(self):
        start = time.time()
        self._notify(f"🚀 Starting: {self.task.name}")

        # ── Wait for dependencies ─────────────────────────────────────────
        dep_context = ""
        for dep_id in self.task.depends_on:
            self._notify(f"⏳ Waiting for dependency: {dep_id}")
            dep_output = self.bus.wait_for(dep_id, timeout=180.0)
            if dep_output:
                dep_context += f"\n\n[Output from {dep_id}]\n{dep_output}"
            else:
                self._notify(f"⚠️ Dependency timed out: {dep_id}")

        goal_with_deps = self.task.goal
        if dep_context:
            goal_with_deps = (
                f"{self.task.goal}\n\n"
                f"Use this context from parallel agents:{dep_context}"
            )

        # ── Run the agent ─────────────────────────────────────────────────
        try:
            agent_result: AgentResult = self._agent.run(
                goal_with_deps,
                context=dep_context,
                on_step=lambda i, tool, msg: self._notify(f"  [{i}] {msg}")
            )
            output   = agent_result.final_answer or _flatten_steps(agent_result)
            success  = agent_result.success
            steps    = len(agent_result.steps)
        except Exception as e:
            logger.error(f"Worker {self.task.id} crashed: {e}", exc_info=True)
            output  = f"Agent error: {e}"
            success = False
            steps   = 0

        duration = time.time() - start
        self._result = SubTaskResult(
            task_id=self.task.id,
            name=self.task.name,
            success=success,
            output=output,
            duration=duration,
            steps_run=steps,
        )

        # Publish so other agents and the coordinator can read it
        self.bus.publish(self.task.id, output)
        self._notify(
            f"{'✅' if success else '❌'} Done: {self.task.name} ({duration:.1f}s)"
        )

    def _notify(self, msg: str):
        logger.info(f"[{self.task.name}] {msg}")
        if self.on_update:
            try:
                self.on_update(self.task.id, self.task.name, msg)
            except Exception:
                pass


# =============================================================================
# COORDINATOR
# Decomposes the user goal, spawns workers, synthesises the result
# =============================================================================

class AgentCoordinator:
    """
    Main entry point for multi-agent tasks.

    Usage:
        coordinator = AgentCoordinator(tool_executor, thinking_system, coding_system)
        result = coordinator.run(
            "Research our top 3 competitors and write a comparison report",
            on_update=lambda task_id, name, msg: print(f"[{name}] {msg}")
        )
    """

    def __init__(self, tool_executor, thinking_system=None, coding_system=None):
        self.tool_executor    = tool_executor
        self.thinking_system  = thinking_system
        self.coding_system    = coding_system
        self.output_dir       = "agent_outputs"
        os.makedirs(self.output_dir, exist_ok=True)

    # ── Public ────────────────────────────────────────────────────────────────

    def run(
        self,
        goal:       str,
        context:    str = "",
        on_update:  Optional[Callable] = None,  # (task_id, name, msg)
    ) -> MultiAgentResult:
        """
        Decompose goal → spawn parallel agents → synthesise → return result.
        """
        start_total = time.time()
        result      = MultiAgentResult()

        logger.info(f"🧠 Coordinator: planning multi-agent run for: {goal[:80]}")

        # ── 1. Decompose ──────────────────────────────────────────────────
        tasks = self._decompose(goal, context)
        if not tasks:
            # Fallback: run as single agent
            single = AutonomousAgent(self.tool_executor, self.thinking_system, self.coding_system)
            single_result = single.run(goal, context)
            result.final_answer = single_result.final_answer
            result.saved_files  = single_result.saved_files
            result.success      = single_result.success
            result.total_time   = time.time() - start_total
            result.agents_used  = 1
            return result

        logger.info(f"📋 Decomposed into {len(tasks)} sub-tasks:")
        for t in tasks:
            deps = f" (needs: {', '.join(t.depends_on)})" if t.depends_on else ""
            logger.info(f"   [{t.id}] {t.name}{deps}")

        if on_update:
            on_update("coordinator", "Coordinator",
                      f"📋 Spawning {len(tasks)} agents in parallel")

        # ── 2. Create bus + workers ───────────────────────────────────────
        bus     = ResultBus()
        workers = [
            WorkerAgent(
                task=task,
                bus=bus,
                tool_executor=self.tool_executor,
                thinking_system=self.thinking_system,
                coding_system=self.coding_system,
                on_update=on_update,
            )
            for task in tasks
        ]

        # ── 3. Launch in waves respecting dependencies ────────────────────
        self._launch_in_waves(workers)

        # ── 4. Collect results ────────────────────────────────────────────
        all_outputs: Dict[str, str] = {}
        for w in workers:
            w.join(timeout=300.0)
            if w.result:
                result.sub_results.append(w.result)
                all_outputs[w.task.id] = w.result.output

        # ── 5. Synthesise ─────────────────────────────────────────────────
        if on_update:
            on_update("synthesiser", "Synthesiser", "🔗 Synthesising all agent outputs...")

        result.final_answer = self._synthesise(goal, tasks, all_outputs)
        result.success      = any(r.success for r in result.sub_results)
        result.total_time   = time.time() - start_total
        result.agents_used  = len(workers)

        # ── 6. Optionally save to file ────────────────────────────────────
        if len(result.final_answer) > 200:
            saved = self._save_report(goal, result)
            if saved:
                result.saved_files.append(saved)

        logger.info(result.summary())
        return result

    # ── Decomposition ─────────────────────────────────────────────────────────

    def _decompose(self, goal: str, context: str) -> List[SubTask]:
        """
        Ask the thinking model to break the goal into parallel sub-tasks.
        Returns a list of SubTask objects.
        """
        prompt = f"""You are an AI coordinator. Break this goal into parallel sub-tasks
that specialised agents can work on simultaneously.

Goal: {goal}
Context: {context}

Return ONLY valid JSON, no markdown:
{{
  "tasks": [
    {{
      "id": "task_1",
      "name": "short label (5 words max)",
      "goal": "detailed instruction for this agent",
      "agent_type": "researcher|coder|writer|general",
      "depends_on": []
    }}
  ]
}}

Rules:
- Maximum {MAX_PARALLEL_AGENTS} tasks
- Prefer parallel tasks (empty depends_on) — only add dependencies when strictly needed
- If the goal is simple (1-2 steps), return just 1 task
- Always include a final "writer" task that synthesises everything if there are multiple tasks
- task IDs must be unique strings like "task_1", "task_2"
"""
        try:
            resp = requests.post(
                OLLAMA_API_URL,
                json={
                    "model":  OLLAMA_THINKING_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 1200}
                },
                timeout=60
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")

            # Strip <think>...</think> from reasoning models
            raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()

            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                return []

            data  = json.loads(match.group(0))
            tasks = []
            for t in data.get("tasks", []):
                tasks.append(SubTask(
                    id=t.get("id", f"task_{len(tasks)+1}"),
                    name=t.get("name", f"Task {len(tasks)+1}"),
                    goal=t.get("goal", goal),
                    agent_type=t.get("agent_type", "general"),
                    depends_on=t.get("depends_on", []),
                ))
            return tasks[:MAX_PARALLEL_AGENTS]

        except Exception as e:
            logger.error(f"Decomposition failed: {e}")
            return []

    # ── Wave launcher ─────────────────────────────────────────────────────────

    def _launch_in_waves(self, workers: List[WorkerAgent]):
        """
        Launch agents whose dependencies are already satisfied first,
        then poll for completed ones and launch dependent agents.
        """
        launched:  set = set()
        completed: set = set()

        def _ready(worker: WorkerAgent) -> bool:
            return all(d in completed for d in worker.task.depends_on)

        deadline = time.time() + 600  # 10 minute max

        while len(completed) < len(workers) and time.time() < deadline:
            # Launch any ready workers
            for w in workers:
                if w.task.id not in launched and _ready(w):
                    w.start()
                    launched.add(w.task.id)

            # Mark completed workers
            for w in workers:
                if w.task.id in launched and w.task.id not in completed:
                    if not w._thread.is_alive():
                        completed.add(w.task.id)

            if len(completed) < len(workers):
                time.sleep(0.5)

    # ── Synthesiser ───────────────────────────────────────────────────────────

    def _synthesise(
        self,
        original_goal:  str,
        tasks:          List[SubTask],
        outputs:        Dict[str, str],
    ) -> str:
        """Merge all sub-agent outputs into a single coherent final answer."""

        # Build a labelled context block
        context_parts = []
        for task in tasks:
            output = outputs.get(task.id, "(no output)")
            context_parts.append(
                f"=== {task.name.upper()} ===\n{output}"
            )
        combined = "\n\n".join(context_parts)

        prompt = (
            f"You are AURA. Multiple specialised agents just completed work on this goal:\n"
            f'"{original_goal}"\n\n'
            f"Here are all their outputs:\n\n{combined}\n\n"
            "Write a single, complete, well-structured final answer that:\n"
            "1. Directly addresses the original goal\n"
            "2. Integrates the best information from all agents\n"
            "3. Removes duplication\n"
            "4. Reads as one coherent document, not separate sections pasted together\n"
            "Use ## headings where appropriate."
        )

        try:
            resp = requests.post(
                OLLAMA_API_URL,
                json={
                    "model":  OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.5, "num_predict": 2000}
                },
                timeout=180
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return combined  # fallback: concatenate raw outputs

    # ── Report saver ──────────────────────────────────────────────────────────

    def _save_report(self, goal: str, result: MultiAgentResult) -> Optional[str]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = re.sub(r'[^a-zA-Z0-9]', '_', goal[:40])
        path      = os.path.join(self.output_dir, f"multi_agent_{filename}_{timestamp}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"AURA Multi-Agent Report\n")
                f.write(f"Goal: {goal}\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n")
                f.write(f"Agents used: {result.agents_used}\n")
                f.write("=" * 60 + "\n\n")
                f.write(result.final_answer)
                f.write("\n\n" + "=" * 60 + "\n")
                f.write(result.summary())
            logger.info(f"Report saved: {path}")
            return path
        except Exception as e:
            logger.error(f"Report save failed: {e}")
            return None


# =============================================================================
# HELPERS
# =============================================================================

def _flatten_steps(agent_result: AgentResult) -> str:
    """Flatten agent steps into a summary string when final_answer is empty."""
    parts = []
    for step in agent_result.steps:
        if step.output:
            parts.append(f"[{step.tool}]\n{step.output}")
    return "\n\n".join(parts) or "No output produced."


# =============================================================================
# TRIGGER DETECTION
# =============================================================================

MULTI_AGENT_TRIGGERS = [
    "research and",
    "find and write",
    "compare and",
    "investigate and",
    "analyse multiple",
    "for each",
    "all of them",
    "in parallel",
    "simultaneously",
    "at the same time",
]


def should_use_multi_agent(prompt: str) -> bool:
    """
    Heuristic: return True if this prompt would benefit from multiple parallel agents.
    The decision system calls this before routing to single AutonomousAgent.
    """
    low = prompt.lower()
    return any(trigger in low for trigger in MULTI_AGENT_TRIGGERS)
