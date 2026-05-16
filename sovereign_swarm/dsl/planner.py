"""Planner — emits an immutable DAG from a Mission.

The DAG is frozen once built.  Runtime changes require a governance
proposal and a new DAG.
"""

import json, time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from .mission import Mission
from .result import Result


@dataclass(frozen=True)
class Step:
    id: str
    tool: str
    params: dict
    timeout: int = 30
    retries: int = 0
    deps: tuple[str, ...] = ()
    description: str = ""

    def depends_on(self, step_id: str) -> bool:
        return step_id in self.deps

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tool": self.tool,
            "params": self.params,
            "timeout": self.timeout,
            "retries": self.retries,
            "deps": list(self.deps),
            "description": self.description,
        }


@dataclass(frozen=True)
class PlanDAG:
    mission_id: str
    steps: tuple[Step, ...]
    state: str = "ready"          # ready | running | paused | cancelled | done
    created_at: Optional[float] = None

    def __post_init__(self):
        if self.created_at is None:
            object.__setattr__(self, "created_at", time.time())

    def step_ids(self) -> set:
        return {s.id for s in self.steps}

    def topological_order(self) -> list[Step]:
        """Kahn's algorithm for deterministic execution order."""
        unvisited = {s.id: s for s in self.steps}
        order = []
        available = [s for s in self.steps if not s.deps]
        seen: set[str] = set()
        while available:
            step = available.pop(0)
            if step.id in seen:
                continue
            seen.add(step.id)
            order.append(step)
            for candidate in self.steps:
                if candidate.id in seen:
                    continue
                if all(d in seen for d in candidate.deps):
                    if candidate not in available:
                        available.append(candidate)
            unvisited.pop(step.id, None)
        if unvisited:
            raise ValueError(f"Cyclic or dangling dependencies: {set(unvisited.keys())}")
        return order

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "steps": [s.__dict__ for s in self.steps],
            "state": self.state,
            "created_at": self.created_at,
        }


class Planner:
    """Simple rule-based planner.  Replace with LLM for complex domains."""

    DEFAULT_TIMEOUT = 30

    def __init__(self, step_timeout: int = None):
        self.step_timeout = step_timeout or self.DEFAULT_TIMEOUT

    async def create(self, mission: Mission) -> PlanDAG:
        """Parse a natural- or structured-goal into a DAG.

        For now: goals that contain semicolons or newline bullets are
        decomposed into sequential steps.  Everything else is a single step.
        """
        goal = mission.goal
        parts = []
        if ";" in goal:
            parts = [p.strip() for p in goal.split(";") if p.strip()]
        elif "\n" in goal:
            raw = [p.strip() for p in goal.split("\n") if p.strip() and not p.strip().startswith("#")]
            if len(raw) > 1:
                parts = raw
            else:
                parts = [goal.strip()]
        else:
            parts = [goal.strip()]

        steps = []
        for i, part in enumerate(parts):
            step_id = f"step_{i:03d}"
            prev = tuple(s.id for s in steps if i == len(steps))
            # Build a Step: heuristic tool assignment
            tool, params = self._heuristic_tool(part, mission)
            s = Step(
                id=step_id,
                tool=tool,
                params=params,
                timeout=self.step_timeout,
                deps=tuple(),  # Sequential: each depends on the previous  
                description=part[:200],
            )
            # Update deps after creation (since frozen, we recast)
            if i > 0:
                deps = (steps[-1].id,)
                s = Step(
                    id=s.id, tool=s.tool, params=s.params,
                    timeout=s.timeout, retries=s.retries,
                    deps=deps, description=s.description,
                )
            steps.append(s)

        dag = PlanDAG(
            mission_id=mission.requester_id,
            steps=tuple(steps),
        )
        return dag

    def _heuristic_tool(self, text: str, mission: Mission) -> tuple[str, dict]:
        import re, os
        lower = text.lower()

        if lower.startswith("read "):
            return ("file.read", {"path": text.split(maxsplit=1)[1]})

        if lower.startswith("write ") or lower.startswith("save "):
            rest = text.split(maxsplit=1)[1] if " " in text else ""
            # If the next token looks like a file path (contains /, \, or common extensions),
            # treat as file.write; otherwise it's a generative request for the LLM.
            first_token = rest.split(maxsplit=1)[0] if rest else ""
            path_like = bool(re.search(r"[./\\]|\.[a-zA-Z0-9]{1,10}$", first_token))
            if path_like:
                # Split into path and content if a space follows the path
                m = re.match(r"(\S+)\s+(.*)", rest)
                if m:
                    path, content = m.groups()
                else:
                    path, content = rest, ""
                return ("file.write", {"path": path, "content": content})
            # Generative fallback
            return ("llm.generate", {"prompt": text, "domain": mission.domain})

        if lower.startswith("search ") or lower.startswith("find "):
            return ("web.search", {"query": text})
        if lower.startswith("run ") or lower.startswith("execute "):
            return ("sandbox.run", {"command": text.split(maxsplit=1)[1]})
        if lower.startswith("validate "):
            return ("validation.diff", {"target": text.split(maxsplit=1)[1]})
        # Default: treat as an LLM/code generation step
        return ("llm.generate", {"prompt": text, "domain": mission.domain})
