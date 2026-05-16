"""DeterministicSovereignLoop — Intent → Plan → Execute → Validate → Govern → Complete.

Every transition is checkpointed. Every plan is immutable.
Self-modification is gated by governance.
Hard budgets terminate the loop before infinite recursion.
"""

import asyncio, json, time, traceback
from typing import Any, Dict, Optional, Callable
from pathlib import Path

from .mission import Mission, MissionState
from .result import Result
from .planner import Planner, PlanDAG
from .intent import IntentParser
from .validator import DifferentialValidator
from .checkpoint import CheckpointManager
from .budget import BudgetEnforcer
from .governance import LazyConsensusGate, Approval
from .sandbox import CapabilitySandbox
from .llm_router import LLMProviderRouter
from .tools import ToolRegistry
from ..infra.memory import SwarmMemory
from ..config import DATA_DIR


class DeterministicSovereignLoop:
    """Main engine implementing the six-state DSL."""

    STATES = ["INTENT", "PLAN", "EXECUTE", "VALIDATE", "GOVERN", "COMPLETE", "ROLLBACK", "ERROR"]

    def __init__(
        self,
        checkpoint_db: Path = None,
        sandbox: CapabilitySandbox = None,
        governor: LazyConsensusGate = None,
        budget: BudgetEnforcer = None,
        planner: Planner = None,
        validator: DifferentialValidator = None,
        intent_parser: IntentParser = None,
        llm_router: LLMProviderRouter = None,
        bus=None,
        on_state_change: Optional[Callable[[str, str, dict], None]] = None,
        memory: SwarmMemory = None,
    ):
        self.checkpoint = CheckpointManager(checkpoint_db)
        self.intent = intent_parser or IntentParser()
        self.planner = planner or Planner()
        self.validator = validator or DifferentialValidator()
        self.governor = governor or LazyConsensusGate(bus=bus)
        self.budget = budget or BudgetEnforcer()
        self.sandbox = sandbox or CapabilitySandbox()
        self.llm = llm_router or LLMProviderRouter()
        self.tools = ToolRegistry(self.llm)
        self.bus = bus
        self.on_state_change = on_state_change
        self.memory = memory

    async def run(self, raw_goal: str, requester_id: str = "default") -> Result:
        """Run the six-state DSL from a raw goal string."""
        mission_id = f"dsl:{requester_id}:{time.time():.6f}"
        meta = {"start": time.time(), "requester": requester_id}

        # Lazy-init memory
        if self.memory is None:
            self.memory = SwarmMemory(DATA_DIR / "dsl_memory.db")
            await self.memory.init()

        # Retrieve prior context for multi-turn continuity
        try:
            prior = await self.memory.search(requester_id, limit=5)
            if prior:
                meta["prior_context"] = [p["value"] for p in prior]
        except Exception:
            pass

        try:
            # ── 1. INTENT ──
            meta["state"] = "INTENT"
            self._emit(mission_id, "INTENT", meta)
            mission = await self._intent(raw_goal, meta)
            if not mission:
                return Result.error("INTENT_FAILED", "Could not parse goal into Mission", state="ERROR")

            self.checkpoint.save("post_intent", mission.to_dict(), mission_id)

            # Pre-flight budget
            if not self.budget.affordable(mission):
                return Result.error("OVER_BUDGET", f"Mission {mission.goal[:80]}... exceeds budget allocation", state="ERROR")

            # ── 2. PLAN ──
            meta["state"] = "PLAN"
            self._emit(mission_id, "PLAN", meta)
            try:
                dag = await self.planner.create(mission)
            except Exception as e:
                self.checkpoint.save("plan_failed", meta, mission_id)
                return Result.error("PLAN_FAILED", str(e), state="ERROR")

            self.checkpoint.save("post_plan", dag.to_dict(), mission_id)

            # ── 3. EXECUTE ──
            meta["state"] = "EXECUTE"
            self._emit(mission_id, "EXECUTE", meta)
            step_outputs: Dict[str, str] = {}
            for step in dag.topological_order():
                if self.budget.exhausted(mission):
                    snap_id = self.checkpoint.last_id(mission_id)
                    return Result.error(
                        "BUDGET_EXHAUSTED",
                        "Budget hit during execution",
                        rollback_target="post_plan",
                        state="ERROR",
                        checkpoint_id=snap_id,
                    )

                snap_id = f"pre_{step.id}"
                self.checkpoint.save(snap_id, {"step": step.to_dict(), "output": None}, mission_id)

                try:
                    output = await self._execute_step(step, mission)
                except Exception as exc:
                    errmsg = f"{step.id}: {exc}"
                    return Result.error(
                        "EXEC_FAILED", errmsg,
                        rollback_target="post_plan",
                        state="ERROR",
                        checkpoint_id=self.checkpoint.last_id(mission_id),
                    )

                step_outputs[step.id] = str(output)
                self.checkpoint.save(f"post_{step.id}", {"step": step.to_dict(), "output": str(output)[:4096]}, mission_id)
                self.budget.charge_time(mission.requester_id, 1.0)

            meta["state"] = "VALIDATE"
            self._emit(mission_id, "VALIDATE", meta)
            validation = await self.validator.diff_test(dag, expected=mission.goal, outputs=step_outputs)
            self.checkpoint.save("post_validate", validation.to_dict(), mission_id)

            if not validation.passed:
                snap_id = self.checkpoint.last_id(mission_id)
                return Result.error(
                    "VALIDATION_FAILED",
                    f"Validation confidence={validation.confidence:.2f} risk={validation.risk_score:.2f}",
                    rollback_target="post_plan",
                    state="ERROR",
                    checkpoint_id=snap_id,
                )

            # ── 5. GOVERN ──
            if mission.allow_self_modify and validation.has_gap:
                meta["state"] = "GOVERN"
                self._emit(mission_id, "GOVERN", meta)
                proposal = validation.to_proposal("validator")
                req = await self.governor.request(
                    proposal=json.dumps(proposal),
                    confidence=validation.confidence,
                    risk_score=validation.risk_score,
                    mission_id=mission_id,
                )
                decision = await self.governor.poll(req.proposal_id, timeout=30)
                if decision != Approval.GRANTED:
                    return Result.error(
                        "GOVERNANCE_DENIED",
                        f"Self-modification denied by governance: {decision.value}",
                        state="ERROR",
                    )
                # Apply patch in sandbox
                self.checkpoint.save("pre_patch", {"mission": mission.to_dict()}, mission_id)
                patch_res = await self.sandbox.apply_patch(validation.patch, timeout=10)
                if not patch_res["ok"]:
                    return Result.error(
                        "PATCH_APPLY_FAILED",
                        patch_res.get("stderr", "patch rejected by sandbox"),
                        state="ERROR",
                    )
                self.checkpoint.save("post_patch", {"patch_result": patch_res}, mission_id)

            # ── 6. COMPLETE ──
            elapsed = time.time() - meta["start"]
            self.checkpoint.save("complete", {"elapsed_sec": elapsed}, mission_id)
            self.budget.reset(mission_id)
            result_data = {
                "mission_id": mission_id,
                "mission": mission.to_dict(),
                "dag": dag.to_dict(),
                "outputs": step_outputs,
                "validation": validation.to_dict(),
                "checkpoints": [s.id for s in self.checkpoint.history(mission_id)],
            }
            # Persist result for multi-turn continuity
            try:
                await self.memory.store(
                    requester_id,
                    {"goal": raw_goal, "outputs": step_outputs, "elapsed": elapsed, "mission_id": mission_id},
                    tags=f"dsl,complete,{requester_id}",
                )
            except Exception:
                pass
            return Result.success(
                data=result_data,
                state="COMPLETE",
                checkpoint_id=self.checkpoint.last_id(mission_id),
                elapsed=elapsed,
            )

        except Exception as exc:
            meta["state"] = "ERROR"
            self._emit(mission_id, "ERROR", meta)
            snap_id = self.checkpoint.last_id(mission_id)
            return Result.error(
                "EXCEPTION",
                f"{type(exc).__name__}: {exc}",
                rollback_target=snap_id,
                state="ERROR",
                checkpoint_id=snap_id,
            )
        finally:
            if self.checkpoint:
                self.checkpoint.close()

    async def _intent(self, raw: str, meta: dict) -> Optional[Mission]:
        """Parse raw goal → Mission."""
        mission = self.intent.parse(raw, meta.get("requester", "default"))
        return mission

    async def _execute_step(self, step, mission: Mission) -> str:
        """Dispatch a single step through the tool registry."""
        return await self.tools.execute(step.tool, step.params, timeout=step.timeout)

    def _emit(self, mission_id: str, state: str, meta: dict):
        payload = {**meta, "mission_id": mission_id, "state": state, "ts": time.time()}
        if self.bus:
            try:
                asyncio.create_task(self.bus.publish("dsl.state_change", payload))
            except Exception:
                pass
        if self.on_state_change:
            try:
                self.on_state_change(mission_id, state, payload)
            except Exception:
                pass
