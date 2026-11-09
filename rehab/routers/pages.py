"""Páginas HTML y service worker."""
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from ..settings import STATIC_DIR
from ..web import page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Página principal"""
    return page(request, "index.html", "Rehab Voice 2025")


@router.get("/practice", response_class=HTMLResponse)
async def practice(request: Request):
    """Página de práctica de palabras"""
    return page(request, "practice.html", "Práctica - Rehab Voice")


@router.get("/games", response_class=HTMLResponse)
async def games(request: Request):
    """Página de juegos"""
    return page(request, "games.html", "Juegos - Rehab Voice")


@router.get("/progress", response_class=HTMLResponse)
async def progress(request: Request):
    """Página de progreso del paciente"""
    return page(request, "progress.html", "Mi Progreso - Rehab Voice")


@router.get("/communicator", response_class=HTMLResponse)
async def communicator(request: Request):
    """Página del tablero de comunicación"""
    return page(request, "communicator.html", "Comunicador - Rehab Voice")


@router.get("/sw.js", include_in_schema=False)
async def service_worker():
    """Service worker desde la raíz: su alcance es toda la app (comunicador sin conexión)."""
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})
