"""OmniBridge — agency-agents → sovereign-swarm-v2 bridge (v2.2.0).

Wraps the OMNI Integration layer (StaticAnalyzer, FridaActuator, GhidraMCPClient,
BinaryDiffer) and exposes them through the HermesV2 channel as a first-class bridge.
Includes JSON-Schema validation using the bundled integration_schema.json.
"""
import hashlib, json, os, subprocess, traceback, sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# import jsonschema if available; degrade gracefully
try:
    import jsonschema
    from jsonschema import validate, ValidationError as JsonSchemaValidationError
except Exception:  # pragma: no cover
    jsonschema = None
    JsonSchemaValidationError = Exception  # type: ignore

from ..config import *
from ..omni.omni_integration import AnalysisArtifact, StaticAnalyzer, FridaActuator, GhidraMCPClient, BinaryDiffer


_SCHEMA_PATH = Path(__file__).with_suffix("").parent.parent / "omni" / "integration_schema.json"
_OMNI_SCHEMA: Optional[Dict] = None


def _load_schema() -> Optional[Dict]:
    global _OMNI_SCHEMA
    if _OMNI_SCHEMA is not None:
        return _OMNI_SCHEMA
    try:
        if _SCHEMA_PATH.exists():
            with open(_SCHEMA_PATH, "r", encoding="utf-8") as fh:
                _OMNI_SCHEMA = json.load(fh)
                return _OMNI_SCHEMA
    except Exception:
        pass
    return None


def _schema_validate(payload: Dict, definition: str) -> Dict:
    schema = _load_schema()
    if not schema:
        return {"valid": False, "error": "schema_unavailable", "detail": "integration_schema.json not loaded"}
    if not jsonschema:
        return {"valid": False, "error": "jsonschema_unavailable", "detail": "jsonschema library not installed"}

    defs = schema.get("definitions", {})
    target = defs.get(definition)
    if not target:
        return {"valid": False, "error": "definition_not_found", "detail": definition}

    try:
        validate(instance=payload, schema=target)
        return {"valid": True}
    except JsonSchemaValidationError as exc:
        return {"valid": False, "error": "validation_failed", "detail": str(exc)}
    except Exception as exc:
        return {"valid": False, "error": "validation_error", "detail": str(exc)}


def _artifact_to_dict(artifact: AnalysisArtifact) -> Dict:
    return {
        "binary_path": artifact.binary_path,
        "analysis_type": artifact.analysis_type,
        "functions": artifact.functions,
        "strings": artifact.strings,
        "imports": artifact.imports,
        "sections": artifact.sections,
        "call_graph": artifact.call_graph,
        "vulnerabilities": artifact.vulnerabilities,
        "frida_hooks": artifact.frida_hooks,
        "raw_output": artifact.raw_output,
        "sha256": artifact.sha256,
    }


