from ..config import *

class PlatformDetector:
    MODEL_MAP = {
        "termux_high": "qwen3:4b", "termux_low": "llama3.2:1b", "ish": "gemma3:1b",
        "wsl": "qwen3:7b", "linux": "qwen3:7b", "macos": "gemma4:9b",
        "windows": "qwen3:7b", "unknown": "llama3.2:1b"
    }

    def detect(self) -> Dict:
        env = os.environ; uname = __import__("platform").uname()
        result = {"platform": "unknown", "model": "llama3.2:1b", "details": {}}
        if env.get("PREFIX") and "Android" in (env.get("TERMUX_VERSION", "") or uname.system):
            try:
                with open("/proc/meminfo") as f:
                    total_gb = int(f.readline().split()[1]) / (1024 * 1024)
                    result["platform"] = "termux_high" if total_gb >= 6 else "termux_low"
                    result["details"]["ram_gb"] = round(total_gb, 1)
            except Exception:
                result["platform"] = "termux_low"
            result["model"] = self.MODEL_MAP[result["platform"]]
            return result
        if os.path.exists("/proc/ish"):
            result["platform"] = "ish"; result["model"] = self.MODEL_MAP["ish"]; return result
        if env.get("WSL_DISTRO_NAME") or env.get("WSLENV"):
            result["platform"] = "wsl"; result["model"] = self.MODEL_MAP["wsl"]; return result
        if sys.platform == "darwin":
            result["platform"] = "macos"; result["model"] = self.MODEL_MAP["macos"]; return result
        if sys.platform.startswith("linux"):
            result["platform"] = "linux"; result["model"] = self.MODEL_MAP["linux"]; return result
        if sys.platform == "win32":
            result["platform"] = "windows"; result["model"] = self.MODEL_MAP["windows"]; return result
        return result

    def report(self) -> Dict:
        d = self.detect(); d["python"] = sys.version; d["machine"] = __import__("platform").machine(); return d


