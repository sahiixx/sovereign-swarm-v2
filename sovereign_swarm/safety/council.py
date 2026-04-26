"""SafetyCouncil — hardened with arm/disarm, input normalization, bounded deques."""

from ..config import *
from collections import deque


class SafetyVerdict:
    """Result of a SafetyCouncil scan."""

    def __init__(self, safe: bool, threat_level: str = "none",
                 violations: list[str] = None, sanitized: str = "",
                 recommendation: str = ""):
        self.safe = safe
        self.threat_level = threat_level
        self.violations = violations or []
        self.sanitized = sanitized
        self.recommendation = recommendation

    def to_dict(self) -> dict:
        return {
            "safe": self.safe,
            "threat_level": self.threat_level,
            "violations": self.violations,
            "sanitized": self.sanitized,
            "recommendation": self.recommendation,
        }


class SafetyCouncil:
    """Multi-layer safety scanner with adaptive rules, arm/disarm, and bounded history.

    Built-in patterns detect dangerous operations. Adaptive rules learn from
    repeated violations. History is stored in a bounded deque (max 1000 entries).
    Input is normalized before scanning (control chars stripped, truncated at 10k).
    """

    BUILTIN_PATTERNS: dict[str, str] = {
        "rm -rf": "critical",
        "mkfs.": "critical",
        r"eval\s*\(": "high",
        r"exec\s*\(": "high",
        "os.system": "high",
        "subprocess.call": "high",
        r"curl\s+.*\| bash": "high",
        "__import__": "medium",
        "chmod 777": "medium",
        "sudo": "medium",
        "dd if=": "high",
    }

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode
        self._armed = True
        self._adaptive_rules: dict[str, str] = {}
        self.violation_history: deque = deque(maxlen=1000)
        self._lock = asyncio.Lock()

    def scan(self, content: str, system_load: float = 0.0) -> dict:
        """Scan content against all rules."""
        return self.scan_sync(content, system_load)

    def scan_sync(self, content: str, system_load: float = 0.0) -> dict:
        sanitized = self.normalize_input(content)
        violations: list[str] = []
        max_severity = "none"
        severity_order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

        all_rules = {**self.BUILTIN_PATTERNS, **self._adaptive_rules}

        for pattern, severity in all_rules.items():
            if re.search(pattern, sanitized, re.IGNORECASE):
                violations.append(f"Matched '{pattern}' (severity: {severity})")
                if severity_order[severity] > severity_order[max_severity]:
                    max_severity = severity

        safe = len(violations) == 0 or not self._armed

        if violations:
            self.violation_history.append({
                "rule": pattern if violations else "none",
                "text": sanitized[:200],
                "load": system_load,
                "severity": max_severity,
            })

        rec_map = {
            "critical": "BLOCK IMMEDIATELY. Critical threat detected.",
            "high": "High risk input. Requires manual review before execution.",
            "medium": "Medium risk. Verify intent and sandbox if possible.",
            "low": "Low risk anomaly. Log and continue with caution.",
            "none": "No threats detected. Proceed normally.",
        }

        return {
            "blocked": not safe,
            "safe": safe,
            "threat_level": max_severity,
            "violations": violations,
            "sanitized": sanitized,
            "confidence": 1.0 if max_severity != "none" else 0.0,
            "rule": violations[-1].split(":")[0].replace("Matched '", "") if violations else "none",
            "recommendation": rec_map.get(max_severity, "Unknown"),
        }

    def normalize_input(self, raw: str, max_length: int = 10000) -> str:
        """Strip control characters and truncate."""
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
        return cleaned[:max_length]

    def arm(self):
        self._armed = True

    def disarm(self):
        self._armed = False

    def arm_emergency(self):
        self._armed = True
        self.add_adaptive_rule("delete", "high")
        self.add_adaptive_rule("format", "critical")
        self.add_adaptive_rule("wipe", "critical")

    def disarm_emergency(self):
        self._adaptive_rules.pop("delete", None)
        self._adaptive_rules.pop("format", None)
        self._adaptive_rules.pop("wipe", None)
        self._armed = True

    def add_adaptive_rule(self, pattern: str, severity: str):
        self._adaptive_rules[pattern] = severity

    def adaptive_rules(self) -> list[str]:
        texts = [v["text"][:50] for v in self.violation_history]
        common = Counter(texts).most_common(3)
        return [f"adaptive_block:{c[0]}" for c in common if c[1] >= 3]

    def get_rules(self) -> list[dict]:
        rules = []
        for pattern, severity in {**self.BUILTIN_PATTERNS, **self._adaptive_rules}.items():
            rules.append({"pattern": pattern, "severity": severity})
        return rules

    def _heuristic_score(self, text: str) -> float:
        if not text:
            return 0.0
        entropy = self._shannon_entropy(text)
        shell_chars = sum(1 for c in text if c in r"|;$&\\`")
        return min(1.0, (entropy / 5.0) * 0.4 + (shell_chars / max(len(text), 1)) * 0.6)

    @staticmethod
    def _shannon_entropy(s: str) -> float:
        if not s:
            return 0
        counts = Counter(s)
        length = len(s)
        return -sum((c / length) * math.log2(c / length) for c in counts.values())
