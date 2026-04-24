from ..config import *

class ThermalMonitor:
    TIERS = [(0, 45, "normal", 1.0), (45, 55, "warn", 0.8), (55, 70, "throttle", 0.5), (70, 100, "emergency", 0.0)]
    def __init__(self):
        self.last_temp = 35.0; self.last_check = 0.0

    def _read_temp(self) -> float:
        try:
            for zone in range(0, 20):
                path = f"/sys/class/thermal/thermal_zone{zone}/temp"
                if os.path.exists(path):
                    with open(path) as f:
                        val = f.read().strip()
                        t = int(val) / 1000.0 if len(val) > 3 else int(val)
                        if 20 <= t <= 120: return t
        except Exception:
            pass
        return self.last_temp

    def check(self) -> Dict:
        temp = self._read_temp(); self.last_temp = temp; self.last_check = time.time()
        for lo, hi, name, factor in self.TIERS:
            if lo <= temp < hi:
                return {"temp_c": round(temp, 1), "tier": name, "throttle_factor": factor, "halt": name == "emergency"}
        return {"temp_c": round(temp, 1), "tier": "unknown", "throttle_factor": 1.0, "halt": False}

    def should_halt(self) -> bool:
        return self.check()["halt"]

    def report(self) -> Dict:
        return self.check()


