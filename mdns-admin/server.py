import base64
import html
import http.client
import json
import os
import re
import socket
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ALIAS_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.local$")
DOCKER_SOCKET_PATH = os.environ.get("DOCKER_SOCKET_PATH", "/var/run/docker.sock")
DOCKER_API_VERSION = os.environ.get("DOCKER_API_VERSION", "v1.41")
MDNS_ADMIN_HOST = os.environ.get("MDNS_ADMIN_HOST", "0.0.0.0")
MDNS_ADMIN_PORT = int(os.environ.get("MDNS_ADMIN_PORT", "8080"))
MDNS_ADMIN_USERNAME = os.environ.get("MDNS_ADMIN_USERNAME", "admin")
MDNS_ADMIN_PASSWORD = os.environ.get("MDNS_ADMIN_PASSWORD") or "__mdns_admin_password_unset__"
MDNS_PUBLISH_IMAGE = os.environ.get("MDNS_PUBLISH_IMAGE", "mdns-admin:local")
MDNS_TARGET_IP = os.environ.get("MDNS_TARGET_IP", "")
TEMPLATE_PATH = Path(__file__).with_name("template.html")

MANAGED_LABEL = "io.mdns-admin.managed"
ALIAS_LABEL = "io.mdns-admin.alias"
TARGET_IP_LABEL = "io.mdns-admin.target-ip"
DBUS_SOCKET_HOST_PATH = "/var/run/dbus/system_bus_socket"


class DockerError(Exception):
    pass


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, unix_socket_path: str):
        super().__init__("localhost")
        self.unix_socket_path = unix_socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.unix_socket_path)


class DockerClient:
    def __init__(self, socket_path: str, api_version: str):
        self.socket_path = socket_path
        self.api_version = api_version

    def request(self, method: str, path: str, *, body=None, headers=None, expected=(200,)):
        conn = UnixHTTPConnection(self.socket_path)
        request_headers = dict(headers or {})
        payload = body
        if isinstance(body, (dict, list)):
            payload = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            payload = body.encode("utf-8")
        full_path = f"/{self.api_version}{path}"
        conn.request(method, full_path, body=payload, headers=request_headers)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        if response.status not in expected:
            detail = raw.decode("utf-8", errors="replace").strip()
            raise DockerError(f"Docker API {response.status}: {detail or response.reason}")
        content_type = response.getheader("Content-Type", "")
        if raw and "application/json" in content_type:
            return json.loads(raw.decode("utf-8"))
        return raw

    def list_alias_containers(self):
        filters = urllib.parse.quote(
            json.dumps({"label": [f"{MANAGED_LABEL}=true"]}),
            safe="",
        )
        containers = self.request("GET", f"/containers/json?all=1&filters={filters}")
        aliases = []
        for container in containers:
            labels = container.get("Labels") or {}
            aliases.append(
                {
                    "id": container.get("Id", ""),
                    "name": (container.get("Names") or [""])[0].lstrip("/"),
                    "alias": labels.get(ALIAS_LABEL, ""),
                    "status": container.get("Status", ""),
                    "state": container.get("State", ""),
                    "image": container.get("Image", ""),
                    "target_ip": labels.get(TARGET_IP_LABEL, ""),
                    "created": container.get("Created"),
                }
            )
        aliases.sort(key=lambda item: item["alias"])
        return aliases

    def create_alias_container(self, alias: str, target_ip: str, image: str):
        name = container_name_for_alias(alias)
        config = {
            "Image": image,
            "Cmd": ["publisher"],
            "Env": [
                f"MDNS_ALIAS={alias}",
                f"MDNS_TARGET_IP={target_ip}",
                "DBUS_SYSTEM_BUS_ADDRESS=unix:path=/var/run/dbus/system_bus_socket",
            ],
            "Labels": {
                MANAGED_LABEL: "true",
                ALIAS_LABEL: alias,
                TARGET_IP_LABEL: target_ip,
            },
            "HostConfig": {
                "Binds": [f"{DBUS_SOCKET_HOST_PATH}:{DBUS_SOCKET_HOST_PATH}"],
                "NetworkMode": "none",
                "RestartPolicy": {"Name": "unless-stopped"},
            },
        }
        self.request(
            "POST",
            f"/containers/create?name={urllib.parse.quote(name, safe='')}",
            body=config,
            expected=(201,),
        )
        self.request(
            "POST",
            f"/containers/{urllib.parse.quote(name, safe='')}/start",
            expected=(204,),
        )

    def delete_alias_container(self, container_id: str):
        self.request(
            "DELETE",
            f"/containers/{urllib.parse.quote(container_id, safe='')}?force=1",
            expected=(204,),
        )


docker_client = DockerClient(DOCKER_SOCKET_PATH, DOCKER_API_VERSION)
PAGE_TEMPLATE = TEMPLATE_PATH.read_text(encoding="utf-8")


def normalize_alias(raw_value: str) -> str:
    value = raw_value.strip().lower()
    if not value:
        raise ValueError("Alias is required.")
    if not value.endswith(".local"):
        value = f"{value}.local"
    if not ALIAS_NAME_RE.fullmatch(value):
        raise ValueError("Alias must be a single label like gitea.local.")
    return value


def container_name_for_alias(alias: str) -> str:
    return "mdns-alias-" + alias[:-6]


