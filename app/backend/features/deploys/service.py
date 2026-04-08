import uuid
from typing import Callable

from ...audit.store import AuditStore
from ...core.process import CommandResult
from ...docker.compose import ComposeService
from ...git.service import GitService
from ...stacks.models import StackDefinition


class DeployService:
    def __init__(
        self,
        compose_service: ComposeService,
        git_service: GitService,
        audit_store: AuditStore,
        output_line_limit: int,
    ):
        self._compose = compose_service
        self._git = git_service
        self._audit = audit_store
        self._output_line_limit = output_line_limit

    def run_action(self, stack: StackDefinition, action: str) -> dict:
        actions: dict[str, list[tuple[str, Callable[[StackDefinition], CommandResult], bool]]] = {
            "clone": [("git clone", self._git.clone, False)],
            "validate": [("docker compose config", self._compose.validate, False)],
            "pull": [("docker compose pull", self._compose.pull, False)],
            "up": [("docker compose up -d", self._compose.up, False)],
            "restart": [("docker compose restart", self._compose.restart, False)],
            "down": [("docker compose down", self._compose.down, False)],
            "deploy": [
                ("git fetch", self._git.fetch, True),
                ("git pull --ff-only", self._git.pull, True),
                ("docker compose config", self._compose.validate, False),
                ("docker compose pull", self._compose.pull, False),
                ("docker compose up -d", self._compose.up, False),
            ],
        }
        if action not in actions:
            raise ValueError(f"Unsupported action: {action}")

        git_info = self._git.info(stack)
        record = {
            "id": str(uuid.uuid4()),
            "stack_id": stack.id,
            "stack_name": stack.name,
            "action": action,
            "started_at": "",
            "completed_at": "",
            "success": True,
            "steps": [],
        }

        for step_name, operation, requires_git in actions[action]:
            if record["started_at"] == "":
                record["started_at"] = _now()
            if requires_git and not git_info.available:
                record["steps"].append(
                    {
                        "name": step_name,
                        "state": "skipped",
                        "result": None,
                    }
                )
                continue
            result = operation(stack)
            record["steps"].append(
                {
                    "name": step_name,
                    "state": "success" if result.exit_code == 0 else "failed",
                    "result": result.to_dict(self._output_line_limit),
                }
            )
            record["completed_at"] = result.completed_at
            if result.exit_code != 0:
                record["success"] = False
                break

        if not record["completed_at"]:
            record["completed_at"] = _now()
        self._audit.append(record)
        return record


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
