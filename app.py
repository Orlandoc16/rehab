"""
🎤 REHAB VOICE 2025
Aplicación de Rehabilitación Vocal con IA
Desarrollado por Orlando - Agent Dragon

Características:
- Reconocimiento de voz con Whisper/Vosk
- Comparación fonética avanzada
- Progresión de palabras a frases
- Gamificación con puntos y logros
- Seguimiento de progreso del paciente

Punto de entrada. La aplicación vive en el paquete rehab/ (ver rehab/__init__.py).
"""
import os

import uvicorn

from rehab.main import app  # uvicorn app:app
from rehab.services import db, game_engine, voice_processor  # acceso para tests y herramientas

__all__ = ["app", "db", "game_engine", "voice_processor"]

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.getenv("HOST", "127.0.0.1"),   # 0.0.0.0 solo si no hay Caddy delante
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "0") == "1",
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        log_level="info"
    )
