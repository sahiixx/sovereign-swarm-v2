from ..config import *

class BackupManager:
    def __init__(self, data_dir: Path, backup_dir: Path = None):
        self.data_dir = Path(data_dir); self.backup_dir = Path(backup_dir) if backup_dir else self.data_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create(self, name: str = None) -> Dict:
        name = name or f"backup_{int(time.time())}"; backup_path = self.backup_dir / name; backup_path.mkdir(exist_ok=True)
        copied = [str(shutil.copy2(db_file, backup_path / db_file.name)) for db_file in self.data_dir.glob("*.db")]
        return {"name": name, "copied": copied, "timestamp": time.time()}

    def list_backups(self) -> List[str]:
        return [d.name for d in self.backup_dir.iterdir() if d.is_dir()]

    def restore(self, name: str) -> Dict:
        backup_path = self.backup_dir / name
        if not backup_path.exists(): return {"restored": False, "error": "backup_not_found"}
        restored = [str(shutil.copy2(db_file, self.data_dir / db_file.name)) for db_file in backup_path.glob("*.db")]
        return {"restored": True, "name": name, "files": restored}

    def report(self) -> Dict:
        return {"backup_dir": str(self.backup_dir), "backups": self.list_backups(), "data_dir": str(self.data_dir)}


