"""Validación de los cuerpos JSON de la API (antes se aceptaba cualquier dict).

Los campos desconocidos se ignoran (compatibilidad con los clientes actuales) y patient_id se
acepta pero no se usa: el paciente siempre es el de la sesión.
"""
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Body(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class WordCreate(_Body):
    word: str = Field(min_length=1, max_length=100)
    category_id: str = Field(default="custom", min_length=1, max_length=50)
    level: int = Field(default=1, ge=1, le=5)
    phonetic_hint: str = Field(default="", max_length=200)
    tips: str = Field(default="", max_length=500)


class ProgressCreate(_Body):
    word_id: str = Field(min_length=1, max_length=64)
    # Porcentaje 0-100. Algunos juegos envían más de 100 (p. ej. nivel x 20): se acota en vez
    # de rechazar la partida, para no perderla ni distorsionar las medias.
    score: float = Field(ge=0)
    attempt_number: int = Field(default=1, ge=1, le=10_000)
    transcription: str = Field(default="", max_length=500)
    feedback: Optional[Dict[str, Any]] = None
    duration_ms: Optional[float] = Field(default=None, ge=0, le=3_600_000)
    is_correct: Optional[bool] = None  # acierto según el umbral del nivel (lo da el analizador)
    patient_id: Optional[str] = None  # ignorado: se usa el paciente de la sesión

    @field_validator("score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        return min(v, 100.0)

    @field_validator("duration_ms")
    @classmethod
    def whole_ms(cls, v: Optional[float]) -> Optional[float]:
        return None if v is None else round(v)

    def as_record(self, patient_id: str) -> Dict[str, Any]:
        """Datos para database.save_progress / game_engine.calculate_points."""
        data = self.model_dump(exclude_none=True, exclude={"patient_id"})
        if "duration_ms" in data:
            data["duration_ms"] = int(data["duration_ms"])
        data["patient_id"] = patient_id
        return data


class TherapistLabel(_Body):
    # True: bien dicho; False: no; None: quitar la valoración (vuelve a contar la automática)
    correct: Optional[bool] = None


class ChallengeComplete(_Body):
    challenge_id: str = Field(min_length=1, max_length=64)
    score: int = Field(default=0, ge=0, le=100_000)
    patient_id: Optional[str] = None  # ignorado: se usa el paciente de la sesión


class PatientCreate(_Body):
    name: str = Field(min_length=1, max_length=80)
    age: Optional[int] = Field(default=None, ge=0, le=130)
    diagnosis: Optional[str] = Field(default=None, max_length=120)
    therapist: Optional[str] = Field(default=None, max_length=80)
    notes: Optional[str] = Field(default=None, max_length=1000)
