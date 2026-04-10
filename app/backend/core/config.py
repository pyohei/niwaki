import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..auth.basic import AuthConfig


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str, default: str, project_root: Path) -> Path:
    raw = os.environ.get(name, default)
    path = Path(raw)
    if path.is_absolute():
        return path
    return project_root / path


def _normalize_base_path(value: str) -> str:
    raw = value.strip()
    if not raw or raw == "/":
        return ""
    normalized = "/" + raw.strip("/")
    return normalized


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    frontend_root: Path
    host: str
    port: int
    base_url: str
    base_path: str
    auth: AuthConfig
    settings_db_path: Path
    stack_root: Optional[Path]
    git_default_branch: str
    git_pull_flags: tuple[str, ...]
    command_log_retention_days: int
    command_output_max_lines: int
    audit_log_path: Path
    docker_socket_path: str
    docker_api_version: str
    mdns_enabled: bool
    mdns_default_domain: str
    mdns_publish_image: str
    mdns_target_ip: str
    mdns_managed_label: str
    mdns_alias_label: str
    mdns_target_ip_label: str


def load_config() -> AppConfig:
    project_root = Path(__file__).resolve().parents[3]
    _load_dotenv(project_root / ".env")

    password = os.environ.get("ADMIN_PASSWORD", "")
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "")
    if not password and not password_hash:
        raise RuntimeError("Either ADMIN_PASSWORD or ADMIN_PASSWORD_HASH must be configured.")

    stack_root = os.environ.get("STACK_ROOT")

    return AppConfig(
        project_root=project_root,
        frontend_root=project_root / "app" / "frontend",
        host=os.environ.get("APP_HOST", "0.0.0.0"),
        port=int(os.environ.get("APP_PORT", "8787")),
        base_url=os.environ.get("APP_BASE_URL", "http://raspberrypi.local:8787"),
        base_path=_normalize_base_path(os.environ.get("APP_BASE_PATH", "")),
        auth=AuthConfig(
            username=os.environ.get("ADMIN_USERNAME", "admin"),
            password=password,
            password_hash=password_hash,
        ),
        settings_db_path=_env_path("SETTINGS_DB_PATH", "data/niwaki.db", project_root),
        stack_root=Path(stack_root) if stack_root else None,
        git_default_branch=os.environ.get("GIT_DEFAULT_BRANCH", "main"),
        git_pull_flags=tuple(
            flag for flag in os.environ.get("GIT_PULL_FLAGS", "--ff-only").split(" ") if flag
        ),
        command_log_retention_days=int(os.environ.get("COMMAND_LOG_RETENTION_DAYS", "30")),
        command_output_max_lines=int(os.environ.get("COMMAND_OUTPUT_MAX_LINES", "200")),
        audit_log_path=_env_path("AUDIT_LOG_PATH", "data/command-history.jsonl", project_root),
        docker_socket_path=os.environ.get("DOCKER_SOCKET_PATH", "/var/run/docker.sock"),
        docker_api_version=os.environ.get("DOCKER_API_VERSION", "v1.41"),
        mdns_enabled=_env_bool("MDNS_ENABLED", True),
        mdns_default_domain=os.environ.get("MDNS_DEFAULT_DOMAIN", "local"),
        mdns_publish_image=os.environ.get("MDNS_PUBLISH_IMAGE", "niwaki:local"),
        mdns_target_ip=os.environ.get("MDNS_TARGET_IP", ""),
        mdns_managed_label=os.environ.get("MDNS_MANAGED_LABEL", "io.mdns-admin.managed"),
        mdns_alias_label=os.environ.get("MDNS_ALIAS_LABEL", "io.mdns-admin.alias"),
        mdns_target_ip_label=os.environ.get("MDNS_TARGET_IP_LABEL", "io.mdns-admin.target-ip"),
    )
