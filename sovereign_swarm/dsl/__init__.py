"""DeterministicSovereignLoop (DSL) — Outperform OMNI v2026.S.

Modules:
    mission        — Immutable Mission with frozen budgets
    result         — Structured Result with rollback targets
    checkpoint     — Git-like SQLite snapshots with SHA256 checksums
    budget         — Hard circuit breakers (tokens, time, cost)
    governance     — LazyConsensusGate with auto-approve thresholds
    sandbox        — Subprocess + unshare + rlimits
    planner        — Immutable DAG with Kahn topological sort
    validator      — Differential testing with confidence scores
    intent         — Rule-based NL goal parser with domain detection
    loop           — DeterministicSovereignLoop main engine

Usage:
    from sovereign_swarm.dsl import DeterministicSovereignLoop, Mission
    loop = DeterministicSovereignLoop()
    result = await loop.run("Write a FastAPI auth service")
"""

from .mission import Mission, MissionState, mission_from_json
from .result import Result
from .checkpoint import CheckpointManager, Snapshot
from .budget import BudgetEnforcer, BudgetSnap
from .governance import LazyConsensusGate, GovernanceRequest, Approval
from .sandbox import CapabilitySandbox
from .planner import Planner, PlanDAG, Step
from .validator import DifferentialValidator, ValidationReport
from .intent import IntentParser
from .loop import DeterministicSovereignLoop
from .llm_router import LLMProviderRouter
from .tools import ToolRegistry

__all__ = [
    "Mission",
    "MissionState",
    "mission_from_json",
    "Result",
    "CheckpointManager",
    "Snapshot",
    "BudgetEnforcer",
    "BudgetSnap",
    "LazyConsensusGate",
    "GovernanceRequest",
    "Approval",
    "CapabilitySandbox",
    "Planner",
    "PlanDAG",
    "Step",
    "DifferentialValidator",
    "ValidationReport",
    "IntentParser",
    "DeterministicSovereignLoop",
    "LLMProviderRouter",
    "ToolRegistry",
]
