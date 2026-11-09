"""Autenticación de terapeutas: contraseñas, tokens de sesión y límite de intentos.

Solo usa la librería estándar:
- Contraseñas con scrypt (hashlib) y sal aleatoria; comparación en tiempo constante.
- La cookie lleva un token aleatorio; en la base de datos solo se guarda su SHA-256, así que
  una copia de la base de datos no permite suplantar sesiones.
- Tras varios intentos fallidos se bloquea temporalmente el inicio de sesión de ese usuario/IP.
"""
import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

SESSION_COOKIE = "rv_session"
SESSION_IDLE_HOURS = 12          # una jornada: la sesión caduca tras 12 h sin actividad
MIN_PASSWORD_LENGTH = 8

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt_b64),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


# Hash fijo para comparar cuando el usuario no existe: el tiempo de respuesta no revela
# qué nombres de usuario son válidos.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def check_credentials(password: str, stored_hash: str | None) -> bool:
    if stored_hash is None:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, stored_hash)


def new_session_token() -> Tuple[str, str]:
    """(token para la cookie, hash para la base de datos)"""
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def session_expiry() -> datetime:
    return utcnow() + timedelta(hours=SESSION_IDLE_HOURS)


class LoginRateLimiter:
    """Bloquea temporalmente tras demasiados intentos fallidos (por usuario y por IP)."""

    def __init__(self, max_failures: int = 5, window_s: int = 300, lockout_s: int = 60):
        self.max_failures, self.window_s, self.lockout_s = max_failures, window_s, lockout_s
        self._failures: Dict[str, list] = {}
        self._locked_until: Dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, *keys: str) -> int:
        """Segundos que faltan para poder reintentar (0 si no hay bloqueo)."""
        now = time.monotonic()
        with self._lock:
            return max([0] + [int(self._locked_until.get(k, 0) - now) + 1 for k in keys if self._locked_until.get(k, 0) > now])

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                recent = [t for t in self._failures.get(k, []) if now - t < self.window_s] + [now]
                self._failures[k] = recent
                if len(recent) >= self.max_failures:
                    self._locked_until[k] = now + self.lockout_s
                    self._failures[k] = []

    def record_success(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._failures.pop(k, None)
                self._locked_until.pop(k, None)
