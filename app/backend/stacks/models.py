from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class StackDefinition:
    id: str
    name: str
    cwd: Path
    repo_url: str = ""
    compose_file: str = "compose.yaml"
    branch: str = ""
    tags: list[str] = field(default_factory=list)
    direct_url: str = ""
    traefik_url: str = ""
    notes: str = ""
