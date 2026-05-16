"""Intent parser — raw goal to structured Mission."""

import re
from typing import Optional

from .mission import Mission


class IntentParser:
    """Parses natural language goals into structured Missions with budget extraction."""

    DOMAIN_PATTERNS = {
        "reverse": ["reverse engineer", "decompile", "unpack", "ghidra", "ida", "binary", "apk", "ipa"],
        "security": ["pentest", "scan", "vulnerability", "exploit", "audit", "cve"],
        "infra": ["deploy", "docker", "kubernetes", "terraform", "ansible", "cloud"],
        "dev": ["write code", "build app", "api", "frontend", "backend", "react", "node"],
        "data": ["scrape", "etl", "pipeline", "database", "sql", "warehouse"],
        "agent": ["swarm", "multi-agent", "orchestrate", "agent", "hermes"],
    }

    def parse(self, raw: str, requester_id: str = "default", created_at: float = None) -> Mission:
        domain = self._detect_domain(raw)
        budget = self._extract_budget(raw)
        return Mission(
            goal=raw,
            domain=domain,
            max_tokens=budget.get("max_tokens", 100_000),
            max_time_sec=budget.get("max_time_sec", 300),
            max_cost_usd=budget.get("max_cost_usd", 5.0),
            allow_self_modify="self-modify" in raw.lower() or "forge" in raw.lower(),
            requester_id=requester_id,
            created_at=created_at,
        )

    def _detect_domain(self, raw: str) -> str:
        text = raw.lower()
        scores = {}
        for domain, keywords in self.DOMAIN_PATTERNS.items():
            scores[domain] = sum(1 for kw in keywords if kw in text)
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "general"

    def _extract_budget(self, raw: str) -> dict:
        budget = {}
        m = re.search(r"(\d+)\s*tokens?", raw, re.I)
        if m:
            budget["max_tokens"] = int(m.group(1))
        m = re.search(r"(\d+)\s*s(?:ec)?", raw, re.I)
        if m:
            budget["max_time_sec"] = int(m.group(1))
        m = re.search(r"\$(\d+(?:\.\d+)?)", raw)
        if m:
            budget["max_cost_usd"] = float(m.group(1))
        return budget
