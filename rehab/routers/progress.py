"""Progreso, estadísticas y juegos (siempre del paciente activo de la sesión)."""
from fastapi import APIRouter, HTTPException, Request

from ..schemas import ChallengeComplete, ProgressCreate, TherapistLabel
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
    progress_id = db.save_progress(record)

    # Calcular puntos del juego
    points = game_engine.calculate_points(record)

    return {
        "success": True,
        "id": progress_id,
        "points_earned": points,
        "total_points": db.get_total_points(record["patient_id"])
    }


@router.post("/progress/{progress_id}/label")
def label_attempt(progress_id: str, label: TherapistLabel, request: Request):
    """Valoración del terapeuta de un intento: manda sobre la automática en informes y logros."""
    if not db.set_therapist_label(current_patient(request), progress_id, label.correct):
        raise HTTPException(status_code=404, detail="Intento no encontrado")
    return {"success": True, "id": progress_id, "correct": label.correct}


@router.get("/stats/{patient_id}")
def get_stats(patient_id: str, request: Request):
    """Obtiene estadísticas detalladas del paciente activo"""
    return db.get_detailed_stats(current_patient(request))


@router.get("/games/level/{patient_id}")
def get_player_level(patient_id: str, request: Request):
    """Nivel y puntos del paciente activo (tarjeta de nivel de la página de juegos)"""
    return game_engine.get_player_level(current_patient(request))


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
