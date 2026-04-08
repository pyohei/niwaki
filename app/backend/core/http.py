import json
from pathlib import Path
from typing import Any


class ApiError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def json_response(handler: Any, payload: Any, status_code: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: Any, body: str, status_code: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
    data = body.encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def send_static_file(handler: Any, path: Path, content_type: str) -> None:
    if not path.exists():
        raise ApiError(404, "Not Found")
    data = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def read_json_body(handler: Any) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0") or "0")
    if content_length == 0:
        return {}
    raw = handler.rfile.read(content_length).decode("utf-8")
    if not raw.strip():
        return {}
    return json.loads(raw)
