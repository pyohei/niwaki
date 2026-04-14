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
        preset: str = "",
        extra_environment: str = "",
        homepage_enabled: bool = False,
        homepage_group: str = "",
        homepage_name: str = "",
        homepage_icon: str = "",
        homepage_href: str = "",
        homepage_description: str = "",
    ) -> dict:
        discovered = self._compose.discover_services(stack)
        known_services = {item["name"] for item in discovered}
        if service_name not in known_services:
            raise ValueError(f"Unknown service: {service_name}")

        port = str(target_port or "").strip()
        port = self._normalize_port(target_port, field_name="Target port")

        normalized_host = self._normalize_hostname(hostname)
        route_name = self._route_name(stack.id, service_name)
        environment_items = self._build_traefik_environment(
            preset=preset,
            hostname=normalized_host,
            extra_environment=extra_environment,
        )
        label_items = self._build_homepage_labels(
            enabled=homepage_enabled,
            default_href=f"http://{normalized_host}/",
            group=homepage_group,
            name=homepage_name,
            icon=homepage_icon,
            href=homepage_href,
            description=homepage_description,
        )
        override_path = Path(stack.override_file)
        override_path.parent.mkdir(parents=True, exist_ok=True)
        override_path.write_text(
            self._render_traefik_override(
                service_name,
                port,
                normalized_host,
                route_name,
                environment_items=environment_items,
                homepage_label_items=label_items,
            ),
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
            "preset": preset,
            "environment": environment_items,
            "homepage_labels": label_items,
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

    def _render_traefik_override(
        self,
        service_name: str,
        target_port: str,
        hostname: str,
        route_name: str,
        *,
        environment_items: list[tuple[str, str]],
        homepage_label_items: list[tuple[str, str]],
    ) -> str:
        environment_block = ""
        if environment_items:
            environment_lines = "\n".join(
                f"      {key}: {self._yaml_quote(value)}" for key, value in environment_items
            )
            environment_block = f"    environment:\n{environment_lines}\n"
        homepage_lines = "\n".join(
            f"      {key}: {self._yaml_quote(value)}" for key, value in homepage_label_items
        )
        homepage_block = f"\n{homepage_lines}" if homepage_lines else ""
        return f"""# Auto-generated by Niwaki.
# This file is managed by Niwaki's Traefik override generator.
services:
  {service_name}:
    ports: !reset []
    expose:
      - "{target_port}"
{environment_block}    networks:
      - {self._config.traefik_network}
    labels:
      traefik.enable: "true"
      traefik.docker.network: "{self._config.traefik_network}"
      traefik.http.routers.{route_name}.rule: "Host(`{hostname}`)"
      traefik.http.routers.{route_name}.entrypoints: "{self._config.traefik_entrypoint}"
      traefik.http.routers.{route_name}.service: "{route_name}"
      traefik.http.services.{route_name}.loadbalancer.server.port: "{target_port}"{homepage_block}

networks:
  {self._config.traefik_network}:
    external: true
"""

    @staticmethod
    def _parse_environment_lines(raw_value: str) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for index, raw_line in enumerate(str(raw_value or "").splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError(f"Environment line {index} must be KEY=VALUE.")
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                raise ValueError(f"Environment line {index} must have a key.")
            items.append((key, value))
        return items

    def _build_traefik_environment(
        self,
        *,
        preset: str,
        hostname: str,
        extra_environment: str,
    ) -> list[tuple[str, str]]:
        environment_map = dict(self._parse_environment_lines(extra_environment))
        normalized_preset = str(preset or "").strip().lower()
        if normalized_preset == "homepage" and "HOMEPAGE_ALLOWED_HOSTS" not in environment_map:
            environment_map["HOMEPAGE_ALLOWED_HOSTS"] = f"localhost:3000,127.0.0.1:3000,{hostname}"
        return list(environment_map.items())

    @staticmethod
    def _build_homepage_labels(
        *,
        enabled: bool,
        default_href: str,
        group: str,
        name: str,
        icon: str,
        href: str,
        description: str,
    ) -> list[tuple[str, str]]:
        if not enabled:
            return []
        resolved_group = group.strip() or "Apps"
        resolved_name = name.strip()
        resolved_href = href.strip() or default_href
        if not resolved_name:
            raise ValueError("Homepage name is required when Homepage listing is enabled.")
        items: list[tuple[str, str]] = [
            ("homepage.group", resolved_group),
            ("homepage.name", resolved_name),
            ("homepage.href", resolved_href),
        ]
        if icon.strip():
            items.append(("homepage.icon", icon.strip()))
        if description.strip():
            items.append(("homepage.description", description.strip()))
        return items

    @staticmethod
    def _yaml_quote(value: str) -> str:
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def _render_port_override(service_name: str, published_port: str, target_port: str) -> str:
        return f"""# Auto-generated by Niwaki.
# This file is managed by Niwaki's direct port override generator.
services:
  {service_name}:
    ports: !override
      - "{published_port}:{target_port}"
"""
