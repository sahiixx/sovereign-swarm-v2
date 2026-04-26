"""RBAC — Role-based access control for the SAHIIXX ecosystem."""

from ..config import *


class RBACPermission(str, Enum):
    EXECUTE = "execute"
    KILL = "kill"
    EMERGENCY_ARM = "emergency_arm"
    ADMIN = "admin"
    AGENT_SPAWN = "agent_spawn"
    TOOL_USE = "tool_use"
    READ = "read"
    WRITE = "write"
    DELETE = "delete"


class RBACGuard:
    """Role-based access control with async-safe locks.

    Roles are permission sets. Identities are assigned to roles.
    """

    def __init__(self):
        self._roles: Dict[str, set[str]] = {}
        self._assignments: Dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    def add_role(self, role: str, permissions: set[RBACPermission]):
        self._roles[role] = {p.value for p in permissions}

    def assign_role(self, identity: str, role: str):
        if role not in self._roles:
            raise ValueError(f"Unknown role: {role}")
        self._assignments.setdefault(identity, set()).add(role)

    def check(self, identity: str, permission: RBACPermission) -> bool:
        roles = self._assignments.get(identity, set())
        target = permission.value
        for role in roles:
            if target in self._roles.get(role, set()):
                return True
        return False

    def require(self, identity: str, permission: RBACPermission):
        if not self.check(identity, permission):
            raise PermissionError(
                f"Identity '{identity}' lacks '{permission.value}'"
            )

    def get_roles(self, identity: str) -> list[str]:
        return list(self._assignments.get(identity, set()))
