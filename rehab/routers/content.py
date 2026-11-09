"""Palabras, categorías, repetición espaciada, comunicador (AAC) y configuración."""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request

from ..schemas import PatientCreate, WordCreate
from ..security import current_patient
from ..services import db, voice_processor
from .speech import generate_tts_cache

router = APIRouter(prefix="/api")


@router.get("/words/{category}")
def get_words(category: str, level: int = 1):
    """Obtiene palabras por categoría y nivel"""
    words = db.get_words(category, level)
    return {"words": words, "category": category, "level": level}


@router.get("/categories")
def get_categories():
    """Lista todas las categorías disponibles"""
    categories = db.get_categories()
    return {"categories": categories}


@router.post("/words")
def add_custom_word(word: WordCreate):
    """Agrega una palabra personalizada"""
    db.add_word(word.model_dump())
    return {"success": True, "message": "Palabra agregada"}


@router.get("/words/practice/{category}")
def get_practice_words(
    category: str,
    background_tasks: BackgroundTasks,
    request: Request,
    level: Optional[int] = None,
    count: int = 10
):
    """
    Obtiene palabras priorizadas para práctica usando repetición espaciada.
    Las palabras más difíciles y menos practicadas aparecen primero.
    """
    patient_id = current_patient(request)
    words = db.get_words_for_practice(patient_id, category, level, count)

    # Disparar generación de audio en background
    background_tasks.add_task(generate_tts_cache, words)

    return {
        "words": words,
        "category": category,
        "level": level,
        "patient_id": patient_id,
        "method": "spaced_repetition"
    }


@router.get("/words/difficult/{patient_id}")
def get_difficult_words(patient_id: str, request: Request, limit: int = 10):
    """
    Obtiene las palabras más difíciles para el paciente.
    Útil para práctica enfocada en áreas de mejora.
    """
    patient_id = current_patient(request)
    words = db.get_difficult_words(patient_id, limit)
    return {
        "words": words,
        "patient_id": patient_id,
        "count": len(words)
    }


@router.get("/aac/config")
def get_aac_config():
    """Obtiene configuración completa del tablero AAC"""
    return db.get_aac_config()


@router.get("/config")
def get_config():
    """Obtiene la configuración actual"""
    return {
        "voices_available": voice_processor.get_available_voices(),
        "languages": ["es-ES", "es-MX", "en-US"],
        "difficulty_levels": [1, 2, 3, 4, 5],
        "categories": db.get_categories()
    }


@router.post("/patient/register")
def register_patient(patient: PatientCreate):
    """Registra un nuevo paciente"""
    patient_id = db.register_patient(patient.model_dump())
    return {"patient_id": patient_id, "success": True}
