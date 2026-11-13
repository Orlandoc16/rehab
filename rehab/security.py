"""Sesión obligatoria y paciente activo.

Todas las páginas y la API requieren la sesión de un terapeuta, que elige el paciente con el
que trabaja. El SERVIDOR impone ese paciente: se ignora el patient_id que envía el navegador
(las páginas envían "default", que significa "el paciente activo").
"""
from typing import Optional
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

import auth

from .services import db

PUBLIC_PATHS = {"/login", "/sw.js", "/favicon.ico"}
NO_PATIENT_PATHS = {"/patients", "/patients/select", "/patients/new", "/logout"}

# Límite de intentos de inicio de sesión (se consulta como security.login_limiter en cada
# petición, así los tests pueden sustituirlo).
login_limiter = auth.LoginRateLimiter()


def safe_next(target: Optional[str]) -> str:
    """Solo redirecciones internas (evita redirecciones abiertas a otros sitios)."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target \
            and not target.startswith(("/login", "/logout", "/patients")):
        return target
    return "/"


async def require_login(request: Request, call_next):
    """Middleware: sin sesión -> login (páginas) o 401 (API); sin paciente -> elegirlo."""
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)

    token = request.cookies.get(auth.SESSION_COOKIE)
    info = None
    if token:
        info = await run_in_threadpool(db.get_session, auth.token_hash(token), auth.utcnow(), auth.session_expiry())
    if info is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Inicia sesión para continuar"}, status_code=401)
        target = path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/login?next={quote(target)}", status_code=303)

    request.state.session = info
    # /patients/<id>/edit y /delete: la ficha se gestiona aunque aún no se haya elegido paciente
    if info["patient_id"] is None and path not in NO_PATIENT_PATHS and not path.startswith("/patients/"):
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Selecciona un paciente"}, status_code=409)
        return RedirectResponse(f"/patients?next={quote(path)}", status_code=303)
    return await call_next(request)


def current_patient(request: Request) -> str:
    """Paciente activo de la sesión (el middleware garantiza que existe)."""
    return request.state.session["patient_id"]


def session_token_hash(request: Request) -> str:
    return auth.token_hash(request.cookies.get(auth.SESSION_COOKIE) or "")
