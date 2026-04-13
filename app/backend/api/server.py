import posixpath
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..audit.store import AuditStore
from ..auth.basic import BasicAuthenticator
from ..core.config import AppConfig, load_config
from ..core.http import ApiError, json_response, read_json_body, send_static_file
from ..docker.compose import ComposeService
from ..docker.network import DockerNetworkService
from ..docker.socket_client import DockerAPIClient
from ..features.deploys.service import DeployService
from ..features.logs.service import LogsService
from ..features.mdns.service import MdnsService
from ..features.overrides.service import OverrideService
from ..features.settings.service import SettingsService
from ..features.stacks.service import StackService
from ..features.system.service import SystemService
from ..git.credentials import GitCredentialStore
from ..git.service import GitService
from ..stacks.registry import StackRegistry


@dataclass
class AppServices:
    config: AppConfig
    auth: BasicAuthenticator
    stack_service: StackService
    deploy_service: DeployService
    logs_service: LogsService
    mdns_service: MdnsService
    override_service: OverrideService
    system_service: SystemService
    settings_service: SettingsService
    audit_store: AuditStore


class NiwakiHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, services: AppServices):
        super().__init__(server_address, NiwakiHandler)
        self.services = services


class NiwakiHandler(BaseHTTPRequestHandler):
    server_version = "niwaki/0.1"

    def do_GET(self) -> None:
        try:
            if self.path.startswith("/api/"):
                self._dispatch_api_get()
                return
            if not self._require_auth():
                return
            self._serve_frontend()
        except ApiError as exc:
            json_response(self, {"error": exc.message}, exc.status_code)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, 500)

    def do_POST(self) -> None:
        try:
            if not self._require_auth():
                return
            self._dispatch_api_post()
        except ApiError as exc:
            json_response(self, {"error": exc.message}, exc.status_code)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, 500)

    def do_DELETE(self) -> None:
        try:
            if not self._require_auth():
                return
            self._dispatch_api_delete()
        except ApiError as exc:
            json_response(self, {"error": exc.message}, exc.status_code)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, 500)

    def log_message(self, format: str, *args) -> None:
        return

    def _dispatch_api_get(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            json_response(self, {"ok": True, "service": "niwaki"})
            return
        if not self._require_auth():
            return
        if path == "/api/meta":
            json_response(self, _meta_payload(self.server.services.config))
            return
        if path == "/api/stacks":
            json_response(self, {"items": self.server.services.stack_service.list_stacks()})
            return
        if path == "/api/settings/stacks":
            json_response(self, {"items": self.server.services.settings_service.list_stack_records()})
            return
        if path == "/api/settings/git-credential":
            json_response(self, self.server.services.settings_service.get_git_credential())
            return
        if path == "/api/system":
            json_response(self, self.server.services.system_service.get_status())
            return
        if path.startswith("/api/stacks/") and path.endswith("/logs"):
            stack_id = path.split("/")[3]
            tail = int(urllib.parse.parse_qs(parsed.query).get("tail", ["200"])[0])
            stack = self._resolve_stack(stack_id)
            json_response(self, self.server.services.logs_service.get_logs(stack, tail=tail))
            return
        if path.startswith("/api/stacks/"):
            stack_id = path.split("/")[3]
            try:
                payload = self.server.services.stack_service.get_stack(stack_id)
            except Exception as exc:
                raise ApiError(404, str(exc)) from exc
            json_response(self, payload)
            return
        if path == "/api/audit":
            limit = int(urllib.parse.parse_qs(parsed.query).get("limit", ["20"])[0])
            stack_id = urllib.parse.parse_qs(parsed.query).get("stack_id", [""])[0].strip()
            json_response(self, {"items": self.server.services.audit_store.list_recent(limit=limit, stack_id=stack_id or None)})
            return
        if path == "/api/mdns/aliases":
            if not self.server.services.config.mdns_enabled:
                raise ApiError(404, "mDNS feature is disabled.")
            json_response(self, {"items": self.server.services.mdns_service.list_aliases()})
            return
        raise ApiError(404, "Not Found")

    def _dispatch_api_post(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/stacks/") and "/actions/" in path:
            _, _, _, stack_id, _, action = path.split("/", 5)
            stack = self._resolve_stack(stack_id)
            try:
                record = self.server.services.deploy_service.run_action(stack, action)
            except ValueError as exc:
                raise ApiError(400, str(exc)) from exc
            json_response(self, record, 202)
            return
        if path.startswith("/api/stacks/") and path.endswith("/override/traefik"):
            stack_id = path.split("/")[3]
            stack = self._resolve_stack(stack_id)
            payload = read_json_body(self)
            try:
                override = self.server.services.override_service.generate_traefik_override(
                    stack,
                    service_name=str(payload.get("service_name") or "").strip(),
                    target_port=str(payload.get("target_port") or "").strip(),
                    hostname=str(payload.get("hostname") or "").strip(),
                    create_alias=bool(payload.get("create_alias")),
                    preset=str(payload.get("preset") or "").strip(),
                    extra_environment=str(payload.get("extra_environment") or ""),
                )
            except ValueError as exc:
                raise ApiError(400, str(exc)) from exc
            updated_stack = self._resolve_stack(stack_id)
            apply_record = self.server.services.deploy_service.run_action(updated_stack, "up")
            json_response(self, {"override": override, "apply": apply_record}, 202)
            return
        if path.startswith("/api/stacks/") and path.endswith("/override/port"):
            stack_id = path.split("/")[3]
            stack = self._resolve_stack(stack_id)
            payload = read_json_body(self)
            try:
                override = self.server.services.override_service.generate_port_override(
                    stack,
                    service_name=str(payload.get("service_name") or "").strip(),
                    target_port=str(payload.get("target_port") or "").strip(),
                    published_port=str(payload.get("published_port") or "").strip(),
                )
            except ValueError as exc:
                raise ApiError(400, str(exc)) from exc
            updated_stack = self._resolve_stack(stack_id)
            apply_record = self.server.services.deploy_service.run_action(updated_stack, "up")
            json_response(self, {"override": override, "apply": apply_record}, 202)
            return
        if path.startswith("/api/system/actions/"):
            action = path.rsplit("/", 1)[1]
            payload = read_json_body(self)
            try:
                result = self.server.services.system_service.launch_runtime_action(
                    action,
                    rolling_update=bool(payload.get("rolling_update")),
                )
            except ValueError as exc:
                raise ApiError(400, str(exc)) from exc
            json_response(self, result, 202)
            return
        if path == "/api/mdns/aliases":
            if not self.server.services.config.mdns_enabled:
                raise ApiError(404, "mDNS feature is disabled.")
            payload = read_json_body(self)
            try:
                result = self.server.services.mdns_service.create_alias(
                    payload.get("alias", ""),
                    payload.get("target_ip"),
                )
            except ValueError as exc:
                raise ApiError(400, str(exc)) from exc
            json_response(self, result, 201)
            return
        if path == "/api/settings/stacks":
            payload = read_json_body(self)
            try:
                result = self.server.services.settings_service.upsert_stack(payload)
            except Exception as exc:
                raise ApiError(400, str(exc)) from exc
            json_response(self, result, 201)
            return
        if path == "/api/settings/git-credential":
            payload = read_json_body(self)
            try:
                result = self.server.services.settings_service.upsert_git_credential(payload)
            except ValueError as exc:
                raise ApiError(400, str(exc)) from exc
            json_response(self, result, 201)
            return
        raise ApiError(404, "Not Found")

    def _dispatch_api_delete(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/mdns/aliases/"):
            if not self.server.services.config.mdns_enabled:
                raise ApiError(404, "mDNS feature is disabled.")
            alias = urllib.parse.unquote(path.rsplit("/", 1)[1])
            try:
                self.server.services.mdns_service.delete_alias(alias)
            except ValueError as exc:
                raise ApiError(404, str(exc)) from exc
            json_response(self, {"deleted": alias})
            return
        if path.startswith("/api/settings/stacks/"):
            stack_id = urllib.parse.unquote(path.rsplit("/", 1)[1])
            try:
                self.server.services.settings_service.delete_stack(stack_id)
            except Exception as exc:
                raise ApiError(404, str(exc)) from exc
            json_response(self, {"deleted": stack_id})
            return
        if path == "/api/settings/git-credential":
            self.server.services.settings_service.delete_git_credential()
            json_response(self, {"deleted": True})
            return
        raise ApiError(404, "Not Found")

    def _serve_frontend(self) -> None:
        request_path = urllib.parse.urlparse(self.path).path
        normalized = posixpath.normpath(request_path)
        forwarded_prefix = (self.headers.get("X-Forwarded-Prefix") or "").rstrip("/")
        if normalized == "." and forwarded_prefix:
            self.send_response(302)
            self.send_header("Location", f"{forwarded_prefix}/")
            self.end_headers()
            return
        if normalized == ".":
            normalized = "/"
        file_map = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "application/javascript; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
        }
        if normalized not in file_map:
            if _is_frontend_page(normalized):
                filename, content_type = ("index.html", "text/html; charset=utf-8")
                send_static_file(self, self.server.services.config.frontend_root / filename, content_type)
                return
            raise ApiError(404, "Not Found")
        filename, content_type = file_map[normalized]
        send_static_file(self, self.server.services.config.frontend_root / filename, content_type)

    def _resolve_stack(self, stack_id: str):
        try:
            return self.server.services.stack_service.resolve(stack_id)
        except Exception as exc:
            raise ApiError(404, str(exc)) from exc

    def _require_auth(self) -> bool:
        if self.server.services.auth.is_authorized(self.headers.get("Authorization")):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Basic realm="{self.server.services.auth.realm}"')
        self.end_headers()
        return False


def _meta_payload(config: AppConfig) -> dict:
    return {
        "name": "Niwaki",
        "base_url": config.base_url,
        "base_path": config.base_path,
        "settings_db_path": str(config.settings_db_path),
        "stack_root": str(config.stack_root) if config.stack_root else "",
        "runtime_root": str(config.runtime_root) if config.runtime_root else "",
        "mdns_enabled": config.mdns_enabled,
        "mdns_target_ip": config.mdns_target_ip,
    }


def _is_frontend_page(path: str) -> bool:
    if path in {"/settings", "/aliases", "/system", "/stacks"}:
        return True
    if not path.startswith("/stacks/"):
        return False
    remainder = path[len("/stacks/"):]
    return bool(remainder) and "/" not in remainder


def build_services(config: AppConfig) -> AppServices:
    auth = BasicAuthenticator(config.auth)
    audit_store = AuditStore(config.settings_db_path, config.command_log_retention_days, config.audit_log_path)
    registry = StackRegistry(config.settings_db_path, config.stack_root)
    credential_store = GitCredentialStore(config.settings_db_path)
    compose_service = ComposeService(config.command_output_max_lines)
    network_service = DockerNetworkService()
    git_service = GitService(config.git_pull_flags, credential_store)
    docker_api = DockerAPIClient(config.docker_socket_path, config.docker_api_version)
    stack_service = StackService(registry, compose_service, git_service, audit_store)
    deploy_service = DeployService(
        compose_service,
        network_service,
        git_service,
        audit_store,
        config.command_output_max_lines,
        config.traefik_network,
    )
    logs_service = LogsService(compose_service, config.command_output_max_lines)
    mdns_service = MdnsService(config, docker_api)
    override_service = OverrideService(config, registry, compose_service, mdns_service)
    system_service = SystemService(config, registry, docker_api)
    settings_service = SettingsService(registry, credential_store)
    return AppServices(
        config=config,
        auth=auth,
        stack_service=stack_service,
        deploy_service=deploy_service,
        logs_service=logs_service,
        mdns_service=mdns_service,
        override_service=override_service,
        system_service=system_service,
        settings_service=settings_service,
        audit_store=audit_store,
    )


def serve() -> None:
    config = load_config()
    services = build_services(config)
    server = NiwakiHTTPServer((config.host, config.port), services)
    print(f"Niwaki listening on http://{config.host}:{config.port}")
    server.serve_forever()
