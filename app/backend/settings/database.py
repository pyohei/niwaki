import sqlite3
from pathlib import Path


def connect_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_database(path: Path) -> None:
    with connect_database(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS stacks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                cwd TEXT NOT NULL,
                repo_url TEXT NOT NULL DEFAULT '',
                compose_file TEXT NOT NULL,
                branch TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                direct_url TEXT NOT NULL DEFAULT '',
                traefik_url TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS git_credentials (
                stack_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                secret TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (stack_id) REFERENCES stacks(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS system_git_credentials (
                slot TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                secret TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_records (
                id TEXT PRIMARY KEY,
                stack_id TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL DEFAULT '',
                success INTEGER NOT NULL DEFAULT 0,
                record_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_records_started_at
            ON audit_records(started_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_records_stack_started_at
            ON audit_records(stack_id, started_at DESC)
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(stacks)").fetchall()
        }
        if "repo_url" not in columns:
            connection.execute("ALTER TABLE stacks ADD COLUMN repo_url TEXT NOT NULL DEFAULT ''")
