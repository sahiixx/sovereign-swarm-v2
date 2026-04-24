from ..config import *

class BatteryMonitor:
    MODES = ["normal", "saver", "critical", "plugged"]
    def __init__(self):
        self.mode = "normal"; self.level = 100; self.plugged = False

    def _read_android(self) -> Dict:
        try:
            import subprocess
            result = subprocess.run(["termux-battery-status"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return {"level": data.get("percentage", 100), "plugged": data.get("plugged", "UNPLUGGED") != "UNPLUGGED"}
        except Exception:
            pass
        try:
            with open("/sys/class/power_supply/battery/capacity") as f:
                level = int(f.read().strip())
            with open("/sys/class/power_supply/battery/status") as f:
                status = f.read().strip()
            return {"level": level, "plugged": status in ("Charging", "Full")}
        except Exception:
            return {"level": 100, "plugged": True}

    def _read_linux(self) -> Dict:
        try:
            for bat in ["BAT0", "BAT1"]:
                base = f"/sys/class/power_supply/{bat}"
                if os.path.exists(base):
                    with open(f"{base}/capacity") as f: level = int(f.read().strip())
                    with open(f"{base}/status") as f: status = f.read().strip()
                    return {"level": level, "plugged": status in ("Charging", "Full")}
        except Exception:
            pass
        return {"level": 100, "plugged": True}

    def refresh(self):
        data = self._read_android() if os.path.exists("/sys/class/power_supply/battery") else self._read_linux()
        self.level = data["level"]; self.plugged = data["plugged"]
        if self.plugged: self.mode = "plugged"
        elif self.level <= 10: self.mode = "critical"
        elif self.level <= 25: self.mode = "saver"
        else: self.mode = "normal"

    def should_throttle(self) -> bool:
        return self.mode in ("saver", "critical")

    def max_agents(self) -> int:
        return {"plugged": 16, "normal": 16, "saver": 8, "critical": 2}.get(self.mode, 16)

    def report(self) -> Dict:
        return {"level": self.level, "plugged": self.plugged, "mode": self.mode, "max_agents": self.max_agents(), "throttle": self.should_throttle()}


