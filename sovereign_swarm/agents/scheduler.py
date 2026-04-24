from ..config import *
from .job import ScheduledJob

class SwarmScheduler:
    def __init__(self, battery_client=None):
        self.jobs: Dict[str, ScheduledJob] = {}; self.battery = battery_client; self.running = False

    def add(self, name: str, cron_expr: str, task: Callable):
        self.jobs[name] = ScheduledJob(name, cron_expr, task)

    def remove(self, name: str):
        self.jobs.pop(name, None)

    def _should_run(self, job: ScheduledJob) -> bool:
        if not job.enabled: return False
        now = time.localtime(); parts = job.cron_expr.split()
        if parts[0].startswith("*/"):
            interval = int(parts[0].replace("*/", ""))
            return time.time() - job.last_run >= interval * 60
        elif len(parts) == 2:
            h, m = map(int, parts)
            return now.tm_hour == h and now.tm_min == m and time.time() - job.last_run >= 60
        return False

    async def loop(self):
        self.running = True
        while self.running:
            if self.battery and hasattr(self.battery, 'mode') and self.battery.mode in ("critical", "saver"):
                await asyncio.sleep(300); continue
            for job in list(self.jobs.values()):
                if self._should_run(job):
                    try:
                        if asyncio.iscoroutinefunction(job.task): await job.task()
                        else: job.task()
                        job.last_run = time.time(); job.run_count += 1
                    except Exception as e: print(f"[scheduler] Job {job.name} failed: {e}")
            await asyncio.sleep(60)

    def stop(self): self.running = False

    def report(self) -> Dict:
        return {name: {"enabled": j.enabled, "runs": j.run_count, "last_run": j.last_run} for name, j in self.jobs.items()}


