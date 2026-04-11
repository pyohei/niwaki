import re
from typing import Any, Optional

from ...core.config import AppConfig
from ...docker.socket_client import DockerAPIClient


ALIAS_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9-]+)?$")
DBUS_SOCKET_HOST_PATH = "/var/run/dbus/system_bus_socket"


class MdnsService:
    def __init__(self, config: AppConfig, docker_api: DockerAPIClient):
        self._config = config
        self._docker_api = docker_api

    def list_aliases(self) -> list[dict[str, Any]]:
        containers = self._docker_api.list_containers_by_label(self._config.mdns_managed_label, "true")
        aliases = []
        for container in containers:
            labels = container.get("Labels") or {}
            aliases.append(
                {
                    "id": container.get("Id", ""),
                    "name": (container.get("Names") or [""])[0].lstrip("/"),
                    "alias": labels.get(self._config.mdns_alias_label, ""),
                    "target_ip": labels.get(self._config.mdns_target_ip_label, ""),
                    "state": container.get("State", ""),
                    "status": container.get("Status", ""),
                    "image": container.get("Image", ""),
                }
            )
        aliases.sort(key=lambda item: item["alias"])
        return aliases

    def create_alias(self, alias: str, target_ip: Optional[str] = None) -> dict[str, Any]:
        normalized_alias = self.normalize_alias(alias)
        resolved_target_ip = (target_ip or self._config.mdns_target_ip).strip()
        if not resolved_target_ip:
            raise ValueError("MDNS_TARGET_IP is required.")
        if any(item["alias"] == normalized_alias for item in self.list_aliases()):
            raise ValueError(f"Alias already exists: {normalized_alias}")
        name = self._container_name(normalized_alias)
        existing = self._find_container_by_name(name)
        if existing:
            if not self._is_managed(existing):
                raise ValueError(f"Container name is already in use: {name}")
            self._docker_api.delete_container(existing.get("Id") or name)
        config = {
            "Image": self._config.mdns_publish_image,
            "Cmd": ["publisher"],
            "Env": [
                f"MDNS_ALIAS={normalized_alias}",
                f"MDNS_TARGET_IP={resolved_target_ip}",
                "DBUS_SYSTEM_BUS_ADDRESS=unix:path=/var/run/dbus/system_bus_socket",
            ],
            "Labels": {
                self._config.mdns_managed_label: "true",
                self._config.mdns_alias_label: normalized_alias,
                self._config.mdns_target_ip_label: resolved_target_ip,
            },
            "HostConfig": {
                "Binds": [f"{DBUS_SOCKET_HOST_PATH}:{DBUS_SOCKET_HOST_PATH}"],
                "NetworkMode": "none",
                "RestartPolicy": {"Name": "unless-stopped"},
            },
        }
        self._docker_api.create_container(name, config)
        self._docker_api.start_container(name)
        return {
            "alias": normalized_alias,
            "target_ip": resolved_target_ip,
        }

    def ensure_alias(self, alias: str, target_ip: Optional[str] = None) -> dict[str, Any]:
        normalized_alias = self.normalize_alias(alias)
        resolved_target_ip = (target_ip or self._config.mdns_target_ip).strip()
        if not resolved_target_ip:
            raise ValueError("MDNS_TARGET_IP is required.")
        name = self._container_name(normalized_alias)
        for item in self.list_aliases():
            if item["alias"] != normalized_alias:
                continue
            if item["target_ip"] and item["target_ip"] != resolved_target_ip:
                self._docker_api.delete_container(item["id"])
                return self.create_alias(normalized_alias, resolved_target_ip)
            if item["state"] != "running":
                self._docker_api.start_container(item["name"] or item["id"])
            return {
                "alias": normalized_alias,
                "target_ip": resolved_target_ip,
            }
        existing = self._find_container_by_name(name)
        if existing:
            if not self._is_managed(existing):
                raise ValueError(f"Container name is already in use: {name}")
            labels = existing.get("Labels") or {}
            existing_alias = labels.get(self._config.mdns_alias_label, "")
            if existing_alias and existing_alias != normalized_alias:
                raise ValueError(f"Container name is already reserved for another alias: {existing_alias}")
            self._docker_api.delete_container(existing.get("Id") or name)
        return self.create_alias(normalized_alias, resolved_target_ip)

    def delete_alias(self, alias: str) -> None:
        normalized_alias = self.normalize_alias(alias)
        for item in self.list_aliases():
            if item["alias"] == normalized_alias:
                self._docker_api.delete_container(item["id"])
                return
        raise ValueError(f"Unknown alias: {normalized_alias}")

    def normalize_alias(self, raw_value: str) -> str:
        value = raw_value.strip().lower()
        if not value:
            raise ValueError("Alias is required.")
        if "." not in value:
            value = f"{value}.{self._config.mdns_default_domain}"
        if not ALIAS_NAME_RE.fullmatch(value):
            raise ValueError("Alias must be a single hostname like niwaki.local.")
        return value

    @staticmethod
    def _container_name(alias: str) -> str:
        return "mdns-alias-" + alias.split(".", 1)[0]

    def _find_container_by_name(self, name: str) -> Optional[dict[str, Any]]:
        containers = self._docker_api.list_containers_by_name(name)
        for container in containers:
            names = container.get("Names") or []
            if any(item.lstrip("/") == name for item in names):
                return container
        return None

    def _is_managed(self, container: dict[str, Any]) -> bool:
        labels = container.get("Labels") or {}
        return labels.get(self._config.mdns_managed_label) == "true"
