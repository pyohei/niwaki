from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class StackDefinition:
    id: str
    name: str
    cwd: Path
    repo_url: str = ""
    compose_file: str = "compose.yaml"
    override_file: str = ""
    branch: str = ""
    tags: list[str] = field(default_factory=list)
    direct_url: str = ""
    traefik_url: str = ""
    notes: str = ""

    def compose_files(self) -> tuple[str, ...]:
        files = [self.compose_file]
        if self.override_file:
            files.append(self.override_file)
        return tuple(files)
