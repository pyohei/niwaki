from ...git.credentials import GitCredentialStore
from ...stacks.registry import StackRegistry


class SettingsService:
    def __init__(self, registry: StackRegistry, credential_store: GitCredentialStore):
        self._registry = registry
        self._credential_store = credential_store

    def list_stack_records(self) -> list[dict]:
        return [self._serialize_stack(stack) for stack in self._registry.load()]

    def upsert_stack(self, payload: dict) -> dict:
        stack = self._registry.upsert(payload)
        return self._serialize_stack(stack)

    def delete_stack(self, stack_id: str) -> None:
        self._registry.delete(stack_id)

    def get_git_credential(self) -> dict:
        credential = self._credential_store.get()
        return credential.to_public_dict() if credential is not None else {}

    def upsert_git_credential(self, payload: dict) -> dict:
        credential = self._credential_store.upsert(
            str(payload.get("username") or ""),
            str(payload.get("secret") or ""),
        )
        return credential.to_public_dict()

    def delete_git_credential(self) -> None:
        self._credential_store.delete()

    @staticmethod
    def _serialize_stack(stack) -> dict:
        return {
            "id": stack.id,
            "name": stack.name,
            "cwd": str(stack.cwd),
            "repo_url": stack.repo_url,
            "compose_file": stack.compose_file,
            "branch": stack.branch,
            "tags": stack.tags,
            "direct_url": stack.direct_url,
            "traefik_url": stack.traefik_url,
            "notes": stack.notes,
        }
