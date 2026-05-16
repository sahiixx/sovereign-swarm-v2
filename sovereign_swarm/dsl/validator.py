"""Differential Validator — deterministic tests, not just LLM judge.

Produces a ValidationReport with pass/fail, confidence, and risk so
that the governance layer can decide whether a patch is needed.
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .mission import Mission
from .planner import PlanDAG


class ValidationReport:
    def __init__(
        self,
        passed: bool,
        confidence: float,
        risk_score: float,
        has_gap: bool,
        step_results: List[Dict],
        patch: str = "",
        target_checkpoints: List[str] = None,
        analysis_artifacts: Dict = None,
    ):
        self.passed = passed
        self.confidence = confidence
        self.risk_score = risk_score
        self.has_gap = has_gap
        self.step_results = step_results
        self.patch = patch
        self.target_checkpoints = target_checkpoints or []
        self.analysis_artifacts = analysis_artifacts or {}

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "confidence": round(self.confidence, 5),
            "risk_score": round(self.risk_score, 5),
            "has_gap": self.has_gap,
            "step_results": self.step_results,
            "patch": self.patch[:4096],
            "target_checkpoints": self.target_checkpoints,
            "analysis_artifacts": self.analysis_artifacts,
        }

    def to_proposal(self, requested_by: str = "validator") -> dict:
        return {
            "proposal_type": "self_modify" if self.has_gap else "patch",
            "patch": self.patch[:4096],
            "confidence": self.confidence,
            "risk_score": self.risk_score,
            "reason": "Validation gap detected — patch required to close capability gap",
            "requested_by": requested_by,
            "artifacts": self.analysis_artifacts,
        }


class DifferentialValidator:
    """Validates DAG output with differential tests + confidence scoring.

    For reverse engineering missions, bridges to OMNI's Ghidra/Frida
    integration to produce real static/dynamic analysis artifacts.
    """

    HIGH_RISK_TOOLS = {"llm.generate", "code.execute", "synthesize", "self.modify"}
    CONFIDENCE_DECAY = 0.05

    def __init__(self):
        self._baseline: Dict[str, Any] = {}
        self._omni: Optional[Any] = None
        self._omni_path: str = ""

    def _init_omni(self):
        """Lazy init of OMNI integration — import only when needed."""
        if self._omni is not None:
            return
        try:
            sys.path.insert(0, "/home/sahiix/workspace")
            from omni_integration import GhidraMCPClient, StaticAnalyzer, FridaActuator
            self._omni = {
                "ghidra": GhidraMCPClient(),
                "static": StaticAnalyzer(),
                "frida": FridaActuator(),
            }
            self._omni_path = "/home/sahiix/workspace/omni_integration.py"
        except Exception as exc:
            self._omni = None
            self._omni_path = str(exc)

    async def diff_test(self, dag: PlanDAG, expected: str, outputs: Dict[str, str] = None) -> ValidationReport:
        outputs = outputs or {}
        step_results: List[Dict] = []
        passed = True
        confidence = 1.0
        risk = 0.0
        gaps: List[str] = []

        for step in dag.topological_order():
            sr = {
                "step": step.id,
                "tool": step.tool,
                "ok": True,
                "error": "",
                "output_hash": self._hash(outputs.get(step.id, "")),
            }
            if step.tool in self.HIGH_RISK_TOOLS:
                risk = max(risk, 0.3)
                confidence *= (1 - self.CONFIDENCE_DECAY)
                sr["risk_note"] = "Generative tool"

            # Heuristic: did output mention the goal keywords?
            out = outputs.get(step.id, "")
            score = self._score(out, expected)
            if score < 0.5:
                sr["ok"] = False
                sr["error"] = f"Output relevance low ({score:.2f})"
                gaps.append(step.id)

            step_results.append(sr)

        overall_pass = confidence >= 0.7 and risk <= 0.5 and len(gaps) == 0
        has_gap = len(gaps) > 0

        # ── OMNI bridge: reverse engineering ──
        artifacts = {}
        if expected.lower().startswith(("reverse", "analyze", "decompile", "disassemble", "re")) and self._omni is None:
            self._init_omni()
        if self._omni:
            binary_path = next((outputs.get(s.id) for s in dag.topological_order() if s.tool in ("file.read", "web.fetch")), None)
            if binary_path and Path(binary_path).is_file():
                try:
                    static = self._omni["static"]
                    artifact = await static.analyze(binary_path)
                    artifacts["static"] = artifact.to_dict() if hasattr(artifact, "to_dict") else artifact
                    confidence = min(confidence, 0.99)
                    has_gap = False
                except Exception as exc:
                    artifacts["static_error"] = str(exc)
            else:
                artifacts["static_skip"] = "No binary file found in step outputs"

        patch = ""
        if has_gap:
            patch = f"# Patch for gap steps: {gaps}\n# Regenerate with stronger prompt constraints\n"

        return ValidationReport(
            passed=overall_pass,
            confidence=confidence,
            risk_score=risk,
            has_gap=has_gap,
            step_results=step_results,
            patch=patch,
            analysis_artifacts=artifacts,
        )

    def _score(self, output: str, expected: str) -> float:
        """Simple heuristic: exact match = 1.0, substring = 0.8, token overlap = 0.0–0.7."""
        if not output and not expected:
            return 1.0
        if not output:
            return 0.0
        if output.strip().lower() == expected.strip().lower():
            return 1.0
        if expected.lower() in output.lower() or output.lower() in expected.lower():
            return 0.8
        # Jaccard on simple token split
        a = set(output.lower().split())
        b = set(expected.lower().split())
        inter = a & b
        union = a | b
        return len(inter) / max(len(union), 1)

    @staticmethod
    def _hash(s: str) -> str:
        import hashlib
        return hashlib.sha256(s.encode()).hexdigest()[:16]
