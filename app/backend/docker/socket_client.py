import http.client
import json
import socket
import urllib.parse
from typing import Any, Optional


class DockerAPIError(Exception):
    pass


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, unix_socket_path: str):
        super().__init__("localhost")
        self.unix_socket_path = unix_socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.unix_socket_path)


class DockerAPIClient:
    def __init__(self, socket_path: str, api_version: str):
        self.socket_path = socket_path
        self.api_version = api_version

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        headers: Optional[dict[str, str]] = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        connection = UnixHTTPConnection(self.socket_path)
        payload = body
        request_headers = dict(headers or {})
        if isinstance(body, (dict, list)):
            payload = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            payload = body.encode("utf-8")
        full_path = f"/{self.api_version}{path}"
        connection.request(method, full_path, body=payload, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        if response.status not in expected:
            detail = raw.decode("utf-8", errors="replace").strip()
            raise DockerAPIError(f"Docker API {response.status}: {detail or response.reason}")
        content_type = response.getheader("Content-Type", "")
        if raw and "application/json" in content_type:
            return json.loads(raw.decode("utf-8"))
        return raw

    def list_containers_by_label(self, label_key: str, label_value: str = "true") -> list[dict[str, Any]]:
        filters = urllib.parse.quote(json.dumps({"label": [f"{label_key}={label_value}"]}), safe="")
        return self.request("GET", f"/containers/json?all=1&filters={filters}")

    def list_containers_by_name(self, name: str) -> list[dict[str, Any]]:
        filters = urllib.parse.quote(json.dumps({"name": [name]}), safe="")
        return self.request("GET", f"/containers/json?all=1&filters={filters}")

    def create_container(self, name: str, config: dict[str, Any]) -> None:
        self.request(
            "POST",
            f"/containers/create?name={urllib.parse.quote(name, safe='')}",
            body=config,
            expected=(201,),
        )

    def start_container(self, container_name: str) -> None:
        self.request(
            "POST",
            f"/containers/{urllib.parse.quote(container_name, safe='')}/start",
            expected=(204, 304),
        )

    def delete_container(self, container_id: str) -> None:
        self.request(
            "DELETE",
            f"/containers/{urllib.parse.quote(container_id, safe='')}?force=1",
            expected=(204,),
        )
