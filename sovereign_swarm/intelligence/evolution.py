from ..config import *

class EvolutionEngine:
    def __init__(self, population_size: int = 16):
        self.population: List[Dict] = []; self.generation = 0; self.population_size = population_size; self.fitness_history: List[float] = []

    def seed(self, strategies: List[Callable]):
        for i, strat in enumerate(strategies[:self.population_size]):
            self.population.append({"id": f"gen0_{i}", "strategy": strat, "fitness": 0.5, "age": 0, "games": 0})

    def evaluate(self, agent_result: Dict) -> float:
        score = agent_result.get("score", 0.5); confidence = agent_result.get("confidence", 1.0)
        collusion_flag = agent_result.get("collusion_flag", False); latency = agent_result.get("latency_ms", 100); cost = agent_result.get("cost_usd", 0.01)
        fitness = score - abs(confidence - score) * 0.3 - (0.4 if collusion_flag else 0) - (latency / 1000) * 0.1 - cost * 5.0
        return max(0.0, min(1.0, fitness))

    def generation_step(self, results: List[Dict]):
        for p in self.population: p["age"] += 1
        for p, res in zip(self.population, results):
            p["fitness"] = self.evaluate(res); p["games"] += 1
        self.population.sort(key=lambda x: x["fitness"], reverse=True)
        avg_fitness = sum(p["fitness"] for p in self.population) / len(self.population)
        self.fitness_history.append(avg_fitness)
        survivors = self.population[:max(1, len(self.population) // 2)]
        offspring = []
        while len(survivors) + len(offspring) < self.population_size:
            a, b = random.sample(survivors, 2)
            child = {"id": f"gen{self.generation}_{len(offspring)}", "strategy": a["strategy"], "fitness": (a["fitness"] + b["fitness"]) / 2, "age": 0, "games": 0}
            if random.random() < 0.2: child["fitness"] *= random.uniform(0.9, 1.1)
            offspring.append(child)
        self.population = survivors + offspring; self.generation += 1

    def best(self) -> Dict:
        return max(self.population, key=lambda x: x["fitness"]) if self.population else {}

    def report(self) -> Dict:
        return {
            "generation": self.generation, "population": len(self.population),
            "avg_fitness": round(sum(p["fitness"] for p in self.population) / len(self.population), 4) if self.population else 0.0,
            "best_fitness": round(self.best().get("fitness", 0.0), 4),
            "fitness_trend": [round(f, 4) for f in self.fitness_history[-10:]]
        }