def parse_basic_auth(header_value: str):
    if not header_value or not header_value.startswith("Basic "):
        return None, None
    try:
        payload = base64.b64decode(header_value.split(" ", 1)[1]).decode("utf-8")
    except Exception:
        return None, None
    if ":" not in payload:
        return None, None
    return payload.split(":", 1)


def format_created(timestamp):
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_alias_rows(aliases):
    if not aliases:
        return """
      <tr>
        <td colspan="6" class="empty">No Docker-managed aliases yet.</td>
      </tr>
    """

    rows = []
    for item in aliases:
        alias = html.escape(item["alias"])
        target_ip = html.escape(item["target_ip"])
        state = html.escape(item["state"] or "")
        status = html.escape(item["status"] or "")
        created = html.escape(format_created(item["created"]))
        delete_target = urllib.parse.quote(item["alias"], safe="")
        rows.append(
            f"""
      <tr>
        <td><code>{alias}</code></td>
        <td><code>{target_ip}</code></td>
        <td>{state}</td>
        <td>{status}</td>
        <td>{created}</td>
        <td>
          <form method="post" action="aliases/{delete_target}/delete" onsubmit="return confirm('Delete {alias}?');">
            <button type="submit">Delete</button>
          </form>
        </td>
      </tr>
"""
        )
    return "".join(rows)


def render_banners(*, message="", error="", warning=""):
    banners = []
    if message:
        banners.append(f'<p class="banner ok">{html.escape(message)}</p>')
    if error:
        banners.append(f'<p class="banner error">{html.escape(error)}</p>')
    if warning:
        banners.append(f'<p class="banner warn">{html.escape(warning)}</p>')
    return "".join(banners)


def render_page(*, aliases, message="", error="", warning=""):
    return (
        PAGE_TEMPLATE.replace("{{BANNERS}}", render_banners(message=message, error=error, warning=warning))
        .replace("{{ALIAS_ROWS}}", render_alias_rows(aliases))
        .replace("{{TARGET_IP_HINT}}", html.escape(MDNS_TARGET_IP or "not configured"))
        .replace("{{BUTTON_DISABLED}}", "" if MDNS_TARGET_IP else "disabled")
        .replace("{{PUBLISH_IMAGE}}", html.escape(MDNS_PUBLISH_IMAGE))
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "mdns-admin/0.1"

    def do_GET(self):
        if not self._authorize():
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path not in ("", "/"):
            self.send_error(404)
            return
        self._render_index()

    def do_POST(self):
        if not self._authorize():
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/aliases":
            self._handle_create()
            return
        if parsed.path.startswith("/aliases/") and parsed.path.endswith("/delete"):
            self._handle_delete(parsed.path)
            return
        self.send_error(404)

    def _authorize(self):
        username, password = parse_basic_auth(self.headers.get("Authorization"))
        if username == MDNS_ADMIN_USERNAME and password == MDNS_ADMIN_PASSWORD:
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="mDNS Admin"')
        self.end_headers()
        self.wfile.write(b"Authentication required.")
        return False

    def _handle_create(self):
        form = self._read_form()
        alias_value = form.get("alias", [""])[0]
        try:
            if not MDNS_TARGET_IP:
                raise ValueError("MDNS_TARGET_IP is not configured.")
            alias = normalize_alias(alias_value)
            existing = {item["alias"] for item in docker_client.list_alias_containers()}
            if alias in existing:
                raise ValueError(f"{alias} already exists.")
            docker_client.create_alias_container(alias, MDNS_TARGET_IP, MDNS_PUBLISH_IMAGE)
            self._redirect_with_message(f"Created {alias}.")
        except (ValueError, DockerError) as exc:
            self._render_index(error=str(exc))

    def _handle_delete(self, path):
        try:
            encoded = path[len("/aliases/") : -len("/delete")].strip("/")
            alias = normalize_alias(urllib.parse.unquote(encoded))
            for item in docker_client.list_alias_containers():
                if item["alias"] == alias:
                    docker_client.delete_alias_container(item["id"])
                    self._redirect_with_message(f"Deleted {alias}.")
                    return
            raise ValueError(f"{alias} was not found.")
        except (ValueError, DockerError) as exc:
            self._render_index(error=str(exc))

    def _read_form(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return urllib.parse.parse_qs(raw, keep_blank_values=True)

    def _redirect_with_message(self, message):
        location = "/?" + urllib.parse.urlencode({"message": message})
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _render_index(self, *, error=""):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        message = params.get("message", [""])[0]
        warning = ""
        if MDNS_ADMIN_PASSWORD == "__mdns_admin_password_unset__":
            warning = "MDNS_ADMIN_PASSWORD is not configured."
        try:
            aliases = docker_client.list_alias_containers()
            self._send_html(
                200,
                render_page(
                    aliases=aliases,
                    message=message,
                    error=error,
                    warning=warning,
                ),
            )
        except DockerError as exc:
            self._send_html(
                500,
                render_page(
                    aliases=[],
                    message=message,
                    error=str(exc),
                    warning=warning,
                ),
            )

    def _send_html(self, status_code: int, page: str):
        encoded = page.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main():
    server = ThreadingHTTPServer((MDNS_ADMIN_HOST, MDNS_ADMIN_PORT), Handler)
    print(f"mDNS admin listening on {MDNS_ADMIN_HOST}:{MDNS_ADMIN_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
