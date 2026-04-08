import os
import stat
import tempfile
from dataclasses import dataclass

from ..core.process import CommandResult, run_command
from .credentials import GitCredentialStore
from ..stacks.models import StackDefinition


@dataclass(frozen=True)
class GitInfo:
    available: bool
    branch: str
    commit: str
    dirty: bool

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "branch": self.branch,
            "commit": self.commit,
            "dirty": self.dirty,
        }


class GitService:
    def __init__(self, pull_flags: tuple[str, ...], credential_store: GitCredentialStore):
        self._pull_flags = pull_flags
        self._credential_store = credential_store

    def info(self, stack: StackDefinition) -> GitInfo:
        if not self._is_git_repo(stack):
            return GitInfo(available=False, branch="", commit="", dirty=False)
        branch = self._git(stack, "branch", "--show-current")
        commit = self._git(stack, "rev-parse", "--short", "HEAD")
        dirty = self._git(stack, "status", "--porcelain")
        return GitInfo(
            available=True,
            branch=branch.stdout.strip(),
            commit=commit.stdout.strip(),
            dirty=bool(dirty.stdout.strip()),
        )

    def fetch(self, stack: StackDefinition) -> CommandResult:
        return self._git(stack, "fetch", "--prune")

    def pull(self, stack: StackDefinition) -> CommandResult:
        return self._git(stack, "pull", *self._pull_flags)

    def clone(self, stack: StackDefinition) -> CommandResult:
        if not stack.repo_url:
            raise ValueError(f"repo_url is required for clone: {stack.id}")
        target_path = stack.cwd
        target_path.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone"]
        if stack.branch:
            command.extend(["--branch", stack.branch])
        command.extend([stack.repo_url, str(target_path)])
        return self._run_git_command(command, cwd=str(target_path.parent))

    def _is_git_repo(self, stack: StackDefinition) -> bool:
        result = self._git(stack, "rev-parse", "--is-inside-work-tree")
        return result.exit_code == 0 and result.stdout.strip() == "true"

    def _git(self, stack: StackDefinition, *args: str) -> CommandResult:
        return self._run_git_command(["git", "-C", str(stack.cwd), *args], cwd=str(stack.cwd))

    def _run_git_command(self, command: list[str], *, cwd: str) -> CommandResult:
        credential = self._credential_store.get()
        if credential is None:
            return run_command(command, cwd=cwd)

        askpass_path = self._create_askpass_script()
        env = {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": askpass_path,
            "NIWAKI_GIT_USERNAME": credential.username,
            "NIWAKI_GIT_PASSWORD": credential.secret,
        }
        try:
            return run_command(command, cwd=cwd, env=env)
        finally:
            try:
                os.remove(askpass_path)
            except OSError:
                pass

    @staticmethod
    def _create_askpass_script() -> str:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
            handle.write('case "$1" in\n')
            handle.write('  *sername*) printf "%s\\n" "$NIWAKI_GIT_USERNAME" ;;\n')
            handle.write('  *assword*) printf "%s\\n" "$NIWAKI_GIT_PASSWORD" ;;\n')
            handle.write('  *) printf "\\n" ;;\n')
            handle.write("esac\n")
        os.chmod(handle.name, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        return handle.name
