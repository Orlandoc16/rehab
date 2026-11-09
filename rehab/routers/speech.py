"""Análisis de voz (Whisper) y síntesis (TTS)."""
import asyncio
import os
import tempfile
import traceback
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from .. import settings
from ..services import voice_processor
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


@router.post("/analyze-voice")
async def analyze_voice(
    audio_file: UploadFile = File(...),
    target_word: str = Form(""),
    level: int = Form(1)
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

        # Procesar audio con nivel de tolerancia (en un hilo, sin bloquear el servidor)
        result = await _run_speech(voice_processor.analyze, temp_path, target_word, level=level)

        return JSONResponse(result)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _remove_quietly(temp_path)


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
