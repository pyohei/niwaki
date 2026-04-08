import json
from typing import Any

from ..core.process import CommandResult, run_command
from ..stacks.models import StackDefinition


class ComposeService:
    def __init__(self, output_line_limit: int):
        self._output_line_limit = output_line_limit

    def validate(self, stack: StackDefinition) -> CommandResult:
        return self._run(stack, "config")

    def pull(self, stack: StackDefinition) -> CommandResult:
        return self._run(stack, "pull")

    def up(self, stack: StackDefinition) -> CommandResult:
        return self._run(stack, "up", "-d")

    def down(self, stack: StackDefinition) -> CommandResult:
        return self._run(stack, "down")

    def restart(self, stack: StackDefinition) -> CommandResult:
        return self._run(stack, "restart")

    def logs(self, stack: StackDefinition, tail: int = 200) -> CommandResult:
        return self._run(stack, "logs", "--tail", str(tail), "--no-color")

    def ps(self, stack: StackDefinition) -> list[dict[str, Any]]:
        result = self._run(stack, "ps", "--all", "--format", "json")
        if result.exit_code != 0:
            raise RuntimeError(result.output)
        raw = result.stdout.strip()
        if not raw:
            return []
        if raw.startswith("["):
            return json.loads(raw)
        return [json.loads(line) for line in raw.splitlines() if line.strip()]

    def _run(self, stack: StackDefinition, *args: str) -> CommandResult:
        command = ["docker", "compose", "-f", stack.compose_file, *args]
        return run_command(command, cwd=str(stack.cwd))
