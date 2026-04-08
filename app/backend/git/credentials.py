from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..settings.database import connect_database, ensure_database


@dataclass(frozen=True)
class GitCredential:
    username: str
    secret: str
    updated_at: str

    def to_public_dict(self) -> dict:
        return {
            "username": self.username,
            "has_secret": bool(self.secret),
            "updated_at": self.updated_at,
        }


class GitCredentialStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path
        ensure_database(self._database_path)

    def get(self) -> Optional[GitCredential]:
        with connect_database(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT username, secret, updated_at
                FROM system_git_credentials
                WHERE slot = 'default'
                """
            ).fetchone()
        if row is None:
            return None
        return self._row_to_credential(row)

    def upsert(self, username: str, secret: str) -> GitCredential:
        normalized_username = username.strip()
        if not normalized_username:
            raise ValueError("username is required.")

        existing = self.get()
        stored_secret = secret
        if not stored_secret and existing is not None:
            stored_secret = existing.secret
        if not stored_secret:
            raise ValueError("password or token is required.")

        with connect_database(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO system_git_credentials (slot, username, secret, updated_at)
                VALUES ('default', ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(slot) DO UPDATE SET
                    username = excluded.username,
                    secret = excluded.secret,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (normalized_username, stored_secret),
            )
            row = connection.execute(
                """
                SELECT username, secret, updated_at
                FROM system_git_credentials
                WHERE slot = 'default'
                """
            ).fetchone()
        return self._row_to_credential(row)

    def delete(self) -> None:
        with connect_database(self._database_path) as connection:
            connection.execute("DELETE FROM system_git_credentials WHERE slot = 'default'")

    @staticmethod
    def _row_to_credential(row) -> GitCredential:
        return GitCredential(
            username=str(row["username"]),
            secret=str(row["secret"]),
            updated_at=str(row["updated_at"]),
        )
