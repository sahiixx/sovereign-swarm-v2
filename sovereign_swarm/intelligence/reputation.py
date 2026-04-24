from ..config import *

class ReputationEngine:
    TIERS = [(0.0, 0.2, "untrusted"), (0.2, 0.4, "low"), (0.4, 0.6, "medium"), (0.6, 0.8, "high"), (0.8, 1.0, "sovereign")]
    def __init__(self, decay_halflife_hours: float = 24.0):
        self.agents: Dict[str, Dict] = {}; self.decay_halflife = decay_halflife_hours * 3600
        self.interaction_matrix: Dict[Tuple[str, str], int] = defaultdict(int)

    def tier(self, agent_id: str) -> str:
        score = self.score(agent_id)
        for lo, hi, name in self.TIERS:
            if lo <= score <= hi: return name
        return "untrusted"

    def score(self, agent_id: str) -> float:
        rec = self.agents.get(agent_id, {"score": 0.5, "last_update": time.time()})
        age = time.time() - rec["last_update"]
        decay = 0.5 ** (age / self.decay_halflife)
        return max(0.0, rec["score"] * decay)

    def update(self, agent_id: str, delta: float, reason: str = ""):
        now = time.time()
        old = self.agents.get(agent_id, {"score": 0.5, "last_update": now})
        age = now - old["last_update"]
        base = old["score"] * (0.5 ** (age / self.decay_halflife))
        new_score = max(0.0, min(1.0, base + delta))
        self.agents[agent_id] = {"score": new_score, "last_update": now, "history": old.get("history", []) + [(now, delta, reason)]}

    def record_interaction(self, a: str, b: str):
        self.interaction_matrix[tuple(sorted([a, b]))] += 1

    def detect_collusion(self, threshold: int = 10, correlation_threshold: float = 0.85) -> List[Dict]:
        alerts = []
        for (a, b), count in self.interaction_matrix.items():
            if count >= threshold:
                correlation = 1.0 - abs(self.score(a) - self.score(b))
                if correlation >= correlation_threshold:
                    alerts.append({"pair": (a, b), "interactions": count, "score_correlation": round(correlation, 3), "severity": "high" if count >= threshold * 2 else "medium"})
        return alerts

    def report(self) -> Dict:
        return {aid: {"score": round(self.score(aid), 3), "tier": self.tier(aid)} for aid in self.agents}


