"""Configuración de la app (variables de entorno). Ver la tabla en el README."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Motor de voz: "faster_whisper" (por defecto), "whisper", "vosk" o "none" (sin modelo: tests/desarrollo)
STT_ENGINE = os.getenv("STT_ENGINE", "faster_whisper")
# Transcripciones simultáneas (Whisper usa la CPU)
SPEECH_CONCURRENCY = max(1, int(os.getenv("SPEECH_CONCURRENCY", "1")))
# La cookie de sesión solo viaja por HTTPS (1 detrás de Caddy)
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
# CORS: el frontend se sirve desde este mismo servidor y no lo necesita. Solo si otra web/app
# debe llamar a la API, lista sus orígenes separados por comas.
# Grabación de muestras de voz para evaluar el reconocimiento (página /samples). Desactivada por
# defecto: guarda la voz de pacientes. Las muestras van a EVAL_AUDIO_DIR (fuera de git).
EVAL_RECORDING = os.getenv("EVAL_RECORDING", "0") == "1"
EVAL_AUDIO_DIR = Path(os.getenv("EVAL_AUDIO_DIR", str(BASE_DIR / "eval_audio" / "clinica")))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
