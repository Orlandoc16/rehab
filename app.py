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
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, UploadFile, File, HTTPException, Form, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import uuid
from pathlib import Path
import tempfile
from typing import Optional

# Importaciones para procesamiento de audio y voz
from voice_processor import VoiceProcessor
from database import Database
from game_engine import GameEngine

# Configuración de la app
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicialización al arrancar y limpieza al cerrar"""
    print("🎤 Rehab Voice 2025 iniciando...")
    db.initialize()
    print("✅ Base de datos inicializada")
    print("✅ Sistema listo!")
    yield
    print("👋 Cerrando Rehab Voice 2025...")

app = FastAPI(
    lifespan=lifespan,
    title="Rehab Voice 2025",
    description="Aplicación de Rehabilitación Vocal con IA",
    version="2.0.0"
)

# CORS para desarrollo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas estáticas y templates
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Inicializar componentes
db = Database()
voice_processor = VoiceProcessor()
game_engine = GameEngine()

# ==================== RUTAS PRINCIPALES ====================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Página principal"""
    return templates.TemplateResponse(request, "index.html", {"title": "Rehab Voice 2025"})

@app.get("/practice", response_class=HTMLResponse)
async def practice(request: Request):
    """Página de práctica de palabras"""
    return templates.TemplateResponse(request, "practice.html", {"title": "Práctica - Rehab Voice"})

@app.get("/games", response_class=HTMLResponse)
async def games(request: Request):
    """Página de juegos"""
    return templates.TemplateResponse(request, "games.html", {"title": "Juegos - Rehab Voice"})

@app.get("/progress", response_class=HTMLResponse)
async def progress(request: Request):
    """Página de progreso del paciente"""
    return templates.TemplateResponse(request, "progress.html", {"title": "Mi Progreso - Rehab Voice"})

# ==================== API DE VOZ ====================

