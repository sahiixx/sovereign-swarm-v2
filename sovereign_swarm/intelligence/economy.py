from ..config import *

class EconomicEngine:
    def __init__(self):
        self.cost_history: List[Dict] = []; self.roi_log: List[Dict] = []

    def predict_cost(self, task_type: str, agent_tier: str = "medium") -> float:
        samples = [c["cost"] for c in self.cost_history if c.get("task_type") == task_type]
        if not samples:
            return {"untrusted": 0.002, "low": 0.005, "medium": 0.01, "high": 0.02, "sovereign": 0.03}.get(agent_tier, 0.01)
        return round(statistics.mean(samples[-50:]), 6)

    def record_cost(self, task_type: str, actual_cost: float, agent_id: str):
        self.cost_history.append({"task_type": task_type, "cost": actual_cost, "agent_id": agent_id, "timestamp": time.time()})

    def record_roi(self, task_type: str, revenue: float, cost: float):
        roi = (revenue - cost) / cost if cost else 0.0
        self.roi_log.append({"task_type": task_type, "revenue": revenue, "cost": cost, "roi": round(roi, 3), "timestamp": time.time()})

    def best_strategy(self, budget_remaining: float, task_types: List[str]) -> str:
        candidates = []
        for tt in task_types:
            pred = self.predict_cost(tt)
            roi_samples = [r["roi"] for r in self.roi_log if r["task_type"] == tt]
            avg_roi = statistics.mean(roi_samples[-20:]) if roi_samples else 0.5
            if pred <= budget_remaining and avg_roi > 0:
                candidates.append((tt, pred, avg_roi))
        if not candidates: return "none"
        candidates.sort(key=lambda x: x[2] / (x[1] + 1e-9), reverse=True)
        return candidates[0][0]

    def report(self) -> Dict:
        if not self.cost_history: return {"predictions": {}, "avg_roi": 0.0}
        recent_costs = [c["cost"] for c in self.cost_history[-100:]]
        recent_rois = [r["roi"] for r in self.roi_log[-50:]]
        return {
            "predictions": {task: self.predict_cost(task) for task in set(c["task_type"] for c in self.cost_history[-100:])},
            "avg_cost_100": round(statistics.mean(recent_costs), 6) if recent_costs else 0.0,
            "avg_roi_50": round(statistics.mean(recent_rois), 3) if recent_rois else 0.0,
            "total_spent": round(sum(c["cost"] for c in self.cost_history), 4)
        }


