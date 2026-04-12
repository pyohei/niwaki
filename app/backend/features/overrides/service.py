import re
from pathlib import Path

from ...core.config import AppConfig
from ...docker.compose import ComposeService
from ...features.mdns.service import MdnsService
from ...stacks.models import StackDefinition
from ...stacks.registry import StackRegistry


class OverrideService:
    def __init__(
        self,
        config: AppConfig,
        registry: StackRegistry,
        compose_service: ComposeService,
        mdns_service: MdnsService,
    ):
        self._config = config
        self._registry = registry
        self._compose = compose_service
        self._mdns = mdns_service

    def generate_traefik_override(
        self,
        stack: StackDefinition,
        *,
        service_name: str,
        target_port: str,
        hostname: str,
        create_alias: bool,
    ) -> dict:
        discovered = self._compose.discover_services(stack)
        known_services = {item["name"] for item in discovered}
        if service_name not in known_services:
            raise ValueError(f"Unknown service: {service_name}")

        port = str(target_port or "").strip()
        port = self._normalize_port(target_port, field_name="Target port")

        normalized_host = self._normalize_hostname(hostname)
        route_name = self._route_name(stack.id, service_name)
        override_path = Path(stack.override_file)
        override_path.parent.mkdir(parents=True, exist_ok=True)
        override_path.write_text(
            self._render_traefik_override(service_name, port, normalized_host, route_name),
            encoding="utf-8",
        )

        alias_result = None
        if create_alias and self._config.mdns_enabled:
            alias_result = self._mdns.ensure_alias(normalized_host)

        updated = self._registry.upsert(
            {
                "id": stack.id,
                "name": stack.name,
                "cwd": str(stack.cwd),
                "repo_url": stack.repo_url,
                "compose_file": stack.compose_file,
                "override_file": str(override_path),
                "branch": stack.branch,
                "notes": stack.notes,
                "traefik_url": f"http://{normalized_host}/",
            }
        )

        return {
            "kind": "traefik",
            "override_file": str(override_path),
            "hostname": normalized_host,
            "service_name": service_name,
            "target_port": port,
            "traefik_url": updated.traefik_url,
            "alias": alias_result,
        }

    def generate_port_override(
        self,
        stack: StackDefinition,
        *,
        service_name: str,
        target_port: str,
        published_port: str,
    ) -> dict:
        discovered = self._compose.discover_services(stack)
        known_services = {item["name"] for item in discovered}
        if service_name not in known_services:
            raise ValueError(f"Unknown service: {service_name}")

        target = self._normalize_port(target_port, field_name="Target port")
        published = self._normalize_port(published_port, field_name="Published port")

        override_path = Path(stack.override_file)
        override_path.parent.mkdir(parents=True, exist_ok=True)
        override_path.write_text(
            self._render_port_override(service_name, published, target),
            encoding="utf-8",
        )

        self._registry.upsert(
            {
                "id": stack.id,
                "name": stack.name,
                "cwd": str(stack.cwd),
                "repo_url": stack.repo_url,
                "compose_file": stack.compose_file,
                "override_file": str(override_path),
                "branch": stack.branch,
                "notes": stack.notes,
                "traefik_url": "",
            }
        )

        return {
            "kind": "port",
            "override_file": str(override_path),
            "service_name": service_name,
            "target_port": target,
            "published_port": published,
        }

    def _normalize_hostname(self, value: str) -> str:
        hostname = value.strip().lower()
        if not hostname:
            raise ValueError("Hostname is required.")
        if "." not in hostname:
            hostname = f"{hostname}.{self._config.mdns_default_domain}"
        return hostname

    @staticmethod
    def _normalize_port(value: str, *, field_name: str) -> str:
        port = str(value or "").strip()
        if not port.isdigit():
            raise ValueError(f"{field_name} must be a number.")
        port_number = int(port)
        if port_number < 1 or port_number > 65535:
            raise ValueError(f"{field_name} must be between 1 and 65535.")
        return str(port_number)

    @staticmethod
    def _route_name(stack_id: str, service_name: str) -> str:
        value = f"{stack_id}-{service_name}".lower()
        value = re.sub(r"[^a-z0-9-]+", "-", value)
        value = re.sub(r"-{2,}", "-", value).strip("-")
        return value or "app"

    def _render_traefik_override(self, service_name: str, target_port: str, hostname: str, route_name: str) -> str:
        return f"""# Auto-generated by Niwaki.
# This file is managed by Niwaki's Traefik override generator.
services:
  {service_name}:
    ports: !reset []
    expose:
      - "{target_port}"
    networks:
      - {self._config.traefik_network}
    labels:
      traefik.enable: "true"
      traefik.docker.network: "{self._config.traefik_network}"
      traefik.http.routers.{route_name}.rule: "Host(`{hostname}`)"
      traefik.http.routers.{route_name}.entrypoints: "{self._config.traefik_entrypoint}"
      traefik.http.routers.{route_name}.service: "{route_name}"
      traefik.http.services.{route_name}.loadbalancer.server.port: "{target_port}"

networks:
  {self._config.traefik_network}:
    external: true
"""

    @staticmethod
    def _render_port_override(service_name: str, published_port: str, target_port: str) -> str:
        return f"""# Auto-generated by Niwaki.
# This file is managed by Niwaki's direct port override generator.
services:
  {service_name}:
    ports: !override
      - "{published_port}:{target_port}"
"""
