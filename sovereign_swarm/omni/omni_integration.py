"""OMNI Integration — Reverse Engineering Bridge for Sovereign Swarm DSL."""
import hashlib, json, os, subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

@dataclass
class AnalysisArtifact:
    binary_path: str
    analysis_type: str
    functions: List[Dict] = field(default_factory=list)
    strings: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    sections: List[Dict] = field(default_factory=list)
    call_graph: Dict = field(default_factory=dict)
    vulnerabilities: List[Dict] = field(default_factory=list)
    frida_hooks: List[str] = field(default_factory=list)
    raw_output: str = ""
    sha256: str = ""

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}

def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def _which(cmd: str):
    for dir_path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(dir_path) / cmd
        if candidate.exists():
            return str(candidate)
    return None

class GhidraMCPClient:
    def __init__(self, ghidra_path=None, project_path=None):
        self.ghidra_path = ghidra_path or os.environ.get("GHIDRA_HOME", "")
        self.project_path = project_path or "/tmp/ghidra_omni_proj"
        self._available = self._detect()

    def _detect(self):
        if self.ghidra_path and Path(self.ghidra_path).exists():
            return True
        return _which("analyzeHeadless") is not None

    @property
    def available(self):
        return self._available

    async def analyze(self, binary_path: str):
        if not self.available:
            return AnalysisArtifact(binary_path=binary_path, analysis_type="static", raw_output="Ghidra not available")
        return AnalysisArtifact(binary_path=binary_path, analysis_type="static", raw_output="Ghidra analysis stub", sha256=_file_hash(binary_path))

class StaticAnalyzer:
    def __init__(self):
        self._tools = {k: _which(k) for k in ["file", "strings", "nm", "objdump", "r2", "rabin2"]}

    async def analyze(self, binary_path: str):
        artifact = AnalysisArtifact(binary_path=binary_path, analysis_type="static", sha256=_file_hash(binary_path))
        if self._tools["file"]:
            try:
                proc = subprocess.run([self._tools["file"], binary_path], capture_output=True, text=True, timeout=10)
                artifact.raw_output += f"[file]\n{proc.stdout}\n"
            except Exception:
                pass
        if self._tools["strings"]:
            try:
                proc = subprocess.run([self._tools["strings"], "-n", "8", binary_path], capture_output=True, text=True, timeout=15)
                artifact.strings = proc.stdout.strip().splitlines()[:200]
                artifact.raw_output += f"[strings] {len(artifact.strings)} found\n"
            except Exception:
                pass
        if self._tools["nm"]:
            try:
                proc = subprocess.run([self._tools["nm"], "-C", binary_path], capture_output=True, text=True, timeout=15)
                funcs = []
                for line in proc.stdout.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[-2] in "TtWw":
                        funcs.append({"name": parts[-1], "type": parts[-2]})
                artifact.functions = funcs[:500]
                artifact.raw_output += f"[nm] {len(funcs)} functions\n"
            except Exception:
                pass
        if self._tools["rabin2"]:
            try:
                for flag, key in [("-i", "imports"), ("-S", "sections")]:
                    proc = subprocess.run([self._tools["rabin2"], flag, binary_path], capture_output=True, text=True, timeout=15)
                    if key == "imports":
                        artifact.imports = [l.strip() for l in proc.stdout.splitlines()[:200]]
                    else:
                        sections = []
                        for line in proc.stdout.splitlines()[:50]:
                            parts = line.strip().split()
                            if len(parts) >= 4:
                                sections.append({"name": parts[-1], "size": parts[2], "vaddr": parts[3]})
                        artifact.sections = sections
                artifact.raw_output += "[rabin2] analyzed\n"
            except Exception:
                pass
        return artifact

class FridaActuator:
    def __init__(self):
        self._available = _which("frida") is not None
        self._frida_ps = _which("frida-ps")

    @property
    def available(self):
        return self._available

    async def instrument(self, binary_path: str, script: str = None):
        artifact = AnalysisArtifact(binary_path=binary_path, analysis_type="dynamic", sha256=_file_hash(binary_path))
        if not self.available:
            artifact.raw_output = "Frida not available"
            return artifact
        artifact.raw_output = "Frida instrumentation stub"
        return artifact

    async def list_processes(self):
        return []

class BinaryDiffer:
    async def diff(self, path_a: str, path_b: str):
        result = {
            "path_a": path_a,
            "path_b": path_b,
            "sha256_a": _file_hash(path_a),
            "sha256_b": _file_hash(path_b),
            "identical": False,
            "size_delta": 0,
            "string_delta": [],
        }
        sa = Path(path_a).stat()
        sb = Path(path_b).stat()
        result["size_delta"] = sb.st_size - sa.st_size
        result["identical"] = result["sha256_a"] == result["sha256_b"]
        tool = _which("strings")
        if tool:
            try:
                a_str = subprocess.run([tool, path_a], capture_output=True, text=True, timeout=15).stdout.splitlines()
                b_str = subprocess.run([tool, path_b], capture_output=True, text=True, timeout=15).stdout.splitlines()
                result["string_delta"] = list(set(b_str) - set(a_str))[:100]
            except Exception:
                pass
        return result
