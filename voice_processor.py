"""
🎙️ Voice Processor Module
Procesamiento de voz con múltiples motores STT y comparación fonética

Características:
- Whisper (OpenAI) - Alta precisión
- Vosk - Offline/tiempo real
- Comparación fonética múltiple
- Text-to-Speech con Edge TTS
"""

import os
import asyncio
import tempfile
import hashlib
import importlib.util
from pathlib import Path
from typing import Optional, Dict, Any, List
import json
import wave
from datetime import datetime

# Caché persistente de audios TTS de los motores de respaldo (Edge/gTTS)
TTS_CACHE_DIR = Path(__file__).resolve().parent / "cache" / "tts"
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Procesamiento de audio
# openai-whisper arrastra PyTorch (~15 s de arranque y cientos de MB de memoria).
# Solo se importa si se elige ese motor; faster-whisper (el motor por defecto) no lo necesita.
WHISPER_AVAILABLE = importlib.util.find_spec("whisper") is not None
if not WHISPER_AVAILABLE:
    print("⚠️ Whisper no disponible. Instalar con: pip install openai-whisper")

try:
    from faster_whisper import WhisperModel

    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    print("ℹ️ Faster Whisper no disponible. Instalar con: pip install faster-whisper")

try:
    from vosk import Model, KaldiRecognizer  # pyright: ignore[reportMissingImports]
    VOSK_AVAILABLE = False  # Deshabilitado por defecto, requiere modelo descargado
except ImportError:
    VOSK_AVAILABLE = False

# Comparación fonética
try:
    from pyphonetics import Soundex, Metaphone, RefinedSoundex
    PHONETICS_AVAILABLE = True
except ImportError:
    PHONETICS_AVAILABLE = False

# Métricas de comparación
try:
    from jiwer import wer
    JIWER_AVAILABLE = True
except ImportError:
    JIWER_AVAILABLE = False

# Text to Speech
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

# Voces EN LÍNEA (Edge TTS de Microsoft, gTTS de Google) como respaldo de Piper. Desactivadas por
# defecto: enviarían a servicios externos las frases del paciente («Tengo dolor de pecho»).
# Actívalas con TTS_ONLINE=1 solo si el centro lo acepta.
TTS_ONLINE = os.getenv("TTS_ONLINE", "0") == "1"


class NoVoiceAvailableError(RuntimeError):
    """Ningún motor de voz pudo generar el audio."""

# Conversión de audio
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

# ============================================
# Piper TTS Integration (Offline, Rápido)
# ============================================
PIPER_INTEGRATION = False
PIPER_TTS = None

try:
    from piper_tts import PiperTTS
    _piper_test = PiperTTS()
    if _piper_test.is_installed():
        PIPER_TTS = _piper_test
        PIPER_INTEGRATION = True
        print("✅ Piper TTS integrado (offline, ~50ms)")
    else:
        print("⚠️ Piper no instalado, usando fallbacks")
except ImportError as e:
    print(f"ℹ️ Piper TTS no disponible: {e}")
except Exception as e:
    print(f"⚠️ Error Piper: {e}")


# --- Compatibilidad faster-whisper <-> PyAV antiguo ---
# faster-whisper pasa metadata_errors="ignore" a av.open(); PyAV antiguo no lo acepta.
import av as _av_module
_av_open_original = _av_module.open
def _av_open_compat(*args, **kwargs):
    kwargs.pop("metadata_errors", None)
    return _av_open_original(*args, **kwargs)
_av_module.open = _av_open_compat
# --- fin compatibilidad ---

