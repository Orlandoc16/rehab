"""Plantillas, estáticos con caché larga y compresión gzip selectiva."""
import hashlib
import re
from functools import lru_cache

from fastapi import Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.types import ASGIApp, Receive, Scope, Send

from . import settings
from .settings import STATIC_DIR, TEMPLATES_DIR

# Compresión gzip para HTML, JSON, CSS y JS. Se excluyen audio e imágenes: ya están
# comprimidos, y el audio usa peticiones por rangos que gzip rompería.
_NO_GZIP_SUFFIXES = (".webp", ".png", ".jpg", ".jpeg", ".gif", ".mp3", ".wav", ".ogg", ".woff2", ".ico")


class SelectiveGZipMiddleware:
    def __init__(self, app: ASGIApp, minimum_size: int = 1000) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if path and not path.startswith("/api/speak") and not path.lower().endswith(_NO_GZIP_SUFFIXES):
            await self.gzip(scope, receive, send)
        else:
            await self.app(scope, receive, send)


# Archivos con hash de contenido en el nombre (p. ej. fuente.398bd26380.woff2)
_HASHED_NAME = re.compile(r"\.[0-9a-f]{10}\.[a-z0-9]+$")


class CachedStaticFiles(StaticFiles):
    """Estáticos con Cache-Control: un año si la URL lleva ?v=<hash> (ver asset()) o el nombre
    lleva un hash de contenido; 1 hora en otro caso."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            versioned = b"v=" in scope.get("query_string", b"") or _HASHED_NAME.search(path) is not None
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable" if versioned else "public, max-age=3600"
            )
        return response


@lru_cache(maxsize=256)
def _asset_hash(path: str, mtime_ns: int) -> str:
    return hashlib.sha256((STATIC_DIR / path).read_bytes()).hexdigest()[:10]


def asset(path: str) -> str:
    """URL de un estático con hash de contenido: cambia sola cuando cambia el archivo."""
    try:
        return f"/static/{path}?v={_asset_hash(path, (STATIC_DIR / path).stat().st_mtime_ns)}"
    except FileNotFoundError:
        return f"/static/{path}"


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["asset"] = asset
templates.env.globals["samples_enabled"] = lambda: settings.EVAL_RECORDING


def page(request: Request, template: str, title: str, **context):
    """Renderiza una página con la sesión (cabecera con el paciente activo)."""
    return templates.TemplateResponse(request, template, {
        "title": title, "session": getattr(request.state, "session", None), **context})
