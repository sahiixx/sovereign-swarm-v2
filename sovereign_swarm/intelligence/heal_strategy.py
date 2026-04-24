from ..config import *

class HealStrategy(Enum):
    RETRY = "retry"; FALLBACK_AGENT = "fallback_agent"; DEGRADE_MODEL = "degrade_model"
    CIRCUIT_BREAK = "circuit_break"; QUARANTINE = "quarantine"; ROLLBACK = "rollback"; ESCALATE = "escalate"

