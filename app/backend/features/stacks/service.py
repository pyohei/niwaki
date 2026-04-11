from ...audit.store import AuditStore
from ...docker.compose import ComposeService
from ...git.service import GitService
from ...stacks.models import StackDefinition
from ...stacks.registry import StackRegistry


class StackService:
    def __init__(self, registry: StackRegistry, compose_service: ComposeService, git_service: GitService, audit_store: AuditStore):
        self._registry = registry
        self._compose = compose_service
        self._git = git_service
        self._audit = audit_store

    def list_stacks(self) -> list[dict]:
        return [self._serialize_stack(stack) for stack in self._registry.load()]

    def get_stack(self, stack_id: str) -> dict:
        return self._serialize_stack(self._registry.get(stack_id), include_logs=False)

    def resolve(self, stack_id: str) -> StackDefinition:
        return self._registry.get(stack_id)

    def _serialize_stack(self, stack: StackDefinition, *, include_logs: bool = False) -> dict:
        git_info = self._git.info(stack).to_dict()
        containers = []
        compose_error = ""
        compose_services = []
        compose_services_error = ""
        try:
            containers = self._compose.ps(stack)
        except Exception as exc:
            compose_error = str(exc)
        try:
            compose_services = self._compose.discover_services(stack)
        except Exception as exc:
            compose_services_error = str(exc)
        last_action = self._audit.last_for_stack(stack.id)
        return {
            "id": stack.id,
            "name": stack.name,
            "cwd": str(stack.cwd),
            "repo_url": stack.repo_url,
            "compose_file": stack.compose_file,
            "override_file": stack.override_file,
            "branch": stack.branch,
            "tags": stack.tags,
            "direct_url": stack.direct_url,
            "traefik_url": stack.traefik_url,
            "notes": stack.notes,
            "git": git_info,
            "containers": containers,
            "container_count": len(containers),
            "status": _status_from_containers(containers, compose_error),
            "compose_error": compose_error,
            "compose_services": compose_services,
            "compose_services_error": compose_services_error,
            "last_action": last_action,
            "logs_included": include_logs,
        }


def _status_from_containers(containers: list[dict], compose_error: str) -> str:
    if compose_error:
        return "error"
    if not containers:
        return "empty"
    states = {str(item.get("State", "")).lower() for item in containers}
    if states == {"running"}:
        return "healthy"
    if "running" in states:
        return "degraded"
    return "stopped"
