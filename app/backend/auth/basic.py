import base64
import hashlib
import hmac
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AuthConfig:
    username: str
    password: str
    password_hash: str
    realm: str = "Niwaki"


class BasicAuthenticator:
    def __init__(self, config: AuthConfig):
        self._config = config

    @property
    def realm(self) -> str:
        return self._config.realm

    def is_authorized(self, header_value: Optional[str]) -> bool:
        username, password = self._parse_basic_auth(header_value)
        if username != self._config.username:
            return False
        return self._verify_password(password)

    def _verify_password(self, password: Optional[str]) -> bool:
        if password is None:
            return False
        password_hash = self._config.password_hash.strip()
        if password_hash:
            return self._verify_pbkdf2(password, password_hash)
        return hmac.compare_digest(password, self._config.password)

    @staticmethod
    def _parse_basic_auth(header_value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        if not header_value or not header_value.startswith("Basic "):
            return None, None
        try:
            payload = base64.b64decode(header_value.split(" ", 1)[1]).decode("utf-8")
        except Exception:
            return None, None
        if ":" not in payload:
            return None, None
        return payload.split(":", 1)

    @staticmethod
    def _verify_pbkdf2(password: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt, expected = encoded.split("$", 3)
        except ValueError:
            return False
        if algorithm != "pbkdf2_sha256":
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(derived, expected)
