import posixpath
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..audit.store import AuditStore
from ..auth.basic import BasicAuthenticator
from ..core.config import AppConfig, _join_http_url, load_config
from ..core.http import ApiError, json_response, read_json_body, send_static_file
from ..docker.compose import ComposeService
from ..docker.socket_client import DockerAPIClient
from ..features.deploys.service import DeployService
from ..features.logs.service import LogsService
from ..features.mdns.service import MdnsService
from ..features.settings.service import SettingsService
from ..features.stacks.service import StackService
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
            json_response(self, {"items": self.server.services.audit_store.list_recent(limit=limit)})
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
    fallback_url = (
        _join_http_url(config.traefik_fallback_host, path=config.base_path) if config.traefik_enabled else ""
    )
    alias_url = _join_http_url(config.traefik_host) if config.traefik_enabled else ""
    return {
        "name": "Niwaki",
        "base_url": config.base_url,
        "base_path": config.base_path,
        "alias_url": alias_url if alias_url != config.base_url else "",
        "fallback_url": fallback_url if fallback_url != config.base_url else "",
        "settings_db_path": str(config.settings_db_path),
        "stack_root": str(config.stack_root) if config.stack_root else "",
        "mdns_enabled": config.mdns_enabled,
        "mdns_target_ip": config.mdns_target_ip,
    }


def build_services(config: AppConfig) -> AppServices:
    auth = BasicAuthenticator(config.auth)
    audit_store = AuditStore(config.audit_log_path, config.command_log_retention_days)
    registry = StackRegistry(config.settings_db_path, config.stack_root)
    credential_store = GitCredentialStore(config.settings_db_path)
    compose_service = ComposeService(config.command_output_max_lines)
    git_service = GitService(config.git_pull_flags, credential_store)
    docker_api = DockerAPIClient(config.docker_socket_path, config.docker_api_version)
    stack_service = StackService(registry, compose_service, git_service, audit_store)
    deploy_service = DeployService(compose_service, git_service, audit_store, config.command_output_max_lines)
    logs_service = LogsService(compose_service, config.command_output_max_lines)
    mdns_service = MdnsService(config, docker_api)
    settings_service = SettingsService(registry, credential_store)
    return AppServices(
        config=config,
        auth=auth,
        stack_service=stack_service,
        deploy_service=deploy_service,
        logs_service=logs_service,
        mdns_service=mdns_service,
        settings_service=settings_service,
        audit_store=audit_store,
    )


def serve() -> None:
    config = load_config()
    services = build_services(config)
    server = NiwakiHTTPServer((config.host, config.port), services)
    print(f"Niwaki listening on http://{config.host}:{config.port}")
    server.serve_forever()
