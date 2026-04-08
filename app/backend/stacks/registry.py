import json
from pathlib import Path
from typing import Optional

from ..settings.database import connect_database, ensure_database
from .models import StackDefinition


class RegistryError(Exception):
    pass


class StackRegistry:
    def __init__(self, database_path: Path, seed_path: Path, stack_root: Optional[Path] = None):
        self._database_path = database_path
        self._seed_path = seed_path
        self._stack_root = stack_root.resolve() if stack_root else None
        ensure_database(self._database_path)
        self._seed_if_empty()

    def load(self) -> list[StackDefinition]:
        with connect_database(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, name, cwd, repo_url, compose_file, branch, tags_json, direct_url, traefik_url, notes
                FROM stacks
                ORDER BY id
                """
            ).fetchall()
        stacks = [self._row_to_stack(row) for row in rows]
        for stack in stacks:
            self._validate_path(stack.cwd)
        return stacks

    def get(self, stack_id: str) -> StackDefinition:
        with connect_database(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT id, name, cwd, repo_url, compose_file, branch, tags_json, direct_url, traefik_url, notes
                FROM stacks
                WHERE id = ?
                """,
                (stack_id,),
            ).fetchone()
        if row is None:
            raise RegistryError(f"Unknown stack id: {stack_id}")
        stack = self._row_to_stack(row)
        self._validate_path(stack.cwd)
        return stack

    def upsert(self, payload: dict) -> StackDefinition:
        stack = self._coerce_payload(payload)
        self._validate_path(stack.cwd)
        with connect_database(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO stacks (id, name, cwd, repo_url, compose_file, branch, tags_json, direct_url, traefik_url, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    cwd = excluded.cwd,
                    repo_url = excluded.repo_url,
                    compose_file = excluded.compose_file,
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
                    stack.branch,
                    json.dumps(stack.tags, ensure_ascii=False),
                    stack.direct_url,
                    stack.traefik_url,
                    stack.notes,
                ),
            )
        return stack

    def delete(self, stack_id: str) -> None:
        with connect_database(self._database_path) as connection:
            cursor = connection.execute("DELETE FROM stacks WHERE id = ?", (stack_id.strip(),))
        if cursor.rowcount == 0:
            raise RegistryError(f"Unknown stack id: {stack_id}")

    def _seed_if_empty(self) -> None:
        with connect_database(self._database_path) as connection:
            count = connection.execute("SELECT COUNT(*) AS count FROM stacks").fetchone()["count"]
            if count:
                return
            if not self._seed_path.exists():
                return
            payload = self._load_seed_payload()
            for item in payload.get("stacks", []):
                stack = self._coerce_payload(item)
                self._validate_path(stack.cwd)
                connection.execute(
                    """
                    INSERT INTO stacks (id, name, cwd, repo_url, compose_file, branch, tags_json, direct_url, traefik_url, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stack.id,
                        stack.name,
                        str(stack.cwd),
                        stack.repo_url,
                        stack.compose_file,
                        stack.branch,
                        json.dumps(stack.tags, ensure_ascii=False),
                        stack.direct_url,
                        stack.traefik_url,
                        stack.notes,
                    ),
                )

    def _load_seed_payload(self) -> dict:
        suffix = self._seed_path.suffix.lower()
        if suffix == ".json":
            return json.loads(self._seed_path.read_text(encoding="utf-8"))
        return self._parse_simple_yaml(self._seed_path.read_text(encoding="utf-8"))

    def _coerce_payload(self, payload: dict) -> StackDefinition:
        stack_id = str(payload.get("id") or "").strip()
        if not stack_id:
            raise RegistryError("Stack id is required.")
        cwd_raw = str(payload.get("cwd") or "").strip()
        if not cwd_raw:
            raise RegistryError("cwd is required.")
        compose_file = str(payload.get("compose_file") or "compose.yaml").strip() or "compose.yaml"
        tags = payload.get("tags") or []
        if isinstance(tags, str):
            tags = [part.strip() for part in tags.split(",") if part.strip()]
        resolved_cwd = Path(cwd_raw).expanduser().resolve()
        return StackDefinition(
            id=stack_id,
            name=str(payload.get("name") or stack_id).strip() or stack_id,
            cwd=resolved_cwd,
            repo_url=str(payload.get("repo_url") or "").strip(),
            compose_file=compose_file,
            branch=str(payload.get("branch") or "").strip(),
            tags=[str(tag).strip() for tag in tags if str(tag).strip()],
            direct_url=str(payload.get("direct_url") or "").strip(),
            traefik_url=str(payload.get("traefik_url") or "").strip(),
            notes=str(payload.get("notes") or "").strip(),
        )

    def _validate_path(self, cwd: Path) -> None:
        if self._stack_root and self._stack_root not in cwd.parents and cwd != self._stack_root:
            raise RegistryError(f"Stack path escapes STACK_ROOT: {cwd}")

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
            branch=str(row["branch"]),
            tags=[str(tag) for tag in tags],
            direct_url=str(row["direct_url"]),
            traefik_url=str(row["traefik_url"]),
            notes=str(row["notes"]),
        )

    @staticmethod
    def _parse_simple_yaml(text: str) -> dict:
        lines = []
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            lines.append(line)
        if not lines or lines[0].strip() != "stacks:":
            raise RegistryError("Registry YAML must start with 'stacks:'.")

        items = []
        index = 1
        while index < len(lines):
            line = lines[index]
            indent = len(line) - len(line.lstrip(" "))
            content = line.strip()
            if indent != 2 or not content.startswith("- "):
                raise RegistryError(f"Unexpected registry line: {line}")
            item = {}
            inline = content[2:].strip()
            if inline:
                key, value = StackRegistry._split_key_value(inline)
                item[key] = StackRegistry._parse_scalar(value)
            index += 1
            while index < len(lines):
                nested_line = lines[index]
                nested_indent = len(nested_line) - len(nested_line.lstrip(" "))
                nested_content = nested_line.strip()
                if nested_indent <= 2:
                    break
                if nested_indent != 4:
                    raise RegistryError(f"Unsupported indentation in registry: {nested_line}")
                key, value = StackRegistry._split_key_value(nested_content)
                if value == "":
                    index += 1
                    values = []
                    while index < len(lines):
                        value_line = lines[index]
                        value_indent = len(value_line) - len(value_line.lstrip(" "))
                        value_content = value_line.strip()
                        if value_indent <= 4:
                            break
                        if value_indent != 6 or not value_content.startswith("- "):
                            raise RegistryError(f"Unsupported nested list in registry: {value_line}")
                        values.append(StackRegistry._parse_scalar(value_content[2:]))
                        index += 1
                    item[key] = values
                    continue
                item[key] = StackRegistry._parse_scalar(value)
                index += 1
            items.append(item)
        return {"stacks": items}

    @staticmethod
    def _split_key_value(raw: str) -> tuple[str, str]:
        if ":" not in raw:
            raise RegistryError(f"Invalid key/value line: {raw}")
        key, value = raw.split(":", 1)
        return key.strip(), value.strip()

    @staticmethod
    def _parse_scalar(raw: str):
        value = raw.strip()
        if not value:
            return ""
        if value.startswith(("'", '"')) and value.endswith(("'", '"')):
            return value[1:-1]
        return value
