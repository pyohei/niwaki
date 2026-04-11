import json
import re
from pathlib import Path
from typing import Optional

from ..settings.database import connect_database, ensure_database
from .models import StackDefinition


class RegistryError(Exception):
    pass


class StackRegistry:
    def __init__(self, database_path: Path, stack_root: Optional[Path] = None):
        self._database_path = database_path
        self._stack_root = stack_root.resolve() if stack_root else None
        ensure_database(self._database_path)

    def load(self) -> list[StackDefinition]:
        with connect_database(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, name, cwd, repo_url, compose_file, override_file, branch, tags_json, direct_url, traefik_url, notes
                FROM stacks
                ORDER BY id
                """
            ).fetchall()
        stacks = [self._row_to_stack(row) for row in rows]
        for stack in stacks:
            self._validate_path(stack.cwd)
            if stack.override_file:
                self._validate_path(Path(stack.override_file))
        return stacks

    def get(self, stack_id: str) -> StackDefinition:
        with connect_database(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT id, name, cwd, repo_url, compose_file, override_file, branch, tags_json, direct_url, traefik_url, notes
                FROM stacks
                WHERE id = ?
                """,
                (stack_id,),
            ).fetchone()
        if row is None:
            raise RegistryError(f"Unknown stack id: {stack_id}")
        stack = self._row_to_stack(row)
        self._validate_path(stack.cwd)
        if stack.override_file:
            self._validate_path(Path(stack.override_file))
        return stack

    def upsert(self, payload: dict) -> StackDefinition:
        stack = self._coerce_payload(payload)
        self._validate_path(stack.cwd)
        with connect_database(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO stacks (id, name, cwd, repo_url, compose_file, override_file, branch, tags_json, direct_url, traefik_url, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    cwd = excluded.cwd,
                    repo_url = excluded.repo_url,
                    compose_file = excluded.compose_file,
                    override_file = excluded.override_file,
                    branch = excluded.branch,
                    tags_json = excluded.tags_json,
                    direct_url = excluded.direct_url,
                    traefik_url = excluded.traefik_url,
                    notes = excluded.notes,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    stack.id,
                    stack.name,
                    str(stack.cwd),
                    stack.repo_url,
                    stack.compose_file,
                    stack.override_file,
                    stack.branch,
                    json.dumps(stack.tags, ensure_ascii=False),
                    stack.direct_url,
                    stack.traefik_url,
                    stack.notes,
                ),
            )
        self._ensure_generated_paths(stack)
        return stack

    def delete(self, stack_id: str) -> None:
        with connect_database(self._database_path) as connection:
            cursor = connection.execute("DELETE FROM stacks WHERE id = ?", (stack_id.strip(),))
        if cursor.rowcount == 0:
            raise RegistryError(f"Unknown stack id: {stack_id}")

    def _coerce_payload(self, payload: dict) -> StackDefinition:
        name = str(payload.get("name") or "").strip()
        stack_id = self._coerce_stack_id(str(payload.get("id") or "").strip(), name)
        existing = self._find_existing(stack_id)
        resolved_cwd = self._coerce_cwd(str(payload.get("cwd") or "").strip(), stack_id, existing)
        compose_file = str(payload.get("compose_file") or "compose.yaml").strip() or "compose.yaml"
        override_file = self._coerce_override_file(
            str(payload.get("override_file") or "").strip(),
            resolved_cwd,
            stack_id,
            existing,
        )
        if override_file:
            self._validate_path(Path(override_file))
        return StackDefinition(
            id=stack_id,
            name=name or (existing.name if existing else stack_id),
            cwd=resolved_cwd,
            repo_url=str(payload.get("repo_url") or (existing.repo_url if existing else "")).strip(),
            compose_file=compose_file,
            override_file=override_file,
            branch=str(payload.get("branch") or (existing.branch if existing else "")).strip(),
            tags=[],
            direct_url=existing.direct_url if existing else "",
            traefik_url=str(payload.get("traefik_url") or (existing.traefik_url if existing else "")).strip(),
            notes=str(payload.get("notes") or (existing.notes if existing else "")).strip(),
        )

    def _coerce_stack_id(self, value: str, name: str) -> str:
        if value:
            return value.strip()
        candidate = name
        candidate = re.sub(r"[\\/]+", "-", candidate.strip())
        candidate = re.sub(r"\s+", "-", candidate)
        candidate = candidate.lower()
        candidate = candidate.strip("-.")
        if not candidate:
            raise RegistryError("Stack name is required.")
        return candidate

    def _coerce_cwd(self, value: str, stack_id: str, existing: Optional[StackDefinition]) -> Path:
        if value:
            return Path(value).expanduser().resolve()
        if existing is not None:
            return existing.cwd.resolve()
        if self._stack_root is None:
            raise RegistryError("cwd is required when STACK_ROOT is not set.")
        if self._stack_root.name == "stacks":
            return (self._stack_root / stack_id).resolve()
        return (self._stack_root / "stacks" / stack_id).resolve()

    def _coerce_override_file(self, value: str, cwd: Path, stack_id: str, existing: Optional[StackDefinition]) -> str:
        if not value:
            if existing is not None and existing.override_file:
                return existing.override_file
            if self._stack_root is None:
                return ""
            return str((self._stack_root / "overrides" / f"{stack_id}.yaml").resolve())
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = cwd.expanduser().resolve() / path
        return str(path.resolve())

    @staticmethod
    def _default_override_contents(stack: StackDefinition) -> str:
        return (
            "# Auto-generated by Niwaki.\n"
            "# Add service-level overrides here.\n"
            "services: {}\n"
        )

    def _ensure_generated_paths(self, stack: StackDefinition) -> None:
        stack.cwd.parent.mkdir(parents=True, exist_ok=True)
        if not stack.override_file:
            return
        override_path = Path(stack.override_file)
        override_path.parent.mkdir(parents=True, exist_ok=True)
        if not override_path.exists():
            override_path.write_text(self._default_override_contents(stack), encoding="utf-8")

    def _validate_path(self, cwd: Path) -> None:
        if self._stack_root and self._stack_root not in cwd.parents and cwd != self._stack_root:
            raise RegistryError(f"Stack path escapes STACK_ROOT: {cwd}")

    def _find_existing(self, stack_id: str) -> Optional[StackDefinition]:
        with connect_database(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT id, name, cwd, repo_url, compose_file, override_file, branch, tags_json, direct_url, traefik_url, notes
                FROM stacks
                WHERE id = ?
                """,
                (stack_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_stack(row)

    @staticmethod
    def _row_to_stack(row) -> StackDefinition:
        raw_tags = row["tags_json"] or "[]"
        tags = json.loads(raw_tags)
        return StackDefinition(
            id=str(row["id"]),
            name=str(row["name"]),
            cwd=Path(str(row["cwd"])),
            repo_url=str(row["repo_url"]),
            compose_file=str(row["compose_file"]),
            override_file=str(row["override_file"] or ""),
            branch=str(row["branch"]),
            tags=[str(tag) for tag in tags],
            direct_url=str(row["direct_url"]),
            traefik_url=str(row["traefik_url"]),
            notes=str(row["notes"]),
        )
