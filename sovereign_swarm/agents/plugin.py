"""Dynamic agent plugin loader — discover and auto-register modules."""
from ..config import *
import importlib.util, pathlib

class PluginLoader:
    def __init__(self, plugin_dir: Optional[Path] = None):
        self.plugin_dir = plugin_dir or (DATA_DIR / "plugins")
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.loaded: Dict[str, Any] = {}

    def discover(self) -> List[Path]:
        return sorted(self.plugin_dir.glob("*.py"))

    def load(self, path: Path) -> Optional[Any]:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if not spec or not spec.loader: return None
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            self.loaded[path.stem] = mod
            return mod
        except Exception as e:
            print(f"[plugin] Failed to load {path}: {e}")
            return None

    def load_all(self) -> Dict[str, Any]:
        for p in self.discover():
            self.load(p)
        return self.loaded

    def register_agents(self, meta_orchestrator, profile_cls) -> int:
        """Auto-register agents from plugins with a make_agent() factory."""
        count = 0
        for name, mod in self.loaded.items():
            factory = getattr(mod, "make_agent", None)
            if callable(factory):
                try:
                    agent = factory()
                    if isinstance(agent, dict):
                        profile = profile_cls(**agent)
                        meta_orchestrator.register(profile)
                        count += 1
                except Exception as e:
                    print(f"[plugin] Factory failed for {name}: {e}")
        return count

    def report(self) -> Dict:
        return {"plugin_dir": str(self.plugin_dir), "discovered": len(self.discover()), "loaded": len(self.loaded), "modules": list(self.loaded.keys())}
