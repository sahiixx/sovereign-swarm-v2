from ..config import *
from dataclasses import dataclass

@dataclass
class ScheduledJob:
    name: str
    cron_expr: str
    task: Callable
    enabled: bool = True
    last_run: float = 0.0
    run_count: int = 0