class VoiceProcessor:
    """Procesador principal de voz"""
    
    def __init__(self, engine: str = "faster_whisper"):
        """
        Args:
            engine: Motor de STT ("faster_whisper", "whisper", "vosk")
        """
        self.engine = engine
        self.model: Any = None
        self.temp_dir = tempfile.gettempdir()
        
        # Inicializar motor seleccionado
        self._initialize_engine()
        
        # Inicializar comparadores fonéticos
        if PHONETICS_AVAILABLE:
            self.soundex = Soundex()  # pyright: ignore[reportPossiblyUnboundVariable]
            self.metaphone = Metaphone()  # pyright: ignore[reportPossiblyUnboundVariable]
            self.refined_soundex = RefinedSoundex()  # pyright: ignore[reportPossiblyUnboundVariable]
            
        # Cache de fonética para palabras objetivo (target_word)
        # Structure: { "word": { "clean": "...", "metaphone": "..." } }
        self.phonetic_cache = {}
    
    def _initialize_engine(self):
        """Inicializa el motor de reconocimiento de voz"""
        if self.engine == "faster_whisper" and FASTER_WHISPER_AVAILABLE:
            # WHISPER_MODEL: "base" (por defecto, ~2-3 s por intento en un portátil) o "small"
            # (menos falsos aprobados, ~3 veces más lento: recomendable con CPU de escritorio o GPU).
            # Comparativa: python tools/eval_speech.py eval_audio/sintetico --model small
            model_size = os.getenv("WHISPER_MODEL", "base")
            print(f"⚡ Cargando Faster Whisper ({model_size})...")
            # Run on CPU with INT8 by default to be safe on all machines
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")  # pyright: ignore[reportPossiblyUnboundVariable]
            print("✅ Faster Whisper cargado")
            
        elif self.engine == "whisper" and WHISPER_AVAILABLE:
            print("🔄 Cargando modelo Whisper (small)...")
            import whisper
            self.model = whisper.load_model("base")
            print("✅ Whisper cargado")
            
        elif self.engine == "vosk" and VOSK_AVAILABLE:
            model_path = Path(__file__).parent / "models" / "vosk-model-es"
            if model_path.exists():
                self.model = Model(str(model_path))  # pyright: ignore[reportPossiblyUnboundVariable]
                print("✅ Vosk cargado")
            else:
                print(f"⚠️ Modelo Vosk no encontrado en {model_path}")
        else:
             print(f"⚠️ Motor {self.engine} no disponible o falló carga. Usando fallback.")
    
    def transcribe(self, audio_path: str, language: str = "es", initial_prompt: Optional[str] = None) -> str:
        """
        Transcribe audio a texto
        
        Args:
            audio_path: Ruta al archivo de audio
            language: Código de idioma (es, en, etc.)
            initial_prompt: Texto de contexto para guiar al modelo
        
        Returns:
            Texto transcrito
        """
        # Convertir audio si es necesario
        wav_path = self._convert_to_wav(audio_path)
        try:
        
            print(f"🎤 Transcribiendo: {wav_path} (engine={self.engine}, prompt='{initial_prompt}')")
        
            if self.engine == "faster_whisper" and self.model:
                # Faster Whisper uses 'initial_prompt'
                segments, _ = self.model.transcribe(
                    wav_path,
                    language=language,
                    initial_prompt=initial_prompt,
                    vad_filter=True,
                    condition_on_previous_text=False,
                    beam_size=5,
                    best_of=5,
                    word_timestamps=False,
                    patience=1.0
                )
                # Combine segments
                transcription = " ".join([segment.text for segment in segments]).strip()
                print(f"✅ Faster Whisper result: '{transcription}'")
            
            elif self.engine == "whisper" and self.model:
                # OpenAI Whisper uses 'initial_prompt'
                result = self.model.transcribe(
                    wav_path,
                    language=language,
                    fp16=False,  # Usar fp32 para compatibilidad
                    initial_prompt=initial_prompt
                )
                transcription = result["text"].strip()
                print(f"✅ Whisper result: '{transcription}'")
            
            elif self.engine == "vosk" and self.model:
                transcription = self._transcribe_vosk(wav_path)
                print(f"✅ Vosk result: '{transcription}'")
            
            else:
                # Fallback
                print("⚠️ No hay motor de transcripción disponible")
                transcription = self._mock_transcription(audio_path)
        
        finally:
            # Limpiar archivo temporal (también si la transcripción falla)
            if wav_path != audio_path and os.path.exists(wav_path):
                os.remove(wav_path)
        
        return transcription
    
    def _convert_to_wav(self, audio_path: str) -> str:
        """
        Intenta convertir a WAV 16kHz mono.
        Si falla (por falta de ffmpeg), devuelve el path original.
        Faster-Whisper suele manejar WebM/MP3 nativamente.
        """
        if not PYDUB_AVAILABLE:
            return audio_path
        
        try:
            # Detectar formato
            ext = Path(audio_path).suffix.lower()
            if ext == ".wav":
                return audio_path
            
            # Intentar conversion
            # Nota: Esto fallará si no está instalado ffmpeg en el sistema
            audio = AudioSegment.from_file(audio_path)  # pyright: ignore[reportPossiblyUnboundVariable]
            audio = audio.set_frame_rate(16000).set_channels(1)
            
            wav_path = os.path.join(self.temp_dir, f"converted_{datetime.now().timestamp()}.wav")
            audio.export(wav_path, format="wav")
            
            return wav_path
        except Exception as e:
            # Si falla (ej: falta ffmpeg), retornamos el original y esperamos que Whisper lo entienda
            print(f"⚠️ No se pudo convertir audio (posible falta de FFmpeg): {e}")
            print(f"ℹ️ Intentando procesar archivo original: {audio_path}")
            return audio_path
    
    def _transcribe_vosk(self, wav_path: str) -> str:
        """Transcripción con Vosk"""
        wf = wave.open(wav_path, "rb")
        rec = KaldiRecognizer(self.model, wf.getframerate())  # pyright: ignore[reportPossiblyUnboundVariable]
        rec.SetWords(True)
        
        results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                part_result = json.loads(rec.Result())
                results.append(part_result.get("text", ""))
        
        final_result = json.loads(rec.FinalResult())
        results.append(final_result.get("text", ""))
        
        return " ".join(results).strip()
    
    def _mock_transcription(self, audio_path: str) -> str:
        """Transcripción simulada para desarrollo sin Whisper"""
        print("⚠️ Usando transcripción simulada (instalar whisper para producción)")
        return "[transcripción simulada - instalar whisper]"
    
    def transcribe_with_retry(self, audio_path: str, language: str = "es", initial_prompt: Optional[str] = None) -> str:
        """
        Intenta transcribir con múltiples configuraciones para mayor robustez.
        Útil para palabras cortas o audio de baja calidad.
        
        Args:
            audio_path: Ruta al archivo de audio
            language: Código de idioma
            initial_prompt: Contexto para el modelo
        
        Returns:
            Mejor transcripción obtenida
        """
        attempts = []
        wav_path = self._convert_to_wav(audio_path)
        
        # Intento 1: Configuración estándar
        try:
            if self.engine == "faster_whisper" and self.model:
                segments, _ = self.model.transcribe(
                    wav_path, 
                    language=language,
                    beam_size=5,
                    best_of=5,
                    initial_prompt=initial_prompt
                )
                result = " ".join([s.text for s in segments]).strip()
                if result and result not in ['', '[BLANK_AUDIO]', '...']:
                    attempts.append(result)
                    print(f"✅ Intento 1 (estándar): '{result}'")
        except Exception as e:
            print(f"⚠️ Intento 1 falló: {e}")
        
        # Intento 2: Con temperature más alta (más creativo)
        try:
            if self.engine == "faster_whisper" and self.model and len(attempts) == 0:
                segments, _ = self.model.transcribe(
                    wav_path,
                    language=language,
                    temperature=0.2,
                    beam_size=3,
                    patience=1.5,
                    initial_prompt=initial_prompt
                )
                result = " ".join([s.text for s in segments]).strip()
                if result and result not in attempts and result not in ['', '[BLANK_AUDIO]', '...']:
                    attempts.append(result)
                    print(f"✅ Intento 2 (temperature): '{result}'")
        except Exception as e:
            print(f"⚠️ Intento 2 falló: {e}")
        
        # Intento 3: Sin supresión de timestamps (puede ayudar con audio corto)
        try:
            if self.engine == "faster_whisper" and self.model and len(attempts) == 0:
                segments, _ = self.model.transcribe(
                    wav_path,
                    language=language,
                    word_timestamps=True,
                    vad_filter=False,  # Desactivar filtro de VAD para audio corto
                    initial_prompt=initial_prompt
                )
                result = " ".join([s.text for s in segments]).strip()
                if result and result not in attempts and result not in ['', '[BLANK_AUDIO]', '...']:
                    attempts.append(result)
                    print(f"✅ Intento 3 (sin VAD): '{result}'")
        except Exception as e:
            print(f"⚠️ Intento 3 falló: {e}")
        
        # Limpiar archivo temporal
        if wav_path != audio_path and os.path.exists(wav_path):
            os.remove(wav_path)
        
        # Seleccionar mejor resultado
        if attempts:
            # Preferir el resultado más largo (usualmente tiene más información)
            # pero filtrar resultados muy largos (posible ruido)
            valid_attempts = [a for a in attempts if len(a) < 200]
            if valid_attempts:
                return max(valid_attempts, key=len)
            return attempts[0]
        
        # Fallback a transcripción normal
        return self.transcribe(audio_path, language, initial_prompt=initial_prompt)
    
    def analyze(self, audio_path: str, target_word: str, level: int = 1,
                alternatives: Optional[List[str]] = None, tolerance_offset: float = 0) -> Dict[str, Any]:
        """
        Análisis completo: transcripción + comparación

        Args:
            audio_path: Ruta al audio
            target_word: Palabra/frase objetivo
            level: Nivel de dificultad (1-5) para ajustar tolerancia
            alternatives: lo que oyó el reconocimiento del navegador (solo pacientes que lo
                consintieron). Se puntúa igual que la transcripción local y gana la mejor.

        Returns:
            Dict con análisis completo; "engine" dice qué reconocimiento dio el resultado
        """
        best: Optional[Dict[str, Any]] = None
        for alt in alternatives or []:
            r = self._score_transcription(alt, target_word, level, tolerance_offset)
            if best is None or r["scores"]["final"] > best["scores"]["final"]:
                best = {**r, "engine": "browser"}
        # Si el navegador ya oyó la palabra tal cual, la transcripción local no puede mejorarlo:
        # se omite y la respuesta llega varios segundos antes.
        if best and best["scores"]["final"] >= 95:
            return best

        # SIN pista con la palabra objetivo: con ella Whisper «oía» la palabra aunque se dijera
        # mal (35 % de las pronunciaciones incorrectas se daban por buenas en tools/eval_speech.py).
        transcription = self.transcribe_with_retry(audio_path, initial_prompt=None)
        local = {**self._score_transcription(transcription, target_word, level, tolerance_offset), "engine": "local"}
        if best is None or local["scores"]["final"] >= best["scores"]["final"]:
            return local
        return best

    # Palabras de más que se toleran (p. ej. «agua por favor» para «agua») y su penalización
    MAX_EXTRA_WORDS = 3
    EXTRA_WORD_PENALTY = 5

    def _score_transcription(self, transcription: str, target_word: str, level: int = 1,
                             tolerance_offset: float = 0) -> Dict[str, Any]:
        """Puntúa una transcripción frente a la palabra objetivo.

        Decir algo de más no es un error de pronunciación: si la transcripción tiene hasta
        MAX_EXTRA_WORDS palabras más que el objetivo, también se puntúa el tramo que mejor
        coincide («el perro» -> «perro»), con una pequeña penalización por palabra extra, y
        gana el mejor resultado. tolerance_offset sube o baja el umbral (ajuste por paciente).
        """
        base = self._score_core(transcription, target_word, level, tolerance_offset)
        window, extra = self._best_window(self._normalize_text(self._clean_whisper_output(transcription)),
                                          self._normalize_text(target_word))
        if not window or not 1 <= extra <= self.MAX_EXTRA_WORDS:
            return base
        w = self._score_core(window, target_word, level, tolerance_offset)
        adjusted = max(0.0, w["scores"]["final"] - self.EXTRA_WORD_PENALTY * extra)
        if adjusted <= base["scores"]["final"]:
            return base
        threshold = w["scores"]["threshold"]
        is_correct = adjusted >= threshold
        w["transcription"] = base["transcription"]
        w["scores"] = {**w["scores"], "final": adjusted, "extra_words": extra}
        w["is_correct"] = is_correct
        w["feedback"] = self._generate_feedback(adjusted, window, self._normalize_text(target_word),
                                                is_correct=is_correct, threshold=threshold)
        return w

    def _best_window(self, transcription_clean: str, target_clean: str):
        """Tramo de la transcripción (con tantas palabras como el objetivo) que más se parece al
        objetivo por fonética, y cuántas palabras sobran. ("", 0) si no sobra ninguna."""
        words = transcription_clean.split()
        n = len(target_clean.split())
        if not n or len(words) <= n:
            return "", 0
        target_phone = " ".join(self._spanish_metaphone(w) for w in target_clean.split())
        best, best_sim = "", -1.0
        for i in range(len(words) - n + 1):
            candidate = words[i:i + n]
            sim = self._string_similarity(" ".join(self._spanish_metaphone(w) for w in candidate), target_phone)
            if sim > best_sim:
                best, best_sim = " ".join(candidate), sim
        return best, len(words) - n

    def _score_core(self, transcription: str, target_word: str, level: int = 1,
                    tolerance_offset: float = 0) -> Dict[str, Any]:
        """Puntuación de una transcripción completa frente al objetivo."""
        # Limpiar transcripción de caracteres extraños de Whisper
        transcription = self._clean_whisper_output(transcription)
        
        # Normalizar textos
        transcription_clean = self._normalize_text(transcription)
        
        # Optimización: Usar caché para phonetics de target_word
        target_clean = ""
        target_phone = ""
        
        if target_word in self.phonetic_cache:
            cached = self.phonetic_cache[target_word]
            target_clean = cached["clean"]
            target_phone = cached["metaphone"]
        else:
            target_clean = self._normalize_text(target_word)
            target_phone = self._spanish_metaphone(target_clean)
            # Guardar en caché
            self.phonetic_cache[target_word] = {
                "clean": target_clean,
                "metaphone": target_phone
            }
        
        print(f"DEBUG: Trans RAW: '{transcription}'")
        print(f"DEBUG: Trans CLEAN: '{transcription_clean}'")
        print(f"DEBUG: Target RAW: '{target_word}'")
        print(f"DEBUG: Target CLEAN: '{target_clean}'")
        
        # ===========================================
        # VERIFICACIÓN TEMPRANA DE COINCIDENCIA EXACTA
        # ===========================================
        # Si son iguales (o casi), dar 100% inmediatamente
        if transcription_clean and target_clean:
            if transcription_clean == target_clean:
                print("DEBUG: ¡COINCIDENCIA EXACTA DETECTADA!")
                return self._create_perfect_result(transcription, target_word, level, tolerance_offset=tolerance_offset)
            
            # Verificar si son fonéticamente idénticos
            trans_phone = self._spanish_metaphone(transcription_clean)
            # target_phone ya calculado arriba
            
            if trans_phone == target_phone:
                print(f"DEBUG: ¡COINCIDENCIA FONÉTICA EXACTA! '{trans_phone}'")
                return self._create_perfect_result(transcription, target_word, level, score=95,
                                                   tolerance_offset=tolerance_offset)
        
        # Calcular similitudes
        # Pasamos ya los textos limpios, pero _calculate_phonetic_similarity calculará sus fonemas de nuevo
        # Podríamos optimizarlo más pasando ya los fonemas, pero requeriría refactorizar _calculate_phonetic_similarity
        phonetic_scores = self._calculate_phonetic_similarity(transcription_clean, target_clean)
        text_scores = self._calculate_text_similarity(transcription_clean, target_clean)
        
        # Para frases (desde 2 palabras), usar también comparación flexible por palabras clave
        word_count = len(target_clean.split()) if target_clean else 0
        if word_count >= 2:
            phrase_score = self._calculate_phrase_similarity(transcription_clean, target_clean)
            phonetic_scores["phrase_similarity"] = phrase_score
            phonetic_scores["average"] = (phonetic_scores.get("spanish_metaphone", 0) * 0.5 + phrase_score * 0.5)
        
        print(f"DEBUG: Scores: Phonetic={phonetic_scores.get('average')}, Text={text_scores.get('average')}")
        
        # Puntuación final ponderada
        final_score = self._calculate_final_score(phonetic_scores, text_scores, level)
        print(f"DEBUG: Final Score: {final_score}")
        
        # Obtener umbral adaptativo
        tolerance_threshold = self._get_tolerance_threshold(level, len(target_clean) if target_clean else 0,
                                                            tolerance_offset)
        is_correct = final_score >= tolerance_threshold
        
        # Detectar errores específicos (para rehabilitación)
        specific_errors = self._detect_specific_errors(transcription_clean, target_clean)
        
        # Generar feedback enriquecido
        feedback = self._generate_feedback(final_score, transcription_clean, target_clean,
                                           is_correct=is_correct, threshold=tolerance_threshold)
        
        # Agregar errores específicos al feedback
        if specific_errors and not is_correct:
            feedback["specific_errors"] = specific_errors
            if specific_errors:
                feedback["tips"] = [err["tip"] for err in specific_errors]
        
        return {
            "success": True,
            "transcription": transcription,
            "target": target_word,
            "scores": {
                "phonetic": phonetic_scores,
                "text": text_scores,
                "final": final_score,
                "threshold": tolerance_threshold
            },
            "feedback": feedback,
            "is_correct": is_correct,
            "level": level,
            "timestamp": datetime.now().isoformat()
        }
    
    def _clean_whisper_output(self, text: str) -> str:
        """
        Limpia la salida de Whisper de caracteres extraños.
        Whisper a veces agrega puntuación, espacios extra, o texto de relleno.
        """
        if not text:
            return ""
        
        # Eliminar patrones comunes de Whisper
        import re
        
        # Eliminar [BLANK_AUDIO], (Subtítulos...), etc.
        text = re.sub(r'\[.*?\]', '', text)
        text = re.sub(r'\(.*?\)', '', text)
        
        # Eliminar puntuación excesiva
        text = re.sub(r'[\.\,\!\?\;\:\.\.\.]+', '', text)
        
        # Eliminar comillas
        text = text.replace('"', '').replace("'", '').replace('«', '').replace('»', '')
        
        # Eliminar guiones al inicio/final
        text = text.strip('-–— ')
        
        # Reducir espacios múltiples
        text = ' '.join(text.split())
        
        return text.strip()
    
    def _create_perfect_result(self, transcription: str, target: str, level: int, score: float = 100,
                               tolerance_offset: float = 0) -> Dict[str, Any]:
        """
        Crea un resultado perfecto para coincidencias exactas.
        """
        return {
            "success": True,
            "transcription": transcription,
            "target": target,
            "scores": {
                "phonetic": {"spanish_metaphone": score, "average": score},
                "text": {"exact_match": score, "levenshtein": score, "wer": score, "average": score},
                "final": score,
                "threshold": self._get_tolerance_threshold(level, len(target), tolerance_offset)
            },
            "feedback": {
                "level": "excellent",
                "message": "¡Excelente! Lo dijiste muy bien.",
                "encouragement": "Sigue así.",
                "should_repeat": False,
                "differences": [],
                "tips": ["¡Perfecto! Continúa con la siguiente palabra."]
            },
            "is_correct": True,
            "level": level,
            "timestamp": datetime.now().isoformat()
        }
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalización agresiva para comparación de voz.
        Convierte "Adiós." -> "adios"
        Convierte "Pingüino" -> "pinguino"
        """
        if not text:
            return ""
            
        import unicodedata
        
        # 1. Minúsculas y stripping básico
        text = text.lower().strip()
        
        # 2. Descomponer caracteres Unicode (NFD) para separar tildes
        text = unicodedata.normalize('NFD', text)
        
        # 3. Filtrar diacríticos
        cleaned = []
        for c in text:
            if unicodedata.category(c) != 'Mn':
                if c.isalnum() or c.isspace():
                    cleaned.append(c)
        
        text = "".join(cleaned)
        
        # 4. Reducir espacios
        text = " ".join(text.split())
        
        return text

    def _spanish_metaphone(self, word: str) -> str:
        """
        Algoritmo fonético MEJORADO para español.
        Convierte una palabra en su representación fonética "tolerante".
        
        Mejoras:
        - Maneja RR vs R correctamente
        - Maneja X (ks/j según contexto)
        - Maneja Y como consonante/vocal
        - Maneja Ñ como NY
        - Maneja W, K, grupos consonantes
        """
        if not word: 
            return ""
        
        word = word.lower().strip()
        code = ""
        i = 0
        n = len(word)
        
        while i < n:
            c = word[i]
            next_c = word[i+1] if i+1 < n else ""
            prev_c = word[i-1] if i > 0 else ""
            third_c = word[i+2] if i+2 < n else ""
            
            # H muda (excepto en CH)
            if c == 'h' and prev_c != 'c':
                i += 1
                continue
            
            # CH -> X (sonido che)
            if c == 'c' and next_c == 'h':
                code += 'x'
                i += 2
                continue
                
            # LL -> Y
            if c == 'l' and next_c == 'l':
                code += 'y'
                i += 2
                continue
            
            # RR -> R fuerte (mantener distintivo)
            if c == 'r' and next_c == 'r':
                code += 'rr'
                i += 2
                continue
            
            # R al inicio = RR fuerte
            if c == 'r' and i == 0:
                code += 'rr'
                i += 1
                continue
                
            # V -> B (b/v suenan igual en español)
            if c == 'v':
                code += 'b'
                i += 1
                continue
            
            # C, Z, S -> S (seseo latinoamericano)
            if c == 'z' or c == 's':
                code += 's'
                i += 1
                continue
                
            if c == 'c':
                if next_c in ['e', 'i']:
                    code += 's'  # CE, CI -> se, si
                else: 
                    code += 'k'  # CA, CO, CU -> ka, ko, ku
                i += 1
                continue
                
            # QU -> K (queso -> keso)
            if c == 'q':
                code += 'k'
                if next_c == 'u':
                    i += 2  # Saltar la U muda
                else:
                    i += 1
                continue
            
            # K -> K
            if c == 'k':
                code += 'k'
                i += 1
                continue
            
            # X -> puede ser "ks" o "j" según contexto
            if c == 'x':
                # X al inicio o seguida de consonante suena como J (México)
                if i == 0 or next_c not in 'aeiouáéíóú':
                    code += 'j'
                else:
                    code += 'ks'
                i += 1
                continue
            
            # G -> J (gente) o G (gato)
            if c == 'g':
                if next_c in ['e', 'i']:
                    code += 'j'  # GE, GI -> je, ji
                elif next_c == 'u':
                    if third_c in ['e', 'i']:
                        # GUE, GUI -> ge, gi (U muda)
                        code += 'g'
                        i += 2
                        continue
                    else:
                        code += 'g'  # GUA, GUO -> gua, guo
                else:
                    code += 'g'  # GA, GO -> ga, go
                i += 1
                continue
            
            # Y - consonante o vocal según posición
            if c == 'y':
                if next_c in 'aeiouáéíóú' or i == 0:
                    code += 'y'  # YA, YE -> consonante
                else:
                    code += 'i'  # Y final o sola = vocal i
                i += 1
                continue
                
            # Ñ -> NY (aproximación fonética)
            if c == 'ñ':
                code += 'ny'
                i += 1
                continue
            
            # W -> U (o GU según contexto)
            if c == 'w':
                code += 'u'
                i += 1
                continue
            
            # J siempre es J
            if c == 'j':
                code += 'j'
                i += 1
                continue
            
            # Vocales y consonantes normales
            code += c
            i += 1
        
        # Deduplicación de consonantes repetidas (excepto RR que es significativo)
        final_code = []
        if code:
            i = 0
            while i < len(code):
                # Preservar RR como unidad
                if code[i:i+2] == 'rr':
                    final_code.append('rr')
                    i += 2
                # Preservar NY como unidad  
                elif code[i:i+2] == 'ny':
                    final_code.append('ny')
                    i += 2
                # Preservar KS como unidad
                elif code[i:i+2] == 'ks':
                    final_code.append('ks')
                    i += 2
                # Deduplicar consonantes repetidas (pero no vocales)
                elif len(final_code) > 0 and code[i] == final_code[-1] and code[i] not in 'aeiou':
                    i += 1
                else:
                    final_code.append(code[i])
                    i += 1
                    
        return "".join(final_code)
    
    def _calculate_phonetic_similarity(self, text1: str, text2: str) -> Dict[str, float]:
        """Calcula similitud fonética usando nuestro motor experto español"""
        scores = {}
        
        # Caso especial: ambos vacíos
        if not text1 and not text2:
            scores["spanish_metaphone"] = 0
            scores["average"] = 0
            return scores
        
        # Caso especial: uno vacío
        if not text1 or not text2:
            scores["spanish_metaphone"] = 0
            scores["average"] = 0
            return scores
        
        # Caso especial: textos idénticos
        if text1 == text2:
            scores["spanish_metaphone"] = 100
            scores["average"] = 100
            return scores
        
        # Tokenizar palabras
        words1 = text1.split()
        words2 = text2.split()
        
        # Generar códigos fonéticos
        phones1 = [self._spanish_metaphone(w) for w in words1]
        phones2 = [self._spanish_metaphone(w) for w in words2]
        
        # Unir para comparar frase entera
        str_phones1 = " ".join(phones1)
        str_phones2 = " ".join(phones2)
        
        print(f"DEBUG: Fonética: '{text1}' -> '{str_phones1}'")
        print(f"DEBUG: Fonética: '{text2}' -> '{str_phones2}'")
        
        # Si los fonemas son idénticos, 100%
        if str_phones1 == str_phones2:
            scores["spanish_metaphone"] = 100
            scores["average"] = 100
            return scores
        
        # Distancia de Levenshtein sobre los fonemas
        lev_score = self._string_similarity(str_phones1, str_phones2)
        
        scores["spanish_metaphone"] = lev_score
        scores["average"] = lev_score
        
        return scores
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> Dict[str, float]:
        """Calcula similitud de texto"""
        scores = {}
        
        # Caso especial: ambos vacíos
        if not text1 and not text2:
            scores["exact_match"] = 0
            scores["levenshtein"] = 0
            scores["wer"] = 0
            scores["average"] = 0
            return scores
        
        # Caso especial: textos idénticos
        if text1 == text2:
            scores["exact_match"] = 100
            scores["levenshtein"] = 100
            scores["wer"] = 100
            scores["average"] = 100
            return scores
        
        # Coincidencia exacta
        if text1 and text2:
            scores["exact_match"] = 100 if text1 == text2 else 0
        else:
            scores["exact_match"] = 0
        
        # Levenshtein (distancia de edición)
        lev_dist = self._levenshtein_distance(text1, text2)
        max_len = max(len(text1), len(text2), 1)
        scores["levenshtein"] = max(0, (1 - lev_dist / max_len) * 100)
        
        # Word Error Rate (si está disponible)
        if JIWER_AVAILABLE and text1 and text2:
            try:
                wer_score = wer(text2, text1)  # pyright: ignore[reportPossiblyUnboundVariable]
                scores["wer"] = max(0, (1 - wer_score) * 100)
            except Exception:
                scores["wer"] = scores["levenshtein"]
        else:
            scores["wer"] = scores["levenshtein"]
        
        # Promedio ponderado
        scores["average"] = (
            scores["exact_match"] * 0.3 +
            scores["levenshtein"] * 0.35 +
            scores["wer"] * 0.35
        )
        
        return scores
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calcula distancia de Levenshtein"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _string_similarity(self, s1: str, s2: str) -> float:
        """Similitud entre dos strings (0-100)"""
        if not s1 or not s2:
            return 0
        
        dist = self._levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        return max(0, (1 - dist / max_len) * 100)
    
    def _calculate_final_score(self, phonetic_scores: Dict, text_scores: Dict, level: int = 1) -> float:
        """Calcula puntuación combinada con tolerancia adaptativa"""
        # Pesos ajustados según el tipo de contenido
        p_score = phonetic_scores.get("average", 0)
        t_score = text_scores.get("average", 0)
        
        # Si la coincidencia de texto es muy alta (casi perfecta), 
        # confiamos en ella por encima de la fonética
        if t_score > 90 and text_scores.get("levenshtein", 0) > 90:
            return t_score
        
        # Si hay coincidencia fonética pero no textual, dar más peso a fonética
        # Esto ayuda con palabras que suenan igual pero se escriben diferente
        if p_score > 80 and t_score < 60:
            w_phonetic = 0.6
            w_text = 0.4
        else:
            w_phonetic = 0.4
            w_text = 0.6
            
        final = (p_score * w_phonetic) + (t_score * w_text)
        
        return min(100.0, max(0.0, final))
    
    def _get_tolerance_threshold(self, level: int, word_length: int, offset: float = 0) -> float:
        """
        Umbrales adaptativos según dificultad.
        Nivel 1 (palabras simples): más tolerante
        Nivel 5 (frases largas): más estricto
        """
        base_thresholds = {
            1: 60,  # Palabras simples - muy tolerante
            2: 65,  # Palabras medias
            3: 68,  # Frases cortas
            4: 72,  # Frases medias
            5: 75   # Frases largas - más estricto
        }
        
        threshold = base_thresholds.get(level, 70)
        
        # Ajustar por longitud de palabra/frase
        if word_length <= 3:
            threshold -= 5  # Palabras muy cortas son difíciles de captar
        elif word_length >= 20:
            threshold -= 3  # Frases muy largas tienen más posibilidad de error
        
        threshold = max(50, min(80, threshold))
        # Ajuste del terapeuta para este paciente (negativo = más tolerante), con límites
        return max(40, min(90, threshold + max(-15, min(15, offset))))
    
    def _calculate_phrase_similarity(self, transcription: str, target: str) -> float:
        """
        Comparación más flexible para frases.
        Considera palabras clave y permite variaciones comunes.
        """
        # Palabras que se pueden ignorar (stop words del español)
        stop_words = {
            'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 
            'de', 'del', 'al', 'a', 'en', 'por', 'para', 'con',
            'me', 'te', 'se', 'le', 'lo', 'que', 'y', 'o', 'pero',
            'mi', 'tu', 'su', 'muy', 'mas', 'ya'
        }
        
        # Normalizar y tokenizar
        trans_words = set(self._normalize_text(transcription).split())
        target_words = set(self._normalize_text(target).split())
        
        # Filtrar stop words para obtener palabras significativas
        trans_significant = trans_words - stop_words
        target_significant = target_words - stop_words
        
        if not target_significant:
            # Si el target solo tiene stop words, comparar todo
            target_significant = target_words
            trans_significant = trans_words
        
        if not target_significant:
            return 100 if not trans_significant else 0
        
        # Calcular palabras coincidentes (por fonética)
        matched = 0
        for tw in target_significant:
            tw_phone = self._spanish_metaphone(tw)
            best_match = 0
            for trw in trans_significant:
                trw_phone = self._spanish_metaphone(trw)
                similarity = self._string_similarity(tw_phone, trw_phone)
                best_match = max(best_match, similarity)
            if best_match > 75:  # Umbral de coincidencia fonética
                matched += 1
        
        # Score basado en cobertura de palabras clave
        coverage = (matched / len(target_significant)) * 100 if target_significant else 0
        
        # Penalización leve por palabras extra (posible ruido)
        extra_words = len(trans_significant) - len(target_significant)
        if extra_words > 2:
            coverage -= min(15, extra_words * 3)
        
        return max(0, coverage)
    
    def _detect_specific_errors(self, transcription: str, target: str) -> List[Dict]:
        """
        Detecta errores específicos de pronunciación y da consejos contextuales.
        Muy útil para rehabilitación vocal.
        """
        errors = []
        
        trans_norm = self._normalize_text(transcription)
        target_norm = self._normalize_text(target)
        
        trans_phone = self._spanish_metaphone(trans_norm)
        target_phone = self._spanish_metaphone(target_norm)
        
        # Error de truncamiento (palabra cortada)
        if len(trans_norm) < len(target_norm) * 0.6 and trans_norm:
            errors.append({
                "type": "truncation",
                "message": "La palabra parece estar incompleta",
                "tip": "Intenta pronunciar hasta el final de cada sílaba, sin cortarte"
            })
        
        # Error de omisión total
        if not trans_norm.strip():
            errors.append({
                "type": "silence",
                "message": "No se detectó audio claro",
                "tip": "Habla más fuerte y cerca del micrófono"
            })
            return errors
        
        # Error de confusión R/L (común en rehabilitación)
        if 'rr' in target_phone or 'r' in target_phone:
            if 'l' in trans_phone and 'l' not in target_phone:
                errors.append({
                    "type": "r_l_confusion",
                    "message": "Posible confusión entre R y L",
                    "tip": "Para la R, haz vibrar la punta de la lengua contra el paladar"
                })
        
        # Error con sonidos nasales (M/N/Ñ)
        nasal_target = target_phone.count('m') + target_phone.count('n') + target_phone.count('ny')
        nasal_trans = trans_phone.count('m') + trans_phone.count('n') + trans_phone.count('ny')
        if nasal_target > 0 and nasal_trans < nasal_target:
            errors.append({
                "type": "nasal_error",
                "message": "Falta pronunciar algún sonido nasal (M, N, Ñ)",
                "tip": "Los sonidos nasales requieren que el aire salga por la nariz"
            })
        
        # Error con sibilantes (S)
        s_target = target_phone.count('s')
        s_trans = trans_phone.count('s')
        if s_target > 0 and abs(s_target - s_trans) >= 1:
            if s_trans < s_target:
                errors.append({
                    "type": "sibilant_missing",
                    "message": "Falta pronunciar el sonido S",
                    "tip": "Pronuncia la S con los dientes casi cerrados y la lengua detrás"
                })
        
        # Error con sonido CH
        if 'x' in target_phone and 'x' not in trans_phone:
            errors.append({
                "type": "ch_error",
                "message": "Falta el sonido CH",
                "tip": "El sonido CH se forma bloqueando el aire con la lengua y soltándolo de golpe"
            })
        
        # Error con sonido J/G fuerte
        j_target = target_phone.count('j')
        j_trans = trans_phone.count('j')
        if j_target > 0 and j_trans < j_target:
            errors.append({
                "type": "j_error",
                "message": "Falta el sonido J (o G fuerte)",
                "tip": "El sonido J es fricativo, el aire pasa rozando el velo del paladar"
            })
        
        return errors[:3]  # Máximo 3 errores para no abrumar
    
    def _generate_feedback(self, score: float, transcription: str, target: str,
                           is_correct: Optional[bool] = None, threshold: float = 70) -> Dict[str, Any]:
        """Mensaje para el paciente. Usa el MISMO umbral que decide si es correcto (antes un 61 %
        salía «¡Correcto!» con el mensaje «intenta más despacio»)."""
        if is_correct is None:
            is_correct = score >= threshold
        if is_correct and score >= 90:
            level = "excellent"
            message = "¡Excelente! Lo dijiste muy bien."
            encouragement = "Sigue así."
            should_repeat = False
        elif is_correct:
            level = "good"
            message = "¡Bien dicho!"
            encouragement = "Puedes pasar a la siguiente o repetirla para afianzarla."
            should_repeat = False
        elif score >= threshold - 15:
            level = "fair"
            message = "Casi. Vas por buen camino."
            encouragement = "Escucha el ejemplo y dilo despacio y claro."
            should_repeat = True
        else:
            level = "retry"
            message = "Vamos a intentarlo otra vez."
            encouragement = "Escucha el ejemplo y repítelo con calma."
            should_repeat = True
        
        # Detectar diferencias específicas
        differences = self._find_differences(transcription, target)
        
        return {
            "level": level,
            "message": message,
            "encouragement": encouragement,
            "should_repeat": should_repeat,
            "differences": differences,
            "tips": self._get_pronunciation_tips(differences)
        }
    
    def _find_differences(self, transcription: str, target: str) -> list:
        """Encuentra diferencias específicas entre transcripción y objetivo"""
        differences = []
        
        # Si son iguales, no hay diferencias
        if transcription == target:
            return []
        
        # Si alguno está vacío
        if not transcription and target:
            return [{"position": 0, "expected": target, "heard": ""}]
        if transcription and not target:
            return [{"position": 0, "expected": "", "heard": transcription}]
        
        words_trans = transcription.split()
        words_target = target.split()
        
        # Comparar palabra por palabra
        max_len = max(len(words_trans), len(words_target))
        for i in range(max_len):
            w_trans = words_trans[i] if i < len(words_trans) else ""
            w_target = words_target[i] if i < len(words_target) else ""
            
            if w_trans != w_target:
                differences.append({
                    "position": i,
                    "expected": w_target,
                    "heard": w_trans
                })
        
        return differences
    
    def _get_pronunciation_tips(self, differences: list) -> list:
        """Genera tips de pronunciación basados en las diferencias"""
        # Si no hay diferencias, dar feedback positivo
        if not differences:
            return ["¡Excelente pronunciación!"]
        
        tips = []
        
        for diff in differences[:3]:  # Máximo 3 tips
            expected = diff.get("expected", "")
            heard = diff.get("heard", "")
            
            if not expected and heard:
                # Se escuchó algo extra
                tips.append(f"Se detectó '{heard}' adicional. Intenta decir solo la palabra objetivo.")
            elif expected and not heard:
                # Faltó pronunciar algo
                tips.append(f"Parece que faltó pronunciar '{expected}'.")
            elif expected and heard:
                # Diferencia en una palabra
                # Verificar si son fonéticamente similares
                tips.append(f"'{expected}' sonó como '{heard}'. Enfatiza cada sílaba.")
        
        if not tips:
            tips.append("Intenta hablar más despacio y claro.")
        
        return tips
    
    def _tts_cache_path(self, engine: str, text: str, voice: str, speed: str, ext: str) -> Path:
        """Ruta estable en caché para un audio TTS (misma entrada -> mismo archivo)."""
        key = hashlib.sha256(f"{engine}|{voice}|{speed}|{text}".encode("utf-8")).hexdigest()[:32]
        return TTS_CACHE_DIR / f"{engine}_{key}{ext}"

    async def text_to_speech(self, text: str, voice: str = "es-ES-ElviraNeural", speed: str = "normal") -> str:
        """Genera audio TTS: Piper (local, preferido); después las voces en línea si TTS_ONLINE=1;
        por último pyttsx3 (local). Si ninguno funciona lanza NoVoiceAvailableError: la página
        usará la voz del dispositivo."""
        output_path = os.path.join(self.temp_dir, f"tts_{datetime.now().timestamp()}.wav")

        # PIPER TTS (Offline, con caché propia). Es síncrono: se ejecuta en un hilo.
        if PIPER_INTEGRATION and PIPER_TTS:
            try:
                result = await asyncio.to_thread(PIPER_TTS.synthesize, text=text, slow_mode=(speed == "lenta"))
                if os.path.exists(result):
                    return result
            except Exception as e:
                print(f"⚠️ Piper: {e}")

        # Edge TTS (en línea, solo con TTS_ONLINE=1). Se guarda en caché persistente.
        if TTS_ONLINE and EDGE_TTS_AVAILABLE:
            cached_mp3 = self._tts_cache_path("edge", text, voice, speed, ".mp3")
            if cached_mp3.exists() and cached_mp3.stat().st_size > 0:
                return str(cached_mp3)
            try:
                tmp_mp3 = cached_mp3.with_suffix(f".{os.getpid()}.tmp")
                # Slight slowdown for better clarity in rehab context
                rate_map = {"lenta": "-30%", "normal": "-10%", "rapida": "+0%"}
                communicate = edge_tts.Communicate(text, voice, rate=rate_map.get(speed, "-10%"))  # pyright: ignore[reportPossiblyUnboundVariable]
                await communicate.save(str(tmp_mp3))
                os.replace(tmp_mp3, cached_mp3)
                return str(cached_mp3)
            except Exception as e:
                print(f"⚠️ EdgeTTS: {e}")

        # pyttsx3 (Offline fallback) - Run in executor to avoid blocking event loop
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._generate_pyttsx3_audio, text, output_path)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
        except Exception as e:
            print(f"⚠️ pyttsx3: {e}")
            
        # gTTS (en línea, solo con TTS_ONLINE=1)
        if not TTS_ONLINE:
            raise NoVoiceAvailableError("No hay motor de voz local disponible (¿Piper instalado?)")
        try:
            from gtts import gTTS  # pyright: ignore[reportMissingImports]
            cached_mp3 = self._tts_cache_path("gtts", text, "es", speed, ".mp3")
            if cached_mp3.exists() and cached_mp3.stat().st_size > 0:
                return str(cached_mp3)
            tmp_mp3 = str(cached_mp3.with_suffix(f".{os.getpid()}.tmp"))
            # Run gTTS in executor as it might block network
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: gTTS(text=text, lang='es', slow=True).save(tmp_mp3))
            os.replace(tmp_mp3, cached_mp3)
            return str(cached_mp3)
        except Exception as e:
            print(f"⚠️ gTTS: {e}")

        raise NoVoiceAvailableError("Ningún motor de voz pudo generar el audio")

    def _generate_pyttsx3_audio(self, text: str, output_path: str):
        """Helper for pyttsx3 to run in thread pool"""
        try:
            import pyttsx3  # pyright: ignore[reportMissingImports]
            engine = pyttsx3.init()
            for v in engine.getProperty('voices'):
                if "spanish" in v.name.lower() or "es" in v.id.lower():
                    engine.setProperty('voice', v.id)
                    break
            engine.setProperty('rate', 130)
            engine.save_to_file(text, output_path)
            engine.runAndWait()
        except Exception as e:
            print(f"Error in pyttsx3 worker: {e}")

    def get_available_voices(self) -> list:
        """Lista voces TTS disponibles para español"""
        return [
            {"id": "es-ES-AlvaroNeural", "name": "Álvaro (España)", "gender": "male"},
            {"id": "es-ES-ElviraNeural", "name": "Elvira (España)", "gender": "female"},
            {"id": "es-MX-DaliaNeural", "name": "Dalia (México)", "gender": "female"},
            {"id": "es-MX-JorgeNeural", "name": "Jorge (México)", "gender": "male"},
            {"id": "es-AR-ElenaNeural", "name": "Elena (Argentina)", "gender": "female"},
            {"id": "es-CO-GonzaloNeural", "name": "Gonzalo (Colombia)", "gender": "male"},
        ]


# Clase para uso offline con Vosk
class VoskProcessor:
    """Procesador específico para Vosk (offline)"""
    
    def __init__(self, model_path: str):
        if not VOSK_AVAILABLE:
            raise ImportError("Vosk no está instalado. Instalar con: pip install vosk")
        
        self.model = Model(model_path)  # pyright: ignore[reportPossiblyUnboundVariable]
    
    def transcribe_stream(self, audio_stream, sample_rate: int = 16000):
        """Transcripción en tiempo real"""
        rec = KaldiRecognizer(self.model, sample_rate)  # pyright: ignore[reportPossiblyUnboundVariable]
        
        for chunk in audio_stream:
            if rec.AcceptWaveform(chunk):
                result = json.loads(rec.Result())
                yield result.get("text", "")
        
        final = json.loads(rec.FinalResult())
        yield final.get("text", "")
