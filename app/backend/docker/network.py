from datetime import datetime, timezone

from ..core.process import CommandResult, run_command


class DockerNetworkService:
    def ensure_network(self, name: str, *, cwd: str) -> CommandResult:
        check = run_command(
            ["docker", "network", "ls", "--filter", f"name=^{name}$", "--format", "{{.Name}}"],
            cwd=cwd,
        )
        if check.exit_code != 0:
            return check
        if any(line.strip() == name for line in check.stdout.splitlines()):
            return self._completed_result(
                ["docker", "network", "ls", "--filter", f"name=^{name}$", "--format", "{{.Name}}"],
                cwd,
                stdout=f"Network already exists: {name}\n",
            )
        return run_command(["docker", "network", "create", name], cwd=cwd)

    @staticmethod
    def _completed_result(command: list[str], cwd: str, *, stdout: str = "", stderr: str = "") -> CommandResult:
        timestamp = datetime.now(timezone.utc).isoformat()
        return CommandResult(
            command=command,
            cwd=cwd,
            exit_code=0,
            stdout=stdout,
            stderr=stderr,
            started_at=timestamp,
            completed_at=timestamp,
            duration_ms=0,
        )
