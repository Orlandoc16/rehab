"""
📊 Database Module
SQLAlchemy ORM for improved database management (SQLite + PostgreSQL)
"""

import os
import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pathlib import Path

from sqlalchemy import create_engine, inspect, text, case, Boolean, String, Integer, Float, Text, ForeignKey, DateTime, Index, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, relationship

from word_images import WORD_IMAGES
from syllables import syllabify

# Base configuration
class Base(DeclarativeBase):
    pass

# ==================== MODELS ====================

def _utcnow() -> datetime:
    """UTC actual como datetime naive (mismo valor que el antiguo utcnow(), sin la deprecación)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]

class Patient(Base):
    __tablename__ = 'patients'
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_short_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    age: Mapped[Optional[int]] = mapped_column(Integer)
    diagnosis: Mapped[Optional[str]] = mapped_column(String)
    therapist: Mapped[Optional[str]] = mapped_column(String)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    # Cuándo dio el paciente (o su representante) su consentimiento para que su voz se reconozca
    # con el servicio del navegador (Google en Chrome). Vacío = solo reconocimiento local.
    cloud_speech_consent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Ajustes de la práctica de voz de este paciente (JSON; ver SPEECH_PROFILE_DEFAULTS)
    speech_profile: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=_utcnow, onupdate=_utcnow)
    
    progress: Mapped[List["Progress"]] = relationship("Progress", back_populates="patient")
    achievements: Mapped[List["Achievement"]] = relationship("Achievement", back_populates="patient")
    points: Mapped[List["Points"]] = relationship("Points", back_populates="patient")

class Category(Base):
    __tablename__ = 'categories'
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String)
    icon: Mapped[Optional[str]] = mapped_column(String)
    color: Mapped[Optional[str]] = mapped_column(String)
    order_num: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    
    words: Mapped[List["Word"]] = relationship("Word", back_populates="category")

class Word(Base):
    __tablename__ = 'words'
    __table_args__ = (Index('ix_words_category_level', 'category_id', 'level'),)
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_short_uuid)
    word: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey('categories.id'))
    level: Mapped[int] = mapped_column(Integer, nullable=True, default=1)
    phonetic_hint: Mapped[Optional[str]] = mapped_column(String)
    image_url: Mapped[Optional[str]] = mapped_column(String)
    audio_url: Mapped[Optional[str]] = mapped_column(String)
    tips: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=_utcnow)
    
    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="words")
    progress: Mapped[List["Progress"]] = relationship("Progress", back_populates="word_item")

# Ajustes de voz por paciente. max_recording_s y pause_s: cuándo se corta la grabación (las pausas
# largas de la afasia o los bloqueos del Parkinson la cortaban a mitad de frase); tolerance: ajuste
# del umbral de acierto (negativo = más tolerante).
SPEECH_PROFILE_DEFAULTS = {"disorder": "", "severity": "", "max_recording_s": 12, "pause_s": 1.8, "tolerance": 0}

GAME_PREFIX = "game_"   # los juegos se guardan en Progress con word_id "game_..."


def is_attempt_correct(score: Optional[float], auto_correct: Optional[bool] = None,
                       therapist_correct: Optional[bool] = None) -> bool:
    """Una sola definición de «correcto»: manda el terapeuta, luego el umbral del nivel."""
    if therapist_correct is not None:
        return bool(therapist_correct)
    if auto_correct is not None:
        return bool(auto_correct)
    return (score or 0) >= 70


def _not_game():
    """Filtro SQL: intentos de pronunciación (excluye las partidas de juegos)."""
    return ~Progress.word_id.like(GAME_PREFIX + "%")


def correct_sql():
    """Expresión SQL de is_attempt_correct (para contar aciertos en la base de datos)."""
    return case(
        (Progress.therapist_correct.is_not(None), Progress.therapist_correct),
        (Progress.auto_correct.is_not(None), Progress.auto_correct),
        else_=Progress.score >= 70,
    )


def _legacy_phonetic_hint(word: str) -> str:
    """Pista que generaban las versiones antiguas (incorrecta: "agu-a", "te-ngo"). Solo sirve
    para reconocer y corregir las pistas ya guardadas."""
    vowels = "aeiouáéíóú"
    hint = ""
    syllable = ""
    for char in word:
        syllable += char
        if char.lower() in vowels and len(syllable) > 1:
            hint += syllable + "-"
            syllable = ""
    hint += syllable
    return hint.rstrip("-")


class Progress(Base):
    __tablename__ = 'progress'
    # Todas las consultas de progreso filtran por paciente (y por palabra o por fecha)
    __table_args__ = (
        Index('ix_progress_patient_word', 'patient_id', 'word_id'),
        Index('ix_progress_patient_created', 'patient_id', 'created_at'),
    )
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_short_uuid)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey('patients.id'), nullable=False)
    word_id: Mapped[str] = mapped_column(String, ForeignKey('words.id'), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=True, default=1)
    score: Mapped[Optional[float]] = mapped_column(Float)
    transcription: Mapped[Optional[str]] = mapped_column(Text)
    feedback: Mapped[Optional[str]] = mapped_column(Text)  # JSON string
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    # Acierto según el umbral del nivel (el del analizador) y, si la hay, la valoración del
    # terapeuta, que manda. Los intentos antiguos no tienen ninguno: se usa score >= 70.
    auto_correct: Mapped[Optional[bool]] = mapped_column(Boolean)
    therapist_correct: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=_utcnow)

    patient: Mapped["Patient"] = relationship("Patient", back_populates="progress")
    word_item: Mapped["Word"] = relationship("Word", back_populates="progress")

class Achievement(Base):
    __tablename__ = 'achievements'
    __table_args__ = (Index('ix_achievements_patient', 'patient_id'),)
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_short_uuid)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey('patients.id'), nullable=False)
    achievement_type: Mapped[str] = mapped_column(String, nullable=False)
    achievement_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON string
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=_utcnow)
    
    patient: Mapped["Patient"] = relationship("Patient", back_populates="achievements")

class Points(Base):
    __tablename__ = 'points'
    __table_args__ = (Index('ix_points_patient', 'patient_id'),)
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_short_uuid)
    patient_id: Mapped[str] = mapped_column(String, ForeignKey('patients.id'), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=_utcnow)
    
    patient: Mapped["Patient"] = relationship("Patient", back_populates="points")

class AACCategory(Base):
    __tablename__ = 'aac_categories'
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String)
    icon: Mapped[Optional[str]] = mapped_column(String)
    order_num: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    
    pictograms: Mapped[List["AACPictogram"]] = relationship("AACPictogram", back_populates="category")

class AACPictogram(Base):
    __tablename__ = 'aac_pictograms'
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    category_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey('aac_categories.id'))
    label: Mapped[str] = mapped_column(String, nullable=False)
    icon_src: Mapped[Optional[str]] = mapped_column(String)
    grammar: Mapped[Optional[str]] = mapped_column(Text) # JSON string
    default_phrase: Mapped[Optional[str]] = mapped_column(String)
    
    category: Mapped[Optional["AACCategory"]] = relationship("AACCategory", back_populates="pictograms")

class Therapist(Base):
    """Terapeuta con acceso a la app. Contraseña con scrypt (ver auth.py)."""
    __tablename__ = 'therapists'

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_short_uuid)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=_utcnow)


class AuthSession(Base):
    """Sesión iniciada. Se guarda el hash del token (la cookie lleva el token)."""
    __tablename__ = 'auth_sessions'

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    therapist_id: Mapped[str] = mapped_column(String, ForeignKey('therapists.id'), nullable=False)
    patient_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey('patients.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def word_image_key(category_id: Optional[str], word: str) -> str:
    """Clave de WORD_IMAGES: «categoría/palabra» en minúsculas, sin tildes ni signos (la ñ se mantiene)."""
    text = unicodedata.normalize("NFD", word.lower().strip())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn" or c == "̃")  # ̃: la virgulilla de la ñ
    text = re.sub(r"[¿?¡!.,]", "", unicodedata.normalize("NFC", text)).strip()
    return f"{category_id}/{text}"


# Ilustraciones de pictogramas: TODAS de ARASAAC, para que el tablero tenga un estilo uniforme.
# Autor: Sergio Palao. Origen: ARASAAC (https://arasaac.org). Licencia: CC BY-NC-SA 4.0
# (uso no comercial, con atribución). Elegidos a mano entre varios candidatos; cada archivo
# se llama como su identificador en ARASAAC. Ver static/pictograms/arasaac/LICENSE.txt
# Los c_*.webp son composiciones A COLOR de piezas de ARASAAC (tools/compose_pictograms.py)
# para conceptos que ARASAAC solo tiene en blanco y negro (parentescos, vecino, acomodarme).
# Los pictogramas aac_* vienen del antiguo script de vocabulario: solo se aplican si existen.
PICTOGRAM_IMAGES = {
    # Acciones
    "walk": "/static/pictograms/arasaac/32214.webp",  # Caminar
    "rest": "/static/pictograms/arasaac/31937.webp",  # Descansar
    "write": "/static/pictograms/arasaac/2380.webp",  # Escribir
    "read": "/static/pictograms/arasaac/31680.webp",  # Leer
    "call": "/static/pictograms/arasaac/34405.webp",  # Llamar
    "listen": "/static/pictograms/arasaac/29718.webp",  # Música
    "paint": "/static/pictograms/arasaac/5574.webp",  # Pintar
    "pray": "/static/pictograms/arasaac/24368.webp",  # Rezar
    "go_out": "/static/pictograms/arasaac/28689.webp",  # Salir
    "watch_tv": "/static/pictograms/arasaac/2782.webp",  # Ver TV
    # Animales
    "aac_horse": "/static/pictograms/arasaac/2294.webp",  # Caballo
    "aac_cat": "/static/pictograms/arasaac/7114.webp",  # Gato
    "aac_dog": "/static/pictograms/arasaac/7202.webp",  # Perro
    "aac_fish": "/static/pictograms/arasaac/2520.webp",  # Pez
    "aac_bird": "/static/pictograms/arasaac/2490.webp",  # Pájaro
    # Aseo
    "groom": "/static/pictograms/arasaac/5361.webp",  # Afeitarme
    "shower": "/static/pictograms/arasaac/2371.webp",  # Bañarme
    "nails": "/static/pictograms/arasaac/10153.webp",  # Cortar Uñas
    "brush_teeth": "/static/pictograms/arasaac/31880.webp",  # Dientes
    "wash_hands": "/static/pictograms/arasaac/8975.webp",  # Lavar Manos
    "comb": "/static/pictograms/arasaac/2512.webp",  # Peinarme
    "change_clothes": "/static/pictograms/arasaac/2781.webp",  # Ropa
    # Asistencia
    "position": "/static/pictograms/arasaac/c_acomodarme.webp",  # Acomodarme (compuesto)
    "tv_remote": "/static/pictograms/arasaac/26182.webp",  # Control TV
    "glasses": "/static/pictograms/arasaac/3329.webp",  # Lentes
    "help_up": "/static/pictograms/arasaac/6548.webp",  # Levantarme
    "light_on": "/static/pictograms/arasaac/8103.webp",  # Luz
    "sit_down": "/static/pictograms/arasaac/25082.webp",  # Sentarme
    "quiet": "/static/pictograms/arasaac/5936.webp",  # Silencio
    "wheelchair": "/static/pictograms/arasaac/6212.webp",  # Silla Ruedas
    "phone": "/static/pictograms/arasaac/26479.webp",  # Teléfono
    # Bebida
    "water": "/static/pictograms/arasaac/2248.webp",  # Agua
    "coffee": "/static/pictograms/arasaac/2296.webp",  # Café
    "juice": "/static/pictograms/arasaac/2624.webp",  # Jugo
    "milk": "/static/pictograms/arasaac/2445.webp",  # Leche
    "tea": "/static/pictograms/arasaac/2429.webp",  # Té
    # Casa
    "aac_bed": "/static/pictograms/arasaac/2304.webp",  # Cama
    "aac_door": "/static/pictograms/arasaac/3244.webp",  # Puerta
    "aac_chair": "/static/pictograms/arasaac/3155.webp",  # Silla
    "aac_tv": "/static/pictograms/arasaac/25498.webp",  # TV
    # Comida
    "rice": "/static/pictograms/arasaac/39387.webp",  # Arroz
    "meat": "/static/pictograms/arasaac/2316.webp",  # Carne
    "salad": "/static/pictograms/arasaac/2377.webp",  # Ensalada
    "fruit": "/static/pictograms/arasaac/4653.webp",  # Fruta
    "hamb": "/static/pictograms/arasaac/2419.webp",  # Hamburguesa
    "bread": "/static/pictograms/arasaac/2494.webp",  # Pan
    "fish": "/static/pictograms/arasaac/2519.webp",  # Pescado
    "chicken": "/static/pictograms/arasaac/24815.webp",  # Pollo
    "dessert": "/static/pictograms/arasaac/7216.webp",  # Postre
    "soup": "/static/pictograms/arasaac/2573.webp",  # Sopa
    # Gente
    "friend": "/static/pictograms/arasaac/8487.webp",  # Amigo
    "caregiver": "/static/pictograms/arasaac/14662.webp",  # Cuidador
    "doctor": "/static/pictograms/arasaac/2467.webp",  # Doctor
    "nurse": "/static/pictograms/arasaac/2375.webp",  # Enfermera
    "wife": "/static/pictograms/arasaac/c_esposa.webp",  # Esposa (compuesto)
    "husband": "/static/pictograms/arasaac/c_esposo.webp",  # Esposo (compuesto)
    "family": "/static/pictograms/arasaac/2392.webp",  # Familia
    "daughter": "/static/pictograms/arasaac/c_hija.webp",  # Hija (compuesto)
    "son": "/static/pictograms/arasaac/c_hijo.webp",  # Hijo (compuesto)
    "granddaughter": "/static/pictograms/arasaac/c_nieta.webp",  # Nieta (compuesto)
    "grandson": "/static/pictograms/arasaac/c_nieto.webp",  # Nieto (compuesto)
    "priest": "/static/pictograms/arasaac/30822.webp",  # Sacerdote
    "neighbor": "/static/pictograms/arasaac/c_vecino.webp",  # Vecino (compuesto)
    # Lugares
    "aac_home_place": "/static/pictograms/arasaac/2317.webp",  # Casa
    "aac_hospital": "/static/pictograms/arasaac/29859.webp",  # Doctor
    "aac_park": "/static/pictograms/arasaac/2859.webp",  # Parque
    "aac_store": "/static/pictograms/arasaac/35695.webp",  # Tienda
    # Necesidad
    "hearing_aid": "/static/pictograms/arasaac/34278.webp",  # Audífono
    "help_gen": "/static/pictograms/arasaac/12252.webp",  # Ayuda
    "toilet": "/static/pictograms/arasaac/2430.webp",  # Baño
    "heat": "/static/pictograms/arasaac/35561.webp",  # Calor
    "charge_phone": "/static/pictograms/arasaac/34939.webp",  # Cargar Celular
    "company": "/static/pictograms/arasaac/28187.webp",  # Compañía
    "dentures": "/static/pictograms/arasaac/37170.webp",  # Dentadura
    "sleep": "/static/pictograms/arasaac/2369.webp",  # Dormir
    "cold": "/static/pictograms/arasaac/35557.webp",  # Frío
    "medicine": "/static/pictograms/arasaac/8163.webp",  # Medicina
    "pillbox": "/static/pictograms/arasaac/39869.webp",  # Pastillero
    # Respuestas
    "bye": "/static/pictograms/arasaac/5896.webp",  # Adiós
    "good": "/static/pictograms/arasaac/5397.webp",  # Bien
    "wait": "/static/pictograms/arasaac/8109.webp",  # Espera
    "thanks": "/static/pictograms/arasaac/8128.webp",  # Gracias
    "hello": "/static/pictograms/arasaac/6009.webp",  # Hola
    "bad": "/static/pictograms/arasaac/5504.webp",  # Mal
    "more": "/static/pictograms/arasaac/3220.webp",  # Más
    "no": "/static/pictograms/arasaac/5526.webp",  # No
    "dont_know": "/static/pictograms/arasaac/7180.webp",  # No sé
    "please": "/static/pictograms/arasaac/38907.webp",  # Por favor
    "yes": "/static/pictograms/arasaac/5584.webp",  # Sí
    "maybe": "/static/pictograms/arasaac/11696.webp",  # Tal vez
    "finished": "/static/pictograms/arasaac/28429.webp",  # Terminé
    # Ropa
    "aac_shirt": "/static/pictograms/arasaac/13640.webp",  # Camisa
    "aac_glasses": "/static/pictograms/arasaac/3329.webp",  # Lentes
    "aac_shoes": "/static/pictograms/arasaac/2622.webp",  # Zapatos
    # Sentir
    "bored": "/static/pictograms/arasaac/31744.webp",  # Aburrido
    "tired": "/static/pictograms/arasaac/31925.webp",  # Cansado
    "pain": "/static/pictograms/arasaac/2367.webp",  # Dolor
    "pain_arm": "/static/pictograms/arasaac/28773.webp",  # Dolor Brazo
    "pain_head": "/static/pictograms/arasaac/28753.webp",  # Dolor Cabeza
    "pain_back": "/static/pictograms/arasaac/28785.webp",  # Dolor Espalda
    "pain_stomach": "/static/pictograms/arasaac/28765.webp",  # Dolor Panza
    "pain_chest": "/static/pictograms/arasaac/28781.webp",  # Dolor Pecho
    "pain_leg": "/static/pictograms/arasaac/28769.webp",  # Dolor Pierna
    "angry": "/static/pictograms/arasaac/31884.webp",  # Enojado
    "happy": "/static/pictograms/arasaac/32123.webp",  # Feliz
    "pain_throat": "/static/pictograms/arasaac/28761.webp",  # Garganta
    "dizzy": "/static/pictograms/arasaac/31795.webp",  # Mareado
    "scared": "/static/pictograms/arasaac/31896.webp",  # Miedo
    "sad": "/static/pictograms/arasaac/31939.webp",  # Triste
}

# ==================== DATABASE MANAGER ====================

class Database:
    """Database Manager using SQLAlchemy"""
    
    def __init__(self):
        # Determine DB URL: Use Env var or fallback to local sqlite
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            base_dir = Path(__file__).parent
            data_dir = base_dir / "data"
            data_dir.mkdir(exist_ok=True)
            self.db_url = f"sqlite:///{data_dir / 'rehab_voice.db'}"
            print(f"📂 Using Local SQLite: {self.db_url}")
        else:
            print(f"🐘 Using Database: {self.db_url}")
        
        self.engine = create_engine(self.db_url, connect_args={"check_same_thread": False} if "sqlite" in self.db_url else {})
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def get_db(self):
        """Get a database session - el llamador es responsable de cerrarla"""
        return self.SessionLocal()
    
    def get_db_context(self):
        """Context manager para manejo seguro de sesiones"""
        from contextlib import contextmanager
        
        @contextmanager
        def session_scope():
            session = self.SessionLocal()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        
        return session_scope()
            
    def initialize(self):
        """Initialize database tables and default data"""
        Base.metadata.create_all(bind=self.engine)
        self._add_missing_columns()
        # create_all solo crea índices en tablas nuevas: crearlos también en bases ya existentes
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                index.create(bind=self.engine, checkfirst=True)
        self._insert_initial_data()
        self._seed_aac_data()
        self._apply_word_images()
        self._refresh_phonetic_hints()

    # Columnas añadidas después de crear la tabla: create_all no las añade a bases ya existentes
    _NEW_COLUMNS = {
        "patients": {"cloud_speech_consent_at": "TIMESTAMP", "speech_profile": "TEXT"},
        "progress": {"auto_correct": "BOOLEAN", "therapist_correct": "BOOLEAN"},
    }

    def _add_missing_columns(self):
        inspector = inspect(self.engine)
        for table, columns in self._NEW_COLUMNS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    with self.engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
                    print(f"🛠️ Columna {table}.{name} añadida")

    def _apply_word_images(self):
        """Imagen de ARASAAC de cada palabra de práctica (WORD_IMAGES). También actualiza
        bases de datos existentes; las palabras sin imagen conocida no se tocan."""
        session = self.SessionLocal()
        try:
            changed = 0
            for word in session.query(Word).all():
                image = WORD_IMAGES.get(word_image_key(word.category_id, word.word))
                if image and word.image_url != image:
                    word.image_url = image
                    changed += 1
            session.commit()
            if changed:
                print(f"🖼️ Imágenes de {changed} palabras de práctica actualizadas")
        finally:
            session.close()
        
    def _refresh_phonetic_hints(self):
        """Corrige las pistas silábicas creadas con el algoritmo antiguo ("agu-a" -> "a-gua").
        Solo toca las que coinciden con lo que generaba aquel: las escritas a mano se respetan."""
        session = self.SessionLocal()
        try:
            changed = 0
            for word in session.query(Word).all():
                if word.phonetic_hint == _legacy_phonetic_hint(word.word or ""):
                    new_hint = syllabify(word.word or "")
                    if new_hint != word.phonetic_hint:
                        word.phonetic_hint = new_hint
                        changed += 1
            session.commit()
            if changed:
                print(f"🔤 Separación silábica corregida en {changed} palabras")
        finally:
            session.close()

    def _seed_aac_data(self):
        """Populate initial AAC data"""
        session = self.SessionLocal()
        try:
            print("🌱 Seeding AAC data...")
            
            # Categories
            cats = [
                ("food", "Comida", "#FFF3E0", "fa-utensils", 1),
                ("drink", "Bebida", "#E0F7FA", "fa-glass-water", 2),
                ("feelings", "Sentir", "#F3E5F5", "fa-face-smile", 3),
                ("needs", "Necesidad", "#FFEBEE", "fa-hand-holding-heart", 4),
                ("actions", "Acciones", "#E8F5E9", "fa-person-walking", 5),
                ("people", "Gente", "#E3F2FD", "fa-users", 6),
                # New Categories
                ("assistance", "Asistencia", "#FFF8E1", "fa-bell", 7),
                ("hygiene", "Aseo", "#E0F2F1", "fa-soap", 8),
                ("responses", "Respuestas", "#14b8a6", "fa-comments", 9)
            ]
            
            for cid, label, color, icon, order in cats:
                # Check if exists to avoid duplicates/errors if re-running
                if not session.get(AACCategory, cid):
                    session.add(AACCategory(id=cid, label=label, color=color, icon=icon, order_num=order))
            
            # Pictograms
            items = [
                # COMIDA
                ("hamb", "food", "Hamburguesa", "fa-burger", {"noun": "hamburguesa", "gender": "f"}, "Quiero hamburguesa"),
                ("soup", "food", "Sopa", "fa-bowl-food", {"noun": "sopa", "gender": "f"}, "Quiero sopa"),
                ("salad", "food", "Ensalada", "fa-leaf", {"noun": "ensalada", "gender": "f"}, "Quiero ensalada"),
                ("fruit", "food", "Fruta", "fa-apple-whole", {"noun": "fruta", "gender": "f"}, "Quiero fruta"),
                ("bread", "food", "Pan", "fa-bread-slice", {"noun": "pan", "gender": "m"}, "Quiero pan"),
                ("chicken", "food", "Pollo", "fa-drumstick-bite", {"noun": "pollo", "gender": "m"}, "Quiero pollo"),
                ("fish", "food", "Pescado", "fa-fish", {"noun": "pescado", "gender": "m"}, "Quiero pescado"),
                ("meat", "food", "Carne", "fa-bacon", {"noun": "carne", "gender": "f"}, "Quiero carne"),
                ("rice", "food", "Arroz", "fa-bowl-rice", {"noun": "arroz", "gender": "m"}, "Quiero arroz"),
                ("dessert", "food", "Postre", "fa-cookie", {"noun": "postre", "gender": "m"}, "Quiero postre"),
                
                # BEBIDA
                ("water", "drink", "Agua", "fa-glass-water", {"noun": "agua", "gender": "m"}, "Quiero agua"),
                ("coffee", "drink", "Café", "fa-mug-hot", {"noun": "café", "gender": "m"}, "Quiero café"),
                ("tea", "drink", "Té", "fa-mug-saucer", {"noun": "té", "gender": "m"}, "Quiero té"),
                ("juice", "drink", "Jugo", "fa-whiskey-glass", {"noun": "jugo", "gender": "m"}, "Quiero jugo"),
                ("milk", "drink", "Leche", "fa-glass-water", {"noun": "leche", "gender": "f"}, "Quiero leche"),
                
                # SENTIMIENTOS (Icons)
                ("happy", "feelings", "Feliz", "fa-face-laugh", {"adj": "feliz"}, "Estoy feliz"),
                ("sad", "feelings", "Triste", "fa-face-sad-tear", {"adj": "triste"}, "Estoy triste"),
                ("pain", "feelings", "Dolor", "fa-face-grimace", {"noun": "dolor"}, "Tengo dolor"),
                ("tired", "feelings", "Cansado", "fa-face-tired", {"adj": "cansado"}, "Estoy cansado"),
                # Extended Feelings
                ("angry", "feelings", "Enojado", "fa-face-angry", {"adj": "enojado"}, "Estoy enojado"),
                ("scared", "feelings", "Miedo", "fa-face-flushed", {"noun": "miedo"}, "Tengo miedo"),
                ("bored", "feelings", "Aburrido", "fa-face-rolling-eyes", {"adj": "aburrido"}, "Estoy aburrido"),
                ("dizzy", "feelings", "Mareado", "fa-arrows-spin", {"adj": "mareado"}, "Me siento mareado"),
                # Specific Pains
                ("pain_head", "feelings", "Dolor Cabeza", "fa-head-side-virus", {"noun": "dolor de cabeza"}, "Me duele la cabeza"),
                ("pain_chest", "feelings", "Dolor Pecho", "fa-heart-pulse", {"noun": "dolor de pecho"}, "Me duele el pecho"),
                ("pain_stomach", "feelings", "Dolor Panza", "fa-hand-holding-medical", {"noun": "dolor de panza"}, "Me duele la panza"),
                ("pain_back", "feelings", "Dolor Espalda", "fa-person-cane", {"noun": "dolor de espalda"}, "Me duele la espalda"),
                ("pain_throat", "feelings", "Garganta", "fa-head-side-cough", {"noun": "dolor de garganta"}, "Me duele la garganta"),
                ("pain_arm", "feelings", "Dolor Brazo", "fa-hand-dots", {"noun": "dolor de brazo"}, "Me duele el brazo"),
                ("pain_leg", "feelings", "Dolor Pierna", "fa-crutch", {"noun": "dolor de pierna"}, "Me duele la pierna"),
                
                # NECESIDADES (Icons)
                ("toilet", "needs", "Baño", "fa-restroom", {}, "Necesito ir al baño"),
                ("sleep", "needs", "Dormir", "fa-bed", {}, "Necesito dormir"),
                ("cold", "needs", "Frío", "fa-snowflake", {}, "Tengo frío"),
                ("heat", "needs", "Calor", "fa-temperature-full", {}, "Tengo calor"),
                # Extended Needs (Senior Focused)
                ("medicine", "needs", "Medicina", "fa-pills", {}, "Necesito mi medicina"),
                ("pillbox", "needs", "Pastillero", "fa-tablets", {}, "¿Dónde está mi pastillero?"),
                ("hearing_aid", "needs", "Audífono", "fa-ear-listen", {}, "Necesito mi audífono"),
                ("dentures", "needs", "Dentadura", "fa-teeth-open", {}, "Necesito mi dentadura"),
                ("company", "needs", "Compañía", "fa-user-group", {}, "Quiero compañía"),
                ("charge_phone", "needs", "Cargar Celular", "fa-battery-quarter", {}, "Necesito cargar mi celular"),
                ("help_gen", "needs", "Ayuda", "fa-hand-holding-hand", {}, "Necesito ayuda por favor"),
                
                # ACCIONES (Icons)
                ("walk", "actions", "Caminar", "fa-person-walking", {}, "Quiero caminar"),
                ("watch_tv", "actions", "Ver TV", "fa-tv", {}, "Quiero ver televisión"),
                ("listen", "actions", "Música", "fa-music", {}, "Quiero escuchar música"),
                # Extended Actions
                ("read", "actions", "Leer", "fa-book-open", {}, "Quiero leer un libro"),
                ("write", "actions", "Escribir", "fa-pen", {}, "Quiero escribir"),
                ("paint", "actions", "Pintar", "fa-palette", {}, "Quiero pintar"),
                ("rest", "actions", "Descansar", "fa-couch", {}, "Quiero descansar un rato"),
                ("go_out", "actions", "Salir", "fa-door-open", {}, "Quiero salir afuera"),
                ("call", "actions", "Llamar", "fa-phone-volume", {}, "Quiero hacer una llamada"),
                ("pray", "actions", "Rezar", "fa-hands-praying", {}, "Quiero rezar"),
                
                # GENTE (Icons)
                ("doctor", "people", "Doctor", "fa-user-doctor", {}, "Necesito al doctor"),
                ("nurse", "people", "Enfermera", "fa-user-nurse", {}, "Necesito a la enfermera"),
                ("family", "people", "Familia", "fa-people-roof", {}, "Quiero ver a mi familia"),
                # Senior Focused People
                ("son", "people", "Hijo", "fa-person", {"noun": "hijo", "gender": "m"}, "Quiero ver a mi hijo"),
                ("daughter", "people", "Hija", "fa-person-dress", {"noun": "hija", "gender": "f"}, "Quiero ver a mi hija"),
                ("husband", "people", "Esposo", "fa-ring", {"noun": "esposo", "gender": "m"}, "Quiero ver a mi esposo"),
                ("wife", "people", "Esposa", "fa-heart", {"noun": "esposa", "gender": "f"}, "Quiero ver a mi esposa"),
                ("grandson", "people", "Nieto", "fa-child", {"noun": "nieto", "gender": "m"}, "Quiero ver a mi nieto"),
                ("granddaughter", "people", "Nieta", "fa-child-dress", {"noun": "nieta", "gender": "f"}, "Quiero ver a mi nieta"),
                ("caregiver", "people", "Cuidador", "fa-hand-holding-heart", {"noun": "cuidador", "gender": "m"}, "Necesito a mi cuidador"),
                ("friend", "people", "Amigo", "fa-user-group", {"noun": "amigo", "gender": "m"}, "Quiero ver a un amigo"),
                ("neighbor", "people", "Vecino", "fa-house-user", {"noun": "vecino", "gender": "m"}, "Quiero ver a mi vecino"),
                ("priest", "people", "Sacerdote", "fa-cross", {"noun": "sacerdote", "gender": "m"}, "Quiero ver al sacerdote"),
                
                # RESPUESTAS COMUNES (Icons)
                ("yes", "responses", "Sí", "fa-thumbs-up", {}, "Sí"),
                ("no", "responses", "No", "fa-thumbs-down", {}, "No"),
                ("thanks", "responses", "Gracias", "fa-hands-clapping", {}, "Gracias"),
                ("please", "responses", "Por favor", "fa-hand-sparkles", {}, "Por favor"),
                ("dont_know", "responses", "No sé", "fa-question", {}, "No sé"),
                ("maybe", "responses", "Tal vez", "fa-scale-balanced", {}, "Tal vez"),
                ("good", "responses", "Bien", "fa-face-smile-beam", {}, "Estoy bien"),
                ("bad", "responses", "Mal", "fa-face-frown", {}, "Estoy mal"),
                ("hello", "responses", "Hola", "fa-hand", {}, "Hola"),
                ("bye", "responses", "Adiós", "fa-person-walking-arrow-right", {}, "Adiós"),
                ("wait", "responses", "Espera", "fa-hourglass-half", {}, "Espera un momento"),
                ("more", "responses", "Más", "fa-plus", {}, "Quiero más"),
                ("finished", "responses", "Terminé", "fa-check", {}, "Ya terminé"),

                # ASISTENCIA (Senior Assistance)
                ("help_up", "assistance", "Levantarme", "fa-person-walking-arrow-right", {}, "Ayúdame a levantarme, por favor"),
                ("sit_down", "assistance", "Sentarme", "fa-chair", {}, "Quiero sentarme"),
                ("position", "assistance", "Acomodarme", "fa-arrows-rotate", {}, "Necesito cambiar de posición"),
                ("wheelchair", "assistance", "Silla Ruedas", "fa-wheelchair", {}, "Necesito mi silla de ruedas"),
                ("glasses", "assistance", "Lentes", "fa-glasses", {}, "¿Dónde están mis lentes?"),
                ("light_on", "assistance", "Luz", "fa-lightbulb", {}, "Prende la luz, por favor"),
                ("tv_remote", "assistance", "Control TV", "fa-gamepad", {}, "Pásame el control de la TV"),
                ("phone", "assistance", "Teléfono", "fa-phone", {}, "Quiero usar el teléfono"),
                ("quiet", "assistance", "Silencio", "fa-volume-xmark", {}, "Necesito silencio, por favor"),

                # ASEO (Personal Hygiene)
                ("shower", "hygiene", "Bañarme", "fa-shower", {}, "Quiero bañarme"),
                ("wash_hands", "hygiene", "Lavar Manos", "fa-hands-bubbles", {}, "Quiero lavarme las manos"),
                ("brush_teeth", "hygiene", "Dientes", "fa-tooth", {}, "Quiero lavarme los dientes"),
                ("comb", "hygiene", "Peinarme", "fa-wand-magic-sparkles", {}, "Ayúdame a peinarme"),
                ("groom", "hygiene", "Afeitarme", "fa-user-tie", {}, "Necesito afeitarme"),
                ("change_clothes", "hygiene", "Ropa", "fa-shirt", {}, "Quiero cambiarme de ropa"),
                ("nails", "hygiene", "Cortar Uñas", "fa-scissors", {}, "Necesito cortarme las uñas")
            ]
            
            for pid, cid, label, icon, gram, phrase in items:
                if not session.get(AACPictogram, pid):
                    session.add(AACPictogram(
                        id=pid, 
                        category_id=cid, 
                        label=label, 
                        icon_src=icon, 
                        grammar=json.dumps(gram), 
                        default_phrase=phrase
                    ))
            
            session.flush()

            # Pictogramas con ilustración: la imagen sustituye al icono genérico.
            # (También actualiza bases de datos antiguas que apuntaban a los .png.)
            for pid, image in PICTOGRAM_IMAGES.items():
                picto = session.get(AACPictogram, pid)
                if picto is not None and picto.icon_src != image:
                    picto.icon_src = image

            session.commit()
            print("✅ AAC data seeded (Updated)")
            
        except Exception as e:
            session.rollback()
            print(f"❌ Error seeding AAC data: {e}")
        finally:
            session.close()

        
    def _insert_initial_data(self):
        """Populate initial categories and words if empty"""
        session = self.SessionLocal()
        try:
            if session.query(Category).count() > 0:
                return

            print("🌱 Seeding initial data...")
            
            # Categories
            categories_data = [
                ("basic_needs", "Necesidades Básicas", "Palabras esenciales del día a día", "🏠", "#4CAF50", 1),
                ("food_drink", "Comida y Bebida", "Alimentos y bebidas comunes", "🍽️", "#FF9800", 2),
                ("body_health", "Cuerpo y Salud", "Partes del cuerpo y salud", "❤️", "#F44336", 3),
                ("emotions", "Emociones", "Expresar sentimientos", "😊", "#9C27B0", 4),
                ("family", "Familia", "Miembros de la familia", "👨‍👩‍👧", "#2196F3", 5),
                ("places", "Lugares", "Lugares comunes", "📍", "#00BCD4", 6),
                ("time", "Tiempo", "Expresiones de tiempo", "🕐", "#607D8B", 7),
                ("actions", "Acciones", "Verbos comunes", "🏃", "#8BC34A", 8),
                ("phrases", "Frases Comunes", "Frases útiles completas", "💬", "#E91E63", 9),
            ]
            
            for cat_id, name, desc, icon, color, order in categories_data:
                cat = Category(id=cat_id, name=name, description=desc, icon=icon, color=color, order_num=order)
                session.add(cat)
            
            # Words Data
            words_data = {
                "basic_needs": {
                    1: ["sí", "no", "hola", "adiós", "gracias", "por favor", "ayuda", "agua", "baño"],
                    2: ["quiero", "necesito", "tengo", "puedo", "dame", "ven", "espera", "más", "menos"],
                    3: ["quiero agua", "necesito ayuda", "gracias por favor", "hola buenos días", "adiós hasta luego"],
                    4: ["necesito ir al baño", "quiero más agua", "muchas gracias por tu ayuda", "buenos días cómo estás"],
                    5: ["me gustaría un poco de agua por favor", "necesito que me ayudes con algo", "muchas gracias por toda tu ayuda"]
                },
                "food_drink": {
                    1: ["pan", "leche", "café", "té", "jugo", "sopa", "arroz", "pollo", "fruta"],
                    2: ["comida", "bebida", "desayuno", "almuerzo", "cena", "merienda", "hambre", "sed"],
                    3: ["quiero comer", "tengo hambre", "tengo sed", "está rico", "no me gusta"],
                    4: ["quiero un vaso de agua", "me gustaría comer pan", "el desayuno está listo"],
                    5: ["me gustaría desayunar café con leche y pan", "la comida está muy rica gracias"]
                },
                # ... (Keeping it brief for the rewrite, but ideally all data should be here)
                # Adding a subset to ensure functionality without huge file size
                 "body_health": {
                    1: ["mano", "pie", "cabeza", "ojo", "boca", "nariz", "oreja", "brazo", "pierna"],
                },
                 "emotions": {
                    1: ["feliz", "triste", "enojado", "miedo", "amor", "alegría", "calma", "paz"],
                }
            }

            for cat_id, levels in words_data.items():
                for level, words in levels.items():
                    for w_text in words:
                        word = Word(
                            word=w_text,
                            category_id=cat_id,
                            level=level,
                            phonetic_hint=self._generate_phonetic_hint(w_text)
                        )
                        session.add(word)
                        
            # Create default patient
            default_patient = Patient(
                id="default",
                name="Paciente Demo",
                age=50,
                diagnosis="Rehabilitación general"
            )
            session.add(default_patient)
            
            session.commit()
            print("✅ Initial data seeded")
            
        except Exception as e:
            session.rollback()
            print(f"❌ Error seeding data: {e}")
        finally:
            session.close()

    def _generate_phonetic_hint(self, word: str) -> str:
        """Separación silábica que se muestra bajo la palabra ("por fa-vor")."""
        return syllabify(word)

    # ==================== QUERY METHODS ====================

    def get_categories(self) -> List[Dict]:
        session = self.SessionLocal()
        try:
            cats = session.query(Category).order_by(Category.order_num).all()
            return [self._to_dict(c) for c in cats]
        finally:
            session.close()

    def get_words(self, category_id: str, level: Optional[int] = None) -> List[Dict]:
        session = self.SessionLocal()
        try:
            query = session.query(Word).filter(Word.category_id == category_id)
            if level:
                query = query.filter(Word.level == level)
            
            words = query.order_by(Word.level, Word.word).all()
            return [self._to_dict(w) for w in words]
        finally:
            session.close()
            
    def get_all_words(self) -> List[Dict]:
        session = self.SessionLocal()
        try:
            words = session.query(Word).all()
            return [self._to_dict(w) for w in words]
        finally:
            session.close()

    def add_word(self, word_data: Dict) -> str:
        session = self.SessionLocal()
        try:
            new_word = Word(
                word=word_data.get("word"),
                category_id=word_data.get("category_id", "custom"),
                level=word_data.get("level", 1),
                phonetic_hint=word_data.get("phonetic_hint") or syllabify(word_data.get("word") or ""),
                tips=word_data.get("tips", ""),
            )
            new_word.image_url = WORD_IMAGES.get(word_image_key(new_word.category_id, new_word.word or ""))
            session.add(new_word)
            session.commit()
            return new_word.id
        finally:
            session.close()

    # ==================== PROGRESS METHODS ====================

    def save_progress(self, data: Dict) -> str:
        session = self.SessionLocal()
        try:
            new_progress = Progress(
                patient_id=data.get("patient_id", "default"),
                word_id=data.get("word_id"),
                attempt_number=data.get("attempt_number", 1),
                score=data.get("score"),
                transcription=data.get("transcription"),
                feedback=json.dumps(data.get("feedback", {})),
                duration_ms=data.get("duration_ms"),
                auto_correct=data.get("is_correct"),
            )
            session.add(new_progress)
            session.commit()
            return new_progress.id
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_progress(self, patient_id: str) -> Dict:
        """Resumen de progreso del paciente: totales, por categoría y últimos intentos.

        Tres consultas agrupadas (antes eran ~52: varias por categoría y una por intento reciente).
        """
        session = self.SessionLocal()
        try:
            # Totales
            total_attempts, unique_words, avg_score, best_score = session.query(
                func.count(Progress.id),
                func.count(func.distinct(Progress.word_id)),
                func.avg(Progress.score),
                func.max(Progress.score),
            ).filter(Progress.patient_id == patient_id, _not_game()).one()

            # Por categoría (solo intentos sobre palabras existentes, como antes)
            practiced = {
                category_id: (words_practiced, cat_avg)
                for category_id, words_practiced, cat_avg in session.query(
                    Word.category_id,
                    func.count(func.distinct(Progress.word_id)),
                    func.avg(Progress.score),
                ).join(Word, Progress.word_id == Word.id)
                .filter(Progress.patient_id == patient_id, _not_game())
                .group_by(Word.category_id)
            }
            totals = dict(session.query(Word.category_id, func.count(Word.id)).group_by(Word.category_id).all())

            by_category = []
            for cat in session.query(Category).order_by(Category.order_num).all():
                words_practiced, cat_avg = practiced.get(cat.id, (0, None))
                by_category.append({
                    "id": cat.id,
                    "name": cat.name,
                    "icon": cat.icon,
                    "words_practiced": words_practiced,
                    "avg_score": round(cat_avg or 0, 1),
                    "total_words": totals.get(cat.id, 0)
                })

            # Últimos intentos, con la palabra (una sola consulta)
            recent_list = []
            for r, word_text in session.query(Progress, Word.word)                    .outerjoin(Word, Progress.word_id == Word.id)                    .filter(Progress.patient_id == patient_id, _not_game())                    .order_by(Progress.created_at.desc()).limit(20).all():
                r_dict = self._to_dict(r)
                r_dict['word'] = word_text if word_text is not None else "Unknown"
                recent_list.append(r_dict)

            return {
                "patient_id": patient_id,
                "stats": {
                    "total_attempts": total_attempts or 0,
                    "unique_words": unique_words or 0,
                    "average_score": round(avg_score or 0, 1),
                    "best_score": best_score or 0
                },
                "by_category": by_category,
                "recent_attempts": recent_list
            }
        finally:
            session.close()

    def get_detailed_stats(self, patient_id: str) -> Dict:
        session = self.SessionLocal()
        try:
             # Daily progress (last 30 days)
             # Note: SQLite and Postgres handle dates differently. 
             # For robustness, we might do some python processing or use specific dialects.
             # Keeping it simple: returning raw list for processing or simple fetch
             
             # Fetch all progress for patient
             # Solo pronunciación: las partidas de juegos no son intentos de habla
             all_p = session.query(Progress).filter(Progress.patient_id == patient_id, _not_game()).all()
             
             # Process in python to be DB agnostic (easier than writing conditional SQL for date functions)
             daily_map = {}
             word_counts = {}
             word_scores = {}
             
             for p in all_p:
                 date_str = p.created_at.strftime("%Y-%m-%d")
                 if date_str not in daily_map:
                     daily_map[date_str] = {"attempts": 0, "total_score": 0, "correct": 0}
                 
                 score = p.score or 0
                 d = daily_map[date_str]
                 d["attempts"] += 1
                 d["total_score"] += score
                 if is_attempt_correct(p.score, p.auto_correct, p.therapist_correct):
                     d["correct"] += 1
                     
                 # Per word stats
                 if p.word_id not in word_counts:
                     word_counts[p.word_id] = 0
                     word_scores[p.word_id] = 0
                 word_counts[p.word_id] += 1
                 word_scores[p.word_id] += score

             # Format daily
             daily_progress = []
             for date, data in sorted(daily_map.items()):
                 daily_progress.append({
                     "date": date,
                     "attempts": data["attempts"],
                     "avg_score": data["total_score"] / data["attempts"],
                     "correct": data["correct"]
                 })
                 
             # Top words
             top_words_list = []
             for wid, count in word_counts.items():
                 w = session.get(Word, wid)
                 if w:
                     top_words_list.append({
                         "word": w.word,
                         "attempts": count,
                         "avg_score": word_scores[wid] / count
                     })
             top_words_list.sort(key=lambda x: x["attempts"], reverse=True)
             
             daily = daily_progress[-30:]  # Last 30 entries
             top = top_words_list[:10]
        finally:
            session.close()
        # Palabras que más le cuestan (media baja con al menos 2 intentos y por debajo de 70)
        difficult = [
            {"word": w["word"], "attempts": w["difficulty_stats"]["attempts"],
             "avg_score": w["difficulty_stats"]["avg_score"]}
            for w in self.get_difficult_words(patient_id, limit=10)
            if w["difficulty_stats"]["avg_score"] < 70
        ]
        return {"daily_progress": daily, "top_words": top, "difficult_words": difficult}

    def set_therapist_label(self, patient_id: str, progress_id: str, correct: Optional[bool]) -> bool:
        """Valoración del terapeuta de un intento (None la quita). False si no es de ese paciente."""
        session = self.SessionLocal()
        try:
            p = session.get(Progress, progress_id)
            if not p or p.patient_id != patient_id or p.word_id.startswith(GAME_PREFIX):
                return False
            p.therapist_correct = correct
            session.commit()
            return True
        finally:
            session.close()

    # ==================== PATIENT & POINTS ====================

    def register_patient(self, data: Dict) -> str:
        session = self.SessionLocal()
        try:
            new_patient = Patient(
                name=data.get("name"),
                age=data.get("age"),
                diagnosis=data.get("diagnosis"),
                therapist=data.get("therapist"),
                notes=data.get("notes")
            )
            session.add(new_patient)
            session.commit()
            return new_patient.id
        finally:
            session.close()

    def get_patient(self, patient_id: str) -> Optional[Dict]:
        session = self.SessionLocal()
        try:
            p = session.get(Patient, patient_id)
            return self._to_dict(p) if p else None
        finally:
            session.close()

    def get_cloud_speech_consent(self, patient_id: str) -> Optional[datetime]:
        session = self.SessionLocal()
        try:
            p = session.get(Patient, patient_id)
            return p.cloud_speech_consent_at if p else None
        finally:
            session.close()

    def get_speech_profile(self, patient_id: str) -> Dict:
        session = self.SessionLocal()
        try:
            p = session.get(Patient, patient_id)
            stored = {}
            if p and p.speech_profile:
                try:
                    stored = json.loads(p.speech_profile)
                except ValueError:
                    stored = {}
            return {k: stored.get(k, v) for k, v in SPEECH_PROFILE_DEFAULTS.items()}
        finally:
            session.close()

    def set_speech_profile(self, patient_id: str, updates: Dict) -> Optional[Dict]:
        """Guarda los ajustes indicados (los demás se conservan). None si no existe el paciente."""
        session = self.SessionLocal()
        try:
            p = session.get(Patient, patient_id)
            if not p:
                return None
            current = {}
            if p.speech_profile:
                try:
                    current = json.loads(p.speech_profile)
                except ValueError:
                    current = {}
            current.update({k: v for k, v in updates.items() if k in SPEECH_PROFILE_DEFAULTS})
            p.speech_profile = json.dumps(current)
            session.commit()
        finally:
            session.close()
        return self.get_speech_profile(patient_id)

    def set_cloud_speech_consent(self, patient_id: str, consent: bool) -> Optional[datetime]:
        """Registra (con la fecha) o retira el consentimiento para el reconocimiento en la nube."""
        session = self.SessionLocal()
        try:
            p = session.get(Patient, patient_id)
            if not p:
                return None
            p.cloud_speech_consent_at = _utcnow() if consent else None
            session.commit()
            return p.cloud_speech_consent_at
        finally:
            session.close()

    def list_patients(self) -> List[Dict]:
        """Pacientes de la clínica (todos los terapeutas comparten la lista), con su actividad."""
        session = self.SessionLocal()
        try:
            rows = session.query(
                Patient,
                func.count(Progress.id),
                func.max(Progress.created_at),
            ).outerjoin(Progress, Progress.patient_id == Patient.id).group_by(Patient.id).order_by(Patient.name).all()
            out = []
            for patient, attempts, last in rows:
                d = self._to_dict(patient)
                d["attempts"] = attempts or 0
                d["last_practiced"] = last.isoformat() if last else None
                out.append(d)
            return out
        finally:
            session.close()

    # ==================== THERAPISTS & SESSIONS ====================

    def count_therapists(self) -> int:
        session = self.SessionLocal()
        try:
            return session.query(func.count(Therapist.id)).scalar() or 0
        finally:
            session.close()

    def create_therapist(self, username: str, name: str, password_hash: str) -> str:
        session = self.SessionLocal()
        try:
            therapist = Therapist(username=username.strip().lower(), name=name.strip(), password_hash=password_hash)
            session.add(therapist)
            session.commit()
            return therapist.id
        finally:
            session.close()

    def get_therapist_by_username(self, username: str) -> Optional[Dict]:
        session = self.SessionLocal()
        try:
            t = session.query(Therapist).filter(Therapist.username == username.strip().lower()).first()
            return self._to_dict(t) if t else None
        finally:
            session.close()

    def set_therapist_password(self, username: str, password_hash: str) -> bool:
        session = self.SessionLocal()
        try:
            t = session.query(Therapist).filter(Therapist.username == username.strip().lower()).first()
            if not t:
                return False
            t.password_hash = password_hash
            # Cambiar la contraseña cierra todas las sesiones abiertas de ese terapeuta
            session.query(AuthSession).filter(AuthSession.therapist_id == t.id).delete()
            session.commit()
            return True
        finally:
            session.close()

    def create_session(self, token_hash: str, therapist_id: str, expires_at: datetime) -> None:
        session = self.SessionLocal()
        try:
            session.add(AuthSession(token_hash=token_hash, therapist_id=therapist_id, expires_at=expires_at))
            session.commit()
        finally:
            session.close()

    def get_session(self, token_hash: str, now: datetime, extend_to: Optional[datetime] = None) -> Optional[Dict]:
        """Sesión válida con su terapeuta y paciente activo; renueva la caducidad si se indica."""
        session = self.SessionLocal()
        try:
            s = session.get(AuthSession, token_hash)
            if s is None:
                return None
            if s.expires_at <= now:
                session.delete(s)
                session.commit()
                return None
            therapist = session.get(Therapist, s.therapist_id)
            if therapist is None:
                return None
            patient = session.get(Patient, s.patient_id) if s.patient_id else None
            # Renovar solo si se gana más de 5 min (evita una escritura en cada petición)
            if extend_to is not None and (extend_to - s.expires_at).total_seconds() > 300:
                s.expires_at = extend_to
                session.commit()
            return {
                "therapist_id": therapist.id,
                "therapist_name": therapist.name,
                "username": therapist.username,
                "patient_id": patient.id if patient else None,
                "patient_name": patient.name if patient else None,
            }
        finally:
            session.close()

    def set_session_patient(self, token_hash: str, patient_id: str) -> bool:
        session = self.SessionLocal()
        try:
            s = session.get(AuthSession, token_hash)
            if s is None or session.get(Patient, patient_id) is None:
                return False
            s.patient_id = patient_id
            session.commit()
            return True
        finally:
            session.close()

    def delete_session(self, token_hash: str) -> None:
        session = self.SessionLocal()
        try:
            session.query(AuthSession).filter(AuthSession.token_hash == token_hash).delete()
            session.commit()
        finally:
            session.close()

    def add_points(self, patient_id: str, points: int, reason: str) -> int:
        session = self.SessionLocal()
        try:
            p = Points(patient_id=patient_id, points=points, reason=reason)
            session.add(p)
            session.commit()
            return self.get_total_points(patient_id)
        finally:
            session.close()

    def get_total_points(self, patient_id: str) -> int:
        session = self.SessionLocal()
        try:
            total = session.query(func.sum(Points.points)).filter(Points.patient_id == patient_id).scalar()
            return int(total) if total else 0
        finally:
            session.close()
            
    # ==================== ACHIEVEMENT METHODS ====================

    def unlock_achievement(self, patient_id: str, achievement_type: str, data: Optional[Dict] = None):
        session = self.SessionLocal()
        try:
            exists = session.query(Achievement).filter(
                Achievement.patient_id == patient_id,
                Achievement.achievement_type == achievement_type
            ).first()
            
            if exists:
                return False
                
            new_ach = Achievement(
                patient_id=patient_id,
                achievement_type=achievement_type,
                achievement_data=json.dumps(data or {})
            )
            session.add(new_ach)
            session.commit()
            return True
        finally:
            session.close()

    def get_achievements(self, patient_id: str) -> List[Dict]:
        session = self.SessionLocal()
        try:
            achs = session.query(Achievement).filter(Achievement.patient_id == patient_id).all()
            return [self._to_dict(a) for a in achs]
        finally:
            session.close()

    def _to_dict(self, obj):
        """Helper to convert ORM object to dict"""
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

    # ==================== SPACED REPETITION SYSTEM ====================
    
    def get_words_for_practice(self, patient_id: str, category_id: str, level: Optional[int] = None, count: int = 10) -> List[Dict]:
        """
        Selecciona palabras priorizando las que necesitan más práctica.
        Usa repetición espaciada (Leitner system simplificado).
        
        Args:
            patient_id: ID del paciente
            category_id: ID de la categoría
            level: Nivel de dificultad (opcional)
            count: Número de palabras a retornar
        
        Returns:
            Lista de palabras ordenadas por prioridad de práctica
        """
        session = self.SessionLocal()
        try:
            # Obtener todas las palabras de la categoría/nivel
            query = session.query(Word).filter(Word.category_id == category_id)
            if level:
                query = query.filter(Word.level == level)
            
            all_words = query.all()
            
            if not all_words:
                return []
            
            # Obtener estadísticas de todas las palabras en una sola consulta
            rows = session.query(
                Progress.word_id,
                func.count(Progress.id),
                func.avg(Progress.score),
                func.max(Progress.created_at)
            ).filter(
                Progress.patient_id == patient_id,
                Progress.word_id.in_([w.id for w in all_words])
            ).group_by(Progress.word_id).all()
            stats_by_word = {
                word_id: (attempts, avg_score, last_practiced)
                for word_id, attempts, avg_score, last_practiced in rows
            }

            word_stats = {}
            for word in all_words:
                attempts, avg_score, last_practiced = stats_by_word.get(word.id, (0, None, None))
                word_stats[word.id] = {
                    'word': self._to_dict(word),
                    'attempts': attempts or 0,
                    'avg_score': float(avg_score or 0),
                    'last_practiced': last_practiced
                }
            
            # Calcular prioridad de cada palabra
            def calculate_priority(word_id):
                stats = word_stats[word_id]
                
                # Nunca practicada = prioridad máxima
                if stats['attempts'] == 0:
                    return 100
                
                # Score bajo = prioridad alta
                score_factor = 100 - stats['avg_score']
                
                # Tiempo desde última práctica
                if stats['last_practiced']:
                    days_since = (_utcnow() - stats['last_practiced']).days
                    time_factor = min(days_since * 5, 50)  # Máx 50 puntos por tiempo
                else:
                    time_factor = 50
                
                # Pocas repeticiones = necesita más práctica
                repetition_factor = max(0, 30 - stats['attempts'] * 3)
                
                return score_factor * 0.5 + time_factor * 0.3 + repetition_factor * 0.2
            
            # Ordenar por prioridad (mayor primero)
            sorted_words = sorted(
                word_stats.items(),
                key=lambda x: calculate_priority(x[0]),
                reverse=True
            )
            
            # Retornar top N palabras con sus estadísticas
            result = []
            for word_id, ws in sorted_words[:count]:
                word_data = ws['word']
                word_data['practice_stats'] = {
                    'attempts': ws['attempts'],
                    'avg_score': round(ws['avg_score'], 1),
                    'priority': round(calculate_priority(word_id), 1)
                }
                result.append(word_data)
            
            return result
            
        finally:
            session.close()
    
    def get_difficult_words(self, patient_id: str, limit: int = 10) -> List[Dict]:
        """
        Obtiene las palabras más difíciles para el paciente.
        (Score promedio más bajo con al menos 2 intentos)
        """
        session = self.SessionLocal()
        try:
            results = session.query(
                Word,
                func.avg(Progress.score).label('avg_score'),
                func.count(Progress.id).label('attempts')
            ).join(
                Progress, Progress.word_id == Word.id
            ).filter(
                Progress.patient_id == patient_id, _not_game()
            ).group_by(
                Word.id
            ).having(
                func.count(Progress.id) >= 2  # Al menos 2 intentos
            ).order_by(
                func.avg(Progress.score).asc()  # Menor score primero
            ).limit(limit).all()
            
            difficult_words = []
            for word, avg_score, attempts in results:
                word_dict = self._to_dict(word)
                word_dict['difficulty_stats'] = {
                    'avg_score': round(float(avg_score), 1),
                    'attempts': attempts
                }
                difficult_words.append(word_dict)
            
            return difficult_words
            
        finally:
            session.close()

    def get_aac_config(self) -> Dict:
        """Get full AAC configuration (categories + pictograms)"""
        session = self.SessionLocal()
        try:
            categories = session.query(AACCategory).order_by(AACCategory.order_num).all()
            pictograms = session.query(AACPictogram).all()
            
            return {
                "categories": [self._to_dict(c) for c in categories],
                "items": [self._to_dict(p) for p in pictograms]
            }
        finally:
            session.close()