@app.post("/api/analyze-voice")
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
    try:
        # Validar nivel
        level = max(1, min(5, level))
        
        # Guardar archivo temporal (compatible con Windows y Linux)
        temp_path = os.path.join(tempfile.gettempdir(), f"audio_{uuid.uuid4().hex}.webm")
        with open(temp_path, "wb") as f:
            content = await audio_file.read()
            f.write(content)
        
        # Procesar audio con nivel de tolerancia
        result = voice_processor.analyze(temp_path, target_word, level=level)
        
        # Limpiar archivo temporal
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        return JSONResponse(result)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transcribe")
async def transcribe_audio(
    audio_file: UploadFile = File(...),
    initial_prompt: str = Form(None)
):
    """Solo transcribe el audio sin comparación, con soporte para prompt"""
    try:
        temp_path = f"/tmp/audio_{uuid.uuid4().hex}.webm"
        with open(temp_path, "wb") as f:
            content = await audio_file.read()
            f.write(content)
        
        transcription = voice_processor.transcribe(temp_path, initial_prompt=initial_prompt)
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        return {"transcription": transcription, "success": True}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/speak/{text}")
async def speak_text(text: str, voice: str = "es-ES-ElviraNeural", speed: str = "normal"):
    """Genera audio TTS para la palabra/frase objetivo"""
    try:
        audio_path = await voice_processor.text_to_speech(text, voice, speed)
        return FileResponse(audio_path, media_type="audio/mp3")
    except Exception as e:
        print(f"❌ Error en TTS: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==================== API DE PALABRAS/FRASES ====================

@app.get("/api/words/{category}")
async def get_words(category: str, level: int = 1):
    """Obtiene palabras por categoría y nivel"""
    words = db.get_words(category, level)
    return {"words": words, "category": category, "level": level}

@app.get("/api/categories")
async def get_categories():
    """Lista todas las categorías disponibles"""
    categories = db.get_categories()
    return {"categories": categories}

@app.post("/api/words")
async def add_custom_word(word_data: dict):
    """Agrega una palabra personalizada"""
    db.add_word(word_data)
    return {"success": True, "message": "Palabra agregada"}



async def generate_tts_cache(words: list):
    """Tarea en segundo plano para generar caché de audio"""
    print(f"🔄 Pre-generando TTS para {len(words)} palabras...")
    for word_item in words:
        try:
            # Solo generar si no existe (la función text_to_speech ya debería manejar caché si se implementara allí, 
            # pero aquí forzamos la llamada para que el archivo físico se cree/verifique)
            await voice_processor.text_to_speech(word_item["word"])
        except Exception as e:
            print(f"⚠️ Error generando TTS background para {word_item['word']}: {e}")

@app.get("/api/words/practice/{category}")
async def get_practice_words(
    category: str, 
    background_tasks: BackgroundTasks,
    level: Optional[int] = None, 
    patient_id: str = "default", 
    count: int = 10
):
    """
    Obtiene palabras priorizadas para práctica usando repetición espaciada.
    Las palabras más difíciles y menos practicadas aparecen primero.
    """
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

@app.get("/api/words/difficult/{patient_id}")
async def get_difficult_words(patient_id: str, limit: int = 10):
    """
    Obtiene las palabras más difíciles para el paciente.
    Útil para práctica enfocada en áreas de mejora.
    """
    words = db.get_difficult_words(patient_id, limit)
    return {
        "words": words,
        "patient_id": patient_id,
        "count": len(words)
    }

# ==================== API DE PROGRESO ====================

@app.get("/api/progress/{patient_id}")
async def get_progress(patient_id: str):
    """Obtiene el progreso de un paciente"""
    progress = db.get_progress(patient_id)
    return progress

@app.post("/api/progress")
async def save_progress(progress_data: dict):
    """Guarda el progreso de una sesión"""
    db.save_progress(progress_data)
    
    # Calcular puntos del juego
    points = game_engine.calculate_points(progress_data)
    
    return {
        "success": True,
        "points_earned": points,
        "total_points": db.get_total_points(progress_data.get("patient_id", "default"))
    }

@app.get("/api/stats/{patient_id}")
async def get_stats(patient_id: str):
    """Obtiene estadísticas detalladas"""
    return db.get_detailed_stats(patient_id)

# ==================== API DE JUEGOS ====================

@app.get("/api/games/daily-challenge")
async def get_daily_challenge():
    """Obtiene el desafío diario"""
    return game_engine.get_daily_challenge()

@app.get("/api/games/achievements/{patient_id}")
async def get_achievements(patient_id: str):
    """Lista los logros del paciente"""
    return game_engine.get_achievements(patient_id)

@app.post("/api/games/complete-challenge")
async def complete_challenge(data: dict):
    """Marca un desafío como completado"""
    patient_id = data.get("patient_id")
    challenge_id = data.get("challenge_id")
    if not patient_id or not challenge_id:
        raise HTTPException(status_code=400, detail="patient_id y challenge_id son obligatorios")
    result = game_engine.complete_challenge(
        str(patient_id),
        str(challenge_id),
        int(data.get("score") or 0)
    )
    return result

# ==================== API DE CONFIGURACIÓN ====================

@app.get("/api/config")
async def get_config():
    """Obtiene la configuración actual"""
    return {
        "voices_available": voice_processor.get_available_voices(),
        "languages": ["es-ES", "es-MX", "en-US"],
        "difficulty_levels": [1, 2, 3, 4, 5],
        "categories": db.get_categories()
    }

@app.post("/api/patient/register")
async def register_patient(data: dict):
    """Registra un nuevo paciente"""
    patient_id = db.register_patient(data)
    return {"patient_id": patient_id, "success": True}

# ==================== MODULO AAC (Tablero de Comunicación) ====================

@app.get("/communicator", response_class=HTMLResponse)
async def communicator(request: Request):
    """Página del tablero de comunicación"""
    return templates.TemplateResponse(request, "communicator.html", {"title": "Comunicador - Rehab Voice"})

@app.get("/api/aac/config")
async def get_aac_config():
    """Obtiene configuración completa del tablero AAC"""
    return db.get_aac_config()

# ==================== MAIN ====================

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
