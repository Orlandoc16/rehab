"""Instancias compartidas de la lógica de dominio (una por proceso)."""
from database import Database
from game_engine import GameEngine
from voice_processor import VoiceProcessor

from . import settings

db = Database()
voice_processor = VoiceProcessor(engine=settings.STT_ENGINE)
game_engine = GameEngine()
