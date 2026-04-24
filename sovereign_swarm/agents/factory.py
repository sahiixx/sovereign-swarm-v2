from ..config import *
from .specialist import SpecialistAgent

class SpecialistFactory:
    SPECIALTIES = ["lead_scout", "ghost_hunter", "rate_lock", "document_bot", "bank_matcher", "commission_calc", "pipeline_tracker", "alert_bot", "memory_bot", "audit_bot"]
    @staticmethod
    def create(specialty: str, index: int = 0) -> SpecialistAgent:
        return SpecialistAgent(f"{specialty}_{index}", specialty)
    @staticmethod
    def spawn_all() -> List[SpecialistAgent]:
        return [SpecialistFactory.create(s, i) for i, s in enumerate(SpecialistFactory.SPECIALTIES)]
