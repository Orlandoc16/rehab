"""Progreso, estadísticas y juegos (siempre del paciente activo de la sesión)."""
from fastapi import APIRouter, Request

from ..schemas import ChallengeComplete, ProgressCreate
from ..security import current_patient
from ..services import db, game_engine

router = APIRouter(prefix="/api")


@router.get("/progress/{patient_id}")
def get_progress(patient_id: str, request: Request):
    """Obtiene el progreso del paciente activo"""
    return db.get_progress(current_patient(request))


@router.post("/progress")
def save_progress(progress: ProgressCreate, request: Request):
    """Guarda el progreso de una sesión (siempre para el paciente activo)"""
    record = progress.as_record(current_patient(request))
    db.save_progress(record)

    # Calcular puntos del juego
    points = game_engine.calculate_points(record)

    return {
        "success": True,
        "points_earned": points,
        "total_points": db.get_total_points(record["patient_id"])
    }


@router.get("/stats/{patient_id}")
def get_stats(patient_id: str, request: Request):
    """Obtiene estadísticas detalladas del paciente activo"""
    return db.get_detailed_stats(current_patient(request))


@router.get("/games/daily-challenge")
def get_daily_challenge():
    """Obtiene el desafío diario"""
    return game_engine.get_daily_challenge()


@router.get("/games/achievements/{patient_id}")
def get_achievements(patient_id: str, request: Request):
    """Lista los logros del paciente activo"""
    return game_engine.get_achievements(current_patient(request))


@router.post("/games/complete-challenge")
def complete_challenge(challenge: ChallengeComplete, request: Request):
    """Marca un desafío como completado (para el paciente activo)"""
    return game_engine.complete_challenge(current_patient(request), challenge.challenge_id, challenge.score)
