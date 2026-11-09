"""Crea la aplicación FastAPI."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import settings
from .routers import accounts, content, pages, progress, samples, speech
from .security import require_login
from .services import db
from .web import CachedStaticFiles, SelectiveGZipMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización al arrancar y limpieza al cerrar"""
    print("🎤 Rehab Voice 2025 iniciando...")
    db.initialize()
    print("✅ Base de datos inicializada")
    print("✅ Sistema listo!")
    yield
    print("👋 Cerrando Rehab Voice 2025...")


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=lifespan,
        title="Rehab Voice 2025",
        description="Aplicación de Rehabilitación Vocal con IA",
        version="2.0.0"
    )

    # Middlewares: el último añadido es el más externo -> sesión, luego gzip, luego CORS.
    if settings.ALLOWED_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.ALLOWED_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(SelectiveGZipMiddleware)
    app.middleware("http")(require_login)

    app.mount("/static", CachedStaticFiles(directory=str(settings.STATIC_DIR)), name="static")
    for module in (accounts, pages, speech, content, progress, samples):
        app.include_router(module.router)
    return app


app = create_app()
