from ..config import *

class AuditTrail:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir); self.data_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.data_dir / "audit.jsonl"; self.txt_path = self.data_dir / "audit.txt"

    def log(self, event: str, data: Dict[str, Any], agent_id: str = "system"):
        entry = {"timestamp": time.time(), "event": event, "agent_id": agent_id, "data": data}
        with open(self.jsonl_path, "a") as jf: jf.write(json.dumps(entry) + "\n")
        with open(self.txt_path, "a") as tf: tf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {agent_id} | {event} | {json.dumps(data)}\n")

    def read_jsonl(self, limit: int = 100) -> List[Dict]:
        if not self.jsonl_path.exists(): return []
        with open(self.jsonl_path) as f: lines = [json.loads(line) for line in f]
        return lines[-limit:]

    def export_report(self, scope: str = "today") -> Path:
        lines = self.read_jsonl(10000)
        if scope == "today":
            today = time.strftime("%Y-%m-%d")
            lines = [l for l in lines if time.strftime("%Y-%m-%d", time.localtime(l["timestamp"])) == today]
        report_path = self.data_dir / f"audit_report_{scope}_{int(time.time())}.json"
        with open(report_path, "w") as f: json.dump({"scope": scope, "entries": lines, "generated_at": time.time()}, f, indent=2)
        return report_path

    def report(self) -> Dict:
        return {"jsonl_path": str(self.jsonl_path), "txt_path": str(self.txt_path), "entries": sum(1 for _ in open(self.jsonl_path)) if self.jsonl_path.exists() else 0}


