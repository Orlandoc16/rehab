"""Análisis de voz (Whisper) y síntesis (TTS)."""
import asyncio
import json
import os
import tempfile
import traceback
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, StrictBool
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from .. import settings
from ..security import current_patient
from ..services import db, voice_processor
from voice_processor import NoVoiceAvailableError

router = APIRouter(prefix="/api")

# Whisper corre en CPU: se ejecuta fuera del event loop (en un hilo) para no congelar
# el resto de peticiones, y se limita cuántas transcripciones corren a la vez.
_speech_slots = asyncio.Semaphore(settings.SPEECH_CONCURRENCY)


async def _save_upload(upload: UploadFile) -> str:
    """Guarda el audio subido en un archivo temporal y devuelve su ruta."""
    fd, path = tempfile.mkstemp(prefix="audio_", suffix=".webm")
    with os.fdopen(fd, "wb") as f:
        f.write(await upload.read())
    return path


async def _run_speech(func, *args, **kwargs):
    """Ejecuta trabajo pesado de voz en un hilo, respetando el límite de concurrencia."""
    async with _speech_slots:
        return await run_in_threadpool(func, *args, **kwargs)


def _remove_quietly(path: Optional[str]) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _parse_browser_transcripts(raw: str) -> list:
    """Lo que oyó el reconocimiento del navegador (lista JSON de textos). Se acota: viene del cliente."""
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(values, list):
        return []
    # Solo la primera (la que el reconocedor cree más probable): quedarse con la mejor de varias
    # alternativas sesga hacia la palabra objetivo y da por buenas pronunciaciones incorrectas.
    return [v.strip()[:200] for v in values if isinstance(v, str) and v.strip()][:1]


@router.post("/analyze-voice")
async def analyze_voice(
    request: Request,
    audio_file: UploadFile = File(...),
    target_word: str = Form(""),
    level: int = Form(1),
    browser_transcripts: str = Form(""),
):
    """
    Analiza el audio del usuario y lo compara con la palabra objetivo

    Args:
        audio_file: Archivo de audio grabado
        target_word: Palabra o frase que el usuario intenta decir
        level: Nivel de dificultad (1-5) para ajustar tolerancia

    Returns:
        Análisis completo con transcripción, puntuación y feedback
    """
    temp_path = None
    try:
        # Validar nivel
        level = max(1, min(5, level))

        temp_path = await _save_upload(audio_file)

        patient_id = current_patient(request)
        # Lo oído por el navegador solo cuenta si el paciente consintió el reconocimiento en la nube
        alternatives = []
        if browser_transcripts and await run_in_threadpool(db.get_cloud_speech_consent, patient_id):
            alternatives = _parse_browser_transcripts(browser_transcripts)
        # Exigencia ajustada por el terapeuta para este paciente (se lee aquí, no del navegador)
        profile = await run_in_threadpool(db.get_speech_profile, patient_id)

        # Procesar audio con nivel de tolerancia (en un hilo, sin bloquear el servidor)
        result = await _run_speech(voice_processor.analyze, temp_path, target_word, level=level,
                                   alternatives=alternatives, tolerance_offset=profile["tolerance"])

        return JSONResponse(result)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _remove_quietly(temp_path)


class SpeechSettings(BaseModel):
    """Solo se cambian los campos enviados."""
    cloud_speech: Optional[bool] = None
    disorder: Optional[Literal["", "afasia", "disartria", "apraxia", "mixto", "otro"]] = None
    severity: Optional[Literal["", "leve", "moderada", "grave"]] = None
    max_recording_s: Optional[int] = Field(default=None, ge=5, le=30)
    pause_s: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    tolerance: Optional[int] = Field(default=None, ge=-15, le=15)
    slow_voice: Optional[StrictBool] = None  # voz modelo lenta en la práctica


def _speech_settings(patient_id: str) -> dict:
    consent = db.get_cloud_speech_consent(patient_id)
    return {"cloud_speech": consent is not None, "consent_at": consent.isoformat() if consent else None,
            "profile": db.get_speech_profile(patient_id)}


@router.get("/speech-settings")
async def get_speech_settings(request: Request):
    """Ajustes de voz del paciente activo: consentimiento del reconocimiento en la nube
    (navegador/Google) y perfil (trastorno, tiempos de grabación, exigencia)."""
    return await run_in_threadpool(_speech_settings, current_patient(request))


@router.post("/speech-settings")
async def set_speech_settings(settings_in: SpeechSettings, request: Request):
    """Cambia los ajustes enviados. cloud_speech=true registra la fecha del consentimiento."""
    patient_id = current_patient(request)
    if settings_in.cloud_speech is not None:
        await run_in_threadpool(db.set_cloud_speech_consent, patient_id, settings_in.cloud_speech)
    profile = settings_in.model_dump(exclude_none=True, exclude={"cloud_speech"})
    if profile:
        await run_in_threadpool(db.set_speech_profile, patient_id, profile)
    return await run_in_threadpool(_speech_settings, patient_id)


@router.post("/transcribe")
async def transcribe_audio(
    audio_file: UploadFile = File(...),
    initial_prompt: str = Form(None)
):
    """Solo transcribe el audio sin comparación, con soporte para prompt"""
    temp_path = None
    try:
        temp_path = await _save_upload(audio_file)

        transcription = await _run_speech(voice_processor.transcribe, temp_path, initial_prompt=initial_prompt)

        return {"transcription": transcription, "success": True}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _remove_quietly(temp_path)


# Piper genera WAV; las voces en línea, MP3
_AUDIO_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg"}


@router.get("/speak/{text}")
async def speak_text(text: str, voice: str = "es-ES-ElviraNeural", speed: str = "normal"):
    """Genera audio TTS para la palabra/frase objetivo"""
    try:
        audio_path = await voice_processor.text_to_speech(text, voice, speed)
        media_type = _AUDIO_TYPES.get(os.path.splitext(audio_path)[1].lower(), "application/octet-stream")
        return FileResponse(audio_path, media_type=media_type)
    except NoVoiceAvailableError as e:
        # La página usa entonces la voz del dispositivo
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        print(f"❌ Error en TTS: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def generate_tts_cache(words: list):
    """Tarea en segundo plano: pre-genera el audio de las palabras que se van a practicar."""
    print(f"🔄 Pre-generando TTS para {len(words)} palabras...")
    for word_item in words:
        try:
            await voice_processor.text_to_speech(word_item["word"])
        except Exception as e:
            print(f"⚠️ Error generando TTS background para {word_item['word']}: {e}")
