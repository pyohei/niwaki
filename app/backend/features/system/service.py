import shlex
import uuid
from pathlib import Path

from ...core.config import AppConfig
from ...core.process import run_command
from ...docker.socket_client import DockerAPIClient
from ...stacks.models import StackDefinition
from ...stacks.registry import StackRegistry


SYSTEM_JOB_LABEL = "io.niwaki.system-job"
SYSTEM_JOB_NAME_LABEL = "io.niwaki.system-job-name"
SYSTEM_JOB_ACTION_LABEL = "io.niwaki.system-job-action"


class SystemService:
    def __init__(self, config: AppConfig, registry: StackRegistry, docker_api: DockerAPIClient):
        self._config = config
        self._registry = registry
        self._docker_api = docker_api

    def get_status(self) -> dict:
        runtime_root = self._config.runtime_root
        jobs = []
        for container in self._docker_api.list_containers_by_label(SYSTEM_JOB_LABEL, "true"):
            labels = container.get("Labels") or {}
            jobs.append(
                {
                    "id": container.get("Id", ""),
                    "name": labels.get(SYSTEM_JOB_NAME_LABEL)
                    or (container.get("Names") or [""])[0].lstrip("/"),
                    "action": labels.get(SYSTEM_JOB_ACTION_LABEL, ""),
                    "state": container.get("State", ""),
                    "status": container.get("Status", ""),
                }
            )
        jobs.sort(key=lambda item: item["name"], reverse=True)
        return {
            "runtime_root": str(runtime_root) if runtime_root else "",
            "stack_root": str(self._config.stack_root) if self._config.stack_root else "",
            "compose_file": str(runtime_root / "compose.yaml") if runtime_root else "",
            "available": bool(runtime_root),
            "jobs": jobs,
        }

    def launch_runtime_action(self, action: str, *, rolling_update: bool) -> dict:
        runtime_root = self._config.runtime_root
        if runtime_root is None:
            raise ValueError("NIWAKI_RUNTIME_ROOT or STACK_ROOT is required for system actions.")
        if action not in {"restart", "update"}:
            raise ValueError(f"Unsupported system action: {action}")

        stacks = self._registry.load() if rolling_update else []
        for stack in stacks:
            self._validate_stack_access(stack, runtime_root)

        job_name = f"niwaki-system-{action}-{uuid.uuid4().hex[:8]}"
        script = self._build_job_script(action, runtime_root, stacks)
        command = [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            job_name,
            "--label",
            f"{SYSTEM_JOB_LABEL}=true",
            "--label",
            f"{SYSTEM_JOB_NAME_LABEL}={job_name}",
            "--label",
            f"{SYSTEM_JOB_ACTION_LABEL}={action}",
            "-v",
            f"{self._config.docker_socket_path}:{self._config.docker_socket_path}",
            "-v",
            f"{runtime_root}:{runtime_root}",
            "-w",
            str(runtime_root),
            self._config.runtime_image,
            "/bin/sh",
            "-lc",
            script,
        ]
        result = run_command(command, cwd=str(self._config.project_root))
        if result.exit_code != 0:
            raise RuntimeError(result.output)
        container_id = result.stdout.strip()
        return {
            "accepted": True,
            "action": action,
            "rolling_update": rolling_update,
            "job_name": job_name,
            "container_id": container_id,
            "runtime_root": str(runtime_root),
        }

    @staticmethod
    def _validate_stack_access(stack: StackDefinition, runtime_root: Path) -> None:
        runtime_root = runtime_root.resolve()
        cwd = stack.cwd.resolve()
        if cwd != runtime_root and runtime_root not in cwd.parents:
            raise ValueError(f"Stack is outside runtime root: {stack.id}")
        if stack.override_file:
            override_path = Path(stack.override_file).resolve()
            if override_path != runtime_root and runtime_root not in override_path.parents:
                raise ValueError(f"Override file is outside runtime root: {stack.id}")

    def _build_job_script(self, action: str, runtime_root: Path, stacks: list[StackDefinition]) -> str:
        lines = ["set -eu"]
        if stacks:
            for stack in stacks:
                lines.extend(self._stack_deploy_lines(stack))
        lines.extend(self._runtime_lines(action, runtime_root))
        return "\n".join(lines)

    def _stack_deploy_lines(self, stack: StackDefinition) -> list[str]:
        command = self._compose_command(stack)
        cwd = shlex.quote(str(stack.cwd))
        lines = [
            f"echo '==> deploy stack: {stack.id}'",
            f"cd {cwd}",
            "if [ -d .git ]; then git fetch --prune && git pull --ff-only; fi",
            f"{command} pull",
            f"{command} up -d",
        ]
        return lines

    @staticmethod
    def _runtime_lines(action: str, runtime_root: Path) -> list[str]:
        root = shlex.quote(str(runtime_root))
        lines = [
            "echo '==> update runtime: niwaki'",
            f"cd {root}",
        ]
        if action == "update":
            lines.append("if [ -d .git ]; then git fetch --prune && git pull --ff-only; fi")
        lines.append("docker compose up -d --build")
        return lines

    @staticmethod
    def _compose_command(stack: StackDefinition) -> str:
        parts = ["docker", "compose"]
        for compose_file in stack.compose_files():
            parts.extend(["-f", compose_file])
        return " ".join(shlex.quote(part) for part in parts)
