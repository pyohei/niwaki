import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


class AuditStore:
    def __init__(self, path: Path, retention_days: int):
        self._path = path
        self._retention_days = retention_days
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        self._purge_locked()
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def list_recent(self, limit: int = 20, stack_id: Optional[str] = None) -> list[dict[str, Any]]:
        with self._lock:
            self._purge_locked()
            if not self._path.exists():
                return []
            records = []
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if stack_id and record.get("stack_id") != stack_id:
                    continue
                records.append(record)
        records.sort(key=lambda item: item.get("started_at", ""), reverse=True)
        return records[:limit]

    def last_for_stack(self, stack_id: str) -> Optional[dict[str, Any]]:
        records = self.list_recent(limit=1, stack_id=stack_id)
        return records[0] if records else None

    def _purge_locked(self) -> None:
        if not self._path.exists():
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
        kept = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            started_at = record.get("started_at")
            if not started_at:
                kept.append(record)
                continue
            try:
                timestamp = datetime.fromisoformat(started_at)
            except ValueError:
                kept.append(record)
                continue
            if timestamp >= cutoff:
                kept.append(record)
        self._path.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in kept) + ("\n" if kept else ""),
            encoding="utf-8",
        )
