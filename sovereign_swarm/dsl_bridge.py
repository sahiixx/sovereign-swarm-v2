"""dsl_bridge.py — Wire DeterministicSovereignLoop into Sovereign Swarm v2.

Integrates with SwarmBus (infra/bus), BudgetController (safety/budget),
SafetyCouncil (safety/council), and MetaOrchestrator (intelligence/orchestrator).
"""

import asyncio, os
from pathlib import Path
from typing import Optional, Callable

from sovereign_swarm.dsl import DeterministicSovereignLoop, LazyConsensusGate, CapabilitySandbox
from sovereign_swarm.dsl.budget import BudgetEnforcer
from sovereign_swarm.dsl.checkpoint import CheckpointManager

from sovereign_swarm.infra.bus import SwarmBus
from sovereign_swarm.safety.budget import BudgetController
from sovereign_swarm.safety.council import SafetyCouncil
from sovereign_swarm.intelligence.orchestrator import MetaOrchestrator


class DSLBridge:
    """Single-point adapter.  Creates a DSL loop that is wired into the
    existing SwarmBus, SafetyCouncil, and BudgetController.
    """

    def __init__(
        self,
        bus: Optional[SwarmBus] = None,
        budget_controller: Optional[BudgetController] = None,
        council: Optional[SafetyCouncil] = None,
        orchestrator: Optional[MetaOrchestrator] = None,
        data_dir: Path = None,
        hitl_callback=None,
    ):
        self.bus = bus
        self.budget_controller = budget_controller
        self.council = council
        self.orchestrator = orchestrator
        self.data_dir = data_dir or Path(os.getenv("SWARM_DATA_DIR", "./data"))
        self.hitl_callback = hitl_callback

        # DSL internals
        self._dsl_budget = BudgetEnforcer()
        self._checkpoint = CheckpointManager(self.data_dir / "dsl_checkpoints.db")
        self._sandbox = CapabilitySandbox()
        self._governor = LazyConsensusGate(hitl_callback=hitl_callback, bus=bus)
        self._loop = DeterministicSovereignLoop(
            checkpoint_db=self.data_dir / "dsl_checkpoints.db",
            sandbox=self._sandbox,
            governor=self._governor,
            budget=self._dsl_budget,
            bus=bus,
            on_state_change=self._on_state,
        )

    def _on_state(self, mission_id: str, state: str, meta: dict):
        """Publish every DSL state change to the SwarmBus topic `dsl.state`."""
        if self.bus:
            asyncio.create_task(self.bus.publish(
                "dsl.state", {"mission_id": mission_id, "state": state, **meta}
            ))

        # Reflect into BudgetController for dashboard visibility
        if self.budget_controller and state in ("EXECUTE", "VALIDATE", "GOVERN"):
            if state == "VALIDATE":
                cost = meta.get("cost_so_far", 0.01)
                asyncio.create_task(self.budget_controller.charge(mission_id, cost))

        # SafetyCouncil: abort on critical states
        if self.council and state == "ERROR":
            payload = meta.get("error_message", "DSL ERROR")
            verdict = self.council.scan_sync(payload)
            if verdict.get("blocked"):
                self._dsl_budget.arm_kill_switch(mission_id)

    async def run(self, raw_goal: str, requester_id: str = "default"):
        """Execute a Mission through the DSL and return a Result."""
        return await self._loop.run(raw_goal, requester_id=requester_id)

    async def run_batch(self, goals: list[str], requester_id: str = "default"):
        results = []
        for g in goals:
            results.append(await self.run(g, requester_id))
        return results

    def status(self) -> dict:
        return {
            "checkpoints": "ok" if self._checkpoint else "down",
            "governance": self._governor.report(),
            "budget": {k: v for k, v in self._dsl_budget._budgets.items()},
        }
