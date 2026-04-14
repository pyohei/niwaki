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

    def discover_services(self, stack: StackDefinition) -> list[dict[str, Any]]:
        result = self._run(stack, "config", "--format", "json")
        if result.exit_code != 0:
            raise RuntimeError(result.output)
        raw = result.stdout.strip()
        if not raw:
            return []
        payload = json.loads(raw)
        services = []
        for name, config in (payload.get("services") or {}).items():
            published_ports: set[str] = set()
            exposed_ports: set[str] = set()
            network_names = sorted((config.get("networks") or {}).keys())
            for port in config.get("ports") or []:
                if isinstance(port, dict) and port.get("target"):
                    published_ports.add(str(port["target"]))
            for port in config.get("expose") or []:
                exposed_ports.add(str(port))
            ordered_ports = sorted(
                published_ports | exposed_ports,
                key=lambda value: int(value) if value.isdigit() else value,
            )
            preferred_ports = published_ports or exposed_ports
            services.append(
                {
                    "name": name,
                    "image": config.get("image", ""),
                    "ports": ordered_ports,
                    "published_ports": sorted(
                        published_ports,
                        key=lambda value: int(value) if value.isdigit() else value,
                    ),
                    "exposed_ports": sorted(
                        exposed_ports,
                        key=lambda value: int(value) if value.isdigit() else value,
                    ),
                    "preferred_port": sorted(
                        preferred_ports,
                        key=lambda value: int(value) if value.isdigit() else value,
                    )[0]
                    if preferred_ports
                    else "",
                    "has_published_ports": bool(published_ports),
                    "networks": network_names,
                }
            )
        services.sort(key=lambda item: item["name"])
        return services

    def _run(self, stack: StackDefinition, *args: str) -> CommandResult:
        command = ["docker", "compose"]
        for compose_file in stack.compose_files():
            command.extend(["-f", compose_file])
        command.extend(args)
        return run_command(command, cwd=str(stack.cwd))
