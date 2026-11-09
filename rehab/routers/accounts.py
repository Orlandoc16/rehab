"""Inicio y cierre de sesión, y selección del paciente activo."""
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

import auth

from .. import security, settings
from ..security import safe_next, session_token_hash
from ..services import db
from ..web import page

router = APIRouter()

LOGIN_TITLE = "Iniciar sesión - Rehab Voice"


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/", logout: int = 0):
    no_users = (await run_in_threadpool(db.count_therapists)) == 0
    return page(request, "login.html", LOGIN_TITLE,
                next=safe_next(next), error=None, no_users=no_users, logged_out=bool(logout))


@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/")):
    ip = request.client.host if request.client else "?"
    keys = (f"user:{username.strip().lower()}", f"ip:{ip}")

    def fail(message: str, status: int):
        response = page(request, "login.html", LOGIN_TITLE, next=safe_next(next),
                        error=message, no_users=False, logged_out=False, username=username)
        response.status_code = status
        return response

    limiter = security.login_limiter
    wait = limiter.retry_after(*keys)
    if wait:
        return fail(f"Demasiados intentos fallidos. Espera {wait} segundos y vuelve a intentarlo.", 429)
    therapist = await run_in_threadpool(db.get_therapist_by_username, username)
    ok = await run_in_threadpool(auth.check_credentials, password, therapist["password_hash"] if therapist else None)
    if not ok or therapist is None:
        limiter.record_failure(*keys)
        return fail("Usuario o contraseña incorrectos.", 401)

    limiter.record_success(*keys)
    token, token_hash = auth.new_session_token()
    await run_in_threadpool(db.create_session, token_hash, therapist["id"], auth.session_expiry())
    response = RedirectResponse(f"/patients?next={quote(safe_next(next))}", status_code=303)
    response.set_cookie(auth.SESSION_COOKIE, token, httponly=True, samesite="lax", secure=settings.COOKIE_SECURE,
                        max_age=auth.SESSION_IDLE_HOURS * 3600, path="/")
    return response


@router.post("/logout")
async def logout(request: Request):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        await run_in_threadpool(db.delete_session, auth.token_hash(token))
    response = RedirectResponse("/login?logout=1", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response


@router.get("/patients", response_class=HTMLResponse)
async def patients_page(request: Request, next: str = "/"):
    patients = await run_in_threadpool(db.list_patients)
    return page(request, "patients.html", "Pacientes - Rehab Voice", patients=patients, next=safe_next(next))


@router.post("/patients/select")
async def select_patient(request: Request, patient_id: str = Form(...), next: str = Form("/")):
    if not await run_in_threadpool(db.set_session_patient, session_token_hash(request), patient_id):
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return RedirectResponse(safe_next(next), status_code=303)


@router.post("/patients/new")
async def new_patient(request: Request, name: str = Form(...), age: str = Form(""),
                      diagnosis: str = Form(""), notes: str = Form(""), next: str = Form("/")):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    age_value = int(age) if age.strip().isdigit() else None
    patient_id = await run_in_threadpool(db.register_patient, {
        "name": name, "age": age_value, "diagnosis": diagnosis.strip() or None,
        "notes": notes.strip() or None, "therapist": request.state.session["therapist_name"]})
    await run_in_threadpool(db.set_session_patient, session_token_hash(request), patient_id)
    return RedirectResponse(safe_next(next), status_code=303)
