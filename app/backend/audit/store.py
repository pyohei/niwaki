import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from ..settings.database import connect_database, ensure_database


class AuditStore:
    def __init__(self, database_path: Path, retention_days: int, legacy_path: Optional[Path] = None):
        self._database_path = database_path
        self._retention_days = retention_days
        self._legacy_path = legacy_path
        self._lock = threading.Lock()
        ensure_database(self._database_path)
        self._import_legacy_file_if_needed()

    def append(self, record: dict[str, Any]) -> None:
        self._purge_locked()
        normalized = self._normalize_record(record)
        with self._lock:
            with connect_database(self._database_path) as connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO audit_records (
                        id,
                        stack_id,
                        started_at,
                        completed_at,
                        success,
                        record_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized["id"],
                        normalized.get("stack_id", ""),
                        normalized.get("started_at", ""),
                        normalized.get("completed_at", ""),
                        1 if normalized.get("success") else 0,
                        json.dumps(normalized, ensure_ascii=False),
                    ),
                )

    def list_recent(self, limit: int = 20, stack_id: Optional[str] = None) -> list[dict[str, Any]]:
        with self._lock:
            self._purge_locked()
            with connect_database(self._database_path) as connection:
                query = """
                    SELECT record_json
                    FROM audit_records
                """
                params: list[Any] = []
                if stack_id:
                    query += " WHERE stack_id = ?"
                    params.append(stack_id)
                query += " ORDER BY started_at DESC, created_at DESC LIMIT ?"
                params.append(limit)
                rows = connection.execute(query, params).fetchall()
        return [json.loads(str(row["record_json"])) for row in rows]

    def last_for_stack(self, stack_id: str) -> Optional[dict[str, Any]]:
        records = self.list_recent(limit=1, stack_id=stack_id)
        return records[0] if records else None

    def _purge_locked(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self._retention_days)).isoformat()
        with connect_database(self._database_path) as connection:
            connection.execute(
                """
                DELETE FROM audit_records
                WHERE started_at != '' AND started_at < ?
                """,
                (cutoff,),
            )

    def _import_legacy_file_if_needed(self) -> None:
        if self._legacy_path is None or not self._legacy_path.exists():
            return
        with self._lock:
            with connect_database(self._database_path) as connection:
                count = connection.execute("SELECT COUNT(*) AS count FROM audit_records").fetchone()["count"]
                if count:
                    return
                records = []
                for line in self._legacy_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    records.append(self._normalize_record(json.loads(line)))
                for record in records:
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO audit_records (
                            id,
                            stack_id,
                            started_at,
                            completed_at,
                            success,
                            record_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record["id"],
                            record.get("stack_id", ""),
                            record.get("started_at", ""),
                            record.get("completed_at", ""),
                            1 if record.get("success") else 0,
                            json.dumps(record, ensure_ascii=False),
                        ),
                    )

    @staticmethod
    def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(record)
        normalized.setdefault("id", "")
        normalized.setdefault("stack_id", "")
        normalized.setdefault("stack_name", "")
        normalized.setdefault("action", "")
        normalized.setdefault("started_at", "")
        normalized.setdefault("completed_at", "")
        normalized.setdefault("success", False)
        normalized.setdefault("steps", [])
        return normalized
