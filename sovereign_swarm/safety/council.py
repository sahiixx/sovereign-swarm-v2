from ..config import *

class SafetyCouncil:
    def __init__(self):
        self.forbidden_patterns = [r"rm\s+-rf", r"mkfs", r"format\s+", r"shutdown", r"eval\s*\(", r"curl\s+.*\|\s*bash", r"import\s+os\.system", r"subprocess\.call", r"__import__\s*\(", r"exec\s*\("]
        self.violation_history: List[Dict] = []; self.emergency_mode = False; self.stress_threshold = 0.8

    def scan(self, text: str, system_load: float = 0.0) -> Dict:
        confidence_cutoff = 0.65 if system_load > self.stress_threshold else 0.85
        for pat in self.forbidden_patterns:
            if re.search(pat, text, re.IGNORECASE):
                self.violation_history.append({"rule": pat, "text": text[:200], "load": system_load})
                return {"blocked": True, "confidence": 1.0, "rule": f"pattern:{pat}"}
        score = self._heuristic_score(text)
        if score >= confidence_cutoff:
            self.violation_history.append({"rule": "heuristic", "text": text[:200], "load": system_load})
            return {"blocked": True, "confidence": score, "rule": "heuristic"}
        if self.emergency_mode and system_load > 0.9:
            if any(k in text.lower() for k in ["delete", "format", "wipe", "drop", "kill"]):
                return {"blocked": True, "confidence": 0.7, "rule": "emergency_keyword"}
        return {"blocked": False, "confidence": 1.0 - score, "rule": "none"}

    def _heuristic_score(self, text: str) -> float:
        if not text: return 0.0
        entropy = self._shannon_entropy(text); shell_chars = sum(1 for c in text if c in r"|;$&\`")
        return min(1.0, (entropy / 5.0) * 0.4 + (shell_chars / max(len(text), 1)) * 0.6)

    @staticmethod
    def _shannon_entropy(s: str) -> float:
        if not s: return 0
        counts = Counter(s); length = len(s)
        return -sum((c / length) * math.log2(c / length) for c in counts.values())

    def adaptive_rules(self) -> List[str]:
        texts = [v["text"][:50] for v in self.violation_history]
        common = Counter(texts).most_common(3)
        return [f"adaptive_block:{c[0]}" for c in common if c[1] >= 3]