class OmniBridge:
    """First-class bridge for Sovereign Swarm v2.2.0 OMNI Integration."""

    VERSION = "2.2.0"

    def __init__(self, ghidra_path: Optional[str] = None, schema_path: Optional[str] = None):
        self.ghidra = GhidraMCPClient(ghidra_path=ghidra_path)
        self.static = StaticAnalyzer()
        self.frida = FridaActuator()
        self.differ = BinaryDiffer()
        self._schema_path = schema_path
        # load schema eagerly so errors surface early
        self._schema = _load_schema()

    # ── Validation utilities ─────────────────────────────

    def validate_static_map(self, payload: Dict) -> Dict:
        return _schema_validate(payload, "StaticMapArtifact")

    def validate_dynamic_truth(self, payload: Dict) -> Dict:
        return _schema_validate(payload, "DynamicTruthArtifact")

    def validate_crm_skill(self, payload: Dict) -> Dict:
        return _schema_validate(payload, "CRMSkillRecord")

    def validate_bus_message(self, payload: Dict, msg_type: str) -> Dict:
        mapping = {
            "actuator_command": "BusMessageActuatorCommand",
            "scheduler_task": "BusMessageSchedulerTask",
            "crm_sync": "BusMessageCRMSync",
            "state_event": "BusMessageStateEvent",
        }
        return _schema_validate(payload, mapping.get(msg_type, msg_type))

    # ── Action handlers ──────────────────────────────────

    async def handle_static_analyze(self, payload: Dict) -> Dict:
        binary_path = payload.get("binary_path", "")
        if not binary_path or not Path(binary_path).exists():
            return {"error": "E_BINARY_NOT_FOUND", "binary_path": binary_path}
        try:
            artifact = await self.static.analyze(binary_path)
            result = _artifact_to_dict(artifact)
            validation = self.validate_static_map(result)
            result["schema_valid"] = validation["valid"]
            if not validation["valid"]:
                result["schema_errors"] = validation.get("detail", "")
            return {"status": "ok", "artifact": result}
        except Exception as exc:
            return {"error": "E_OBJDUMP_MISSING", "detail": str(exc), "trace": traceback.format_exc()}

    async def handle_dynamic_instrument(self, payload: Dict) -> Dict:
        binary_path = payload.get("binary_path", "")
        if not binary_path or not Path(binary_path).exists():
            return {"error": "E_BINARY_NOT_FOUND", "binary_path": binary_path}
        if not self.frida.available:
            return {"error": "E_FRIDA_NOT_INSTALLED", "detail": "frida-tools not available"}
        try:
            artifact = await self.frida.instrument(binary_path, script=payload.get("script"))
            result = _artifact_to_dict(artifact)
            validation = self.validate_dynamic_truth(result)
            result["schema_valid"] = validation["valid"]
            if not validation["valid"]:
                result["schema_errors"] = validation.get("detail", "")
            return {"status": "ok", "artifact": result}
        except Exception as exc:
            return {"error": "E_FRIDA_ATTACH_FAILED", "detail": str(exc), "trace": traceback.format_exc()}

    async def handle_binary_diff(self, payload: Dict) -> Dict:
        path_a = payload.get("path_a", "")
        path_b = payload.get("path_b", "")
        if not path_a or not Path(path_a).exists():
            return {"error": "E_BINARY_NOT_FOUND", "path": path_a}
        if not path_b or not Path(path_b).exists():
            return {"error": "E_BINARY_NOT_FOUND", "path": path_b}
        try:
            result = await self.differ.diff(path_a, path_b)
            return {"status": "ok", "diff": result}
        except Exception as exc:
            return {"error": "diff_failed", "detail": str(exc), "trace": traceback.format_exc()}

    async def handle_crm_sync(self, payload: Dict) -> Dict:
        # CRM sync is a placeholder until a real CRM db path is supplied.
        action = payload.get("action", "status")
        try:
            if action == "status":
                return {"status": "ok", "offline_mode": True, "pushed": 0, "pulled_leads": 0}
            if action == "sync":
                return {"status": "ok", "offline_mode": True, "pushed": 0, "pulled_leads": 0, "note": "no live CRM db configured"}
            if action == "write_skill":
                skill = payload.get("skill", {})
                validation = self.validate_crm_skill(skill)
                if not validation["valid"]:
                    return {"error": "E_CRM_SCHEMA_MISMATCH", "detail": validation.get("detail", "")}
                return {"status": "ok", "written": True, "skill_id": skill.get("id", "unknown")}
            return {"error": "unknown_action", "action": action}
        except Exception as exc:
            return {"error": "E_CRM_OFFLINE", "detail": str(exc), "trace": traceback.format_exc()}

    async def handle_schema_validate(self, payload: Dict) -> Dict:
        msg_type = payload.get("msg_type", "")
        target = payload.get("payload", {})
        if not msg_type:
            return {"error": "missing_msg_type"}
        result = self.validate_bus_message(target, msg_type)
        return {"status": "ok", "validation": result}

    # ── Unified Hermes entrypoint ──────────────────────

    async def handle(self, payload: Dict) -> Dict:
        action = payload.get("action", "")
        if action == "static.analyze":
            return await self.handle_static_analyze(payload)
        if action == "dynamic.instrument":
            return await self.handle_dynamic_instrument(payload)
        if action == "binary.diff":
            return await self.handle_binary_diff(payload)
        if action in ("crm.sync", "crm.status", "crm.write_skill"):
            return await self.handle_crm_sync(payload)
        if action == "schema.validate":
            return await self.handle_schema_validate(payload)
        if action == "version":
            return {"status": "ok", "bridge_version": self.VERSION, "channels": ["omni"], "schema_loaded": self._schema is not None}
        if action == "report":
            return {
                "status": "ok",
                "bridge_version": self.VERSION,
                "ghidra_available": self.ghidra.available,
                "frida_available": self.frida.available,
                "schema_loaded": self._schema is not None,
                "schema_path": str(self._schema_path),
            }
        return {"error": "unknown_action", "action": action, "bridge_version": self.VERSION}

    def report(self) -> Dict:
        return {
            "bridge": "OmniBridge",
            "version": self.VERSION,
            "ghidra_available": self.ghidra.available,
            "frida_available": self.frida.available,
            "schema_loaded": self._schema is not None,
            "schema_path": str(self._schema_path),
        }
