import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Optional, Sequence


def tail_lines(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    lines = text.splitlines()
    if len(lines) <= limit:
        return text
    return "\n".join(lines[-limit:])


@dataclass
class CommandResult:
    command: list[str]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    started_at: str
    completed_at: str
    duration_ms: int

    @property
    def output(self) -> str:
        if self.stderr.strip():
            return f"{self.stdout}\n{self.stderr}".strip()
        return self.stdout.strip()

    def to_dict(self, line_limit: Optional[int] = None) -> dict:
        output = self.output
        if line_limit is not None:
            output = tail_lines(output, line_limit)
        return {
            "command": self.command,
            "command_text": " ".join(shlex.quote(part) for part in self.command),
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "output": output,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
        }


def run_command(
    command: Sequence[str],
    *,
    cwd: str,
    env: Optional[dict[str, str]] = None,
    timeout: int = 900,
) -> CommandResult:
    started_at_dt = datetime.now(timezone.utc)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
            timeout=timeout,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except FileNotFoundError as exc:
        exit_code = 127
        stdout = ""
        stderr = str(exc)
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + "\nCommand timed out."
    duration_ms = int((time.monotonic() - started) * 1000)
    completed_at_dt = datetime.now(timezone.utc)
    return CommandResult(
        command=list(command),
        cwd=cwd,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        started_at=started_at_dt.isoformat(),
        completed_at=completed_at_dt.isoformat(),
        duration_ms=duration_ms,
    )
