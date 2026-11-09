"""
🎙️ Piper TTS Module para Rehab Voice 2025
==========================================

Motor de Text-to-Speech usando Piper (rhasspy/piper)
- 100% Offline - No requiere internet
- Muy rápido en CPU (~50-100ms por palabra)
- Voces de alta calidad en español
- Ideal para rehabilitación vocal

Uso:
    from piper_tts import PiperTTS, get_tts_engine
    
    # Opción 1: Directo
    tts = PiperTTS()
    audio_path = tts.synthesize("Hola mundo")
    
    # Opción 2: Híbrido con fallbacks
    engine = get_tts_engine()
    audio_path = await engine.synthesize("Hola mundo")

Autor: Rehab Voice Team
Fecha: Diciembre 2025
"""

import os
import json
import asyncio
import tempfile
import subprocess
import hashlib
import importlib.util
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from datetime import datetime
import urllib.request
import shutil

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

@dataclass 
class PiperConfig:
    """Configuración para Piper TTS."""
    
    # Rutas
    piper_exe: str = ""  # Se auto-detecta
    voices_dir: str = "./voices/piper"
    cache_dir: str = "./cache/piper"
    
    # Voz por defecto (español México - Claude alta calidad)
    default_voice: str = "es_MX-claude-high"
    
    # Calidad
    # Opciones: x_low, low, medium, high
    default_quality: str = "high"
    
    # Audio
    sample_rate: int = 22050  # Hz (depende del modelo)
    
    # Caché
    enable_cache: bool = True
    max_cache_size_mb: int = 200
    
    # Velocidad (ajuste de hablado)
    length_scale: float = 1.0  # 1.0 = normal, >1 = más lento, <1 = más rápido
    
    # Para rehabilitación
    slow_mode_scale: float = 1.3  # 30% más lento


# Voces españolas disponibles en Piper
SPANISH_VOICES = {
    # España
    "es_ES-davefx-medium": {
        "name": "Davefx (España)",
        "gender": "male",
        "quality": "medium",
        "sample_rate": 22050,
        "url_model": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx",
        "url_config": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json",
    },
    "es_ES-sharvard-medium": {
        "name": "Sharvard (España)", 
        "gender": "male",
        "quality": "medium",
        "sample_rate": 22050,
        "url_model": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx",
        "url_config": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx.json",
    },
    "es_ES-carlfm-x_low": {
        "name": "Carlfm (España, ligero)",
        "gender": "male", 
        "quality": "x_low",
        "sample_rate": 16000,
        "url_model": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx",
        "url_config": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx.json",
    },
    # México
    "es_MX-claude-high": {
        "name": "Claude (México, alta calidad)",
        "gender": "male",
        "quality": "high", 
        "sample_rate": 22050,
        "url_model": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx",
        "url_config": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx.json",
    },
    "es_MX-ald-medium": {
        "name": "Ald (México)",
        "gender": "male",
        "quality": "medium",
        "sample_rate": 22050,
        "url_model": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/ald/medium/es_MX-ald-medium.onnx",
        "url_config": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/ald/medium/es_MX-ald-medium.onnx.json",
    },
}

# Voz recomendada para rehabilitación
RECOMMENDED_VOICE = "es_MX-claude-high"


# ============================================================================
# CLASE PRINCIPAL: PiperTTS
# ============================================================================

class PiperTTS:
    """
    Motor TTS usando Piper - Rápido, offline, alta calidad.
    Optimizado para rehabilitación vocal en español.
    """
    
    def __init__(self, config: Optional[PiperConfig] = None):
        """
        Inicializa Piper TTS.
        
        Args:
            config: Configuración personalizada
        """
        self.config = config or PiperConfig()
        self.piper_exe: Optional[str] = None
        self.current_voice: Optional[str] = None
        self.current_voice_config: Optional[Dict] = None
        self._audio_cache: Dict[str, str] = {}
        self._cache_stats = {"hits": 0, "misses": 0}
        
        # Crear directorios
        Path(self.config.voices_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.cache_dir).mkdir(parents=True, exist_ok=True)
        
        # Cargar caché
        self._load_cache_index()
        
        # Detectar ejecutable de Piper
        self._detect_piper()
    
    def _detect_piper(self):
        """Detecta la ubicación del ejecutable de Piper."""
        possible_paths = [
            # Configurado manualmente
            self.config.piper_exe,
            # Windows
            "./piper/piper.exe",
            "./piper.exe",
            str(Path(self.config.voices_dir).parent / "piper" / "piper.exe"),
            # Linux/Mac
            "./piper/piper",
            "./piper",
            "/usr/local/bin/piper",
            "/usr/bin/piper",
            str(Path.home() / ".local" / "bin" / "piper"),
        ]
        
        for path in possible_paths:
            if path and Path(path).exists():
                self.piper_exe = str(Path(path).absolute())
                print(f"✅ Piper encontrado: {self.piper_exe}")
                return
        
        # Intentar encontrar en PATH
        try:
            result = subprocess.run(
                ["where" if os.name == "nt" else "which", "piper"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                self.piper_exe = result.stdout.strip().split('\n')[0]
                print(f"✅ Piper en PATH: {self.piper_exe}")
                return
        except Exception:
            pass
        
        print("⚠️ Piper no encontrado. Coloca el ejecutable de Piper en la carpeta piper/.")
    
    def _load_cache_index(self):
        """Carga índice de caché."""
        index_path = Path(self.config.cache_dir) / "cache_index.json"
        if index_path.exists():
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    self._audio_cache = json.load(f)
                # Limpiar entradas inválidas
                self._audio_cache = {
                    k: v for k, v in self._audio_cache.items()
                    if Path(v).exists()
                }
            except Exception:
                self._audio_cache = {}
    
    def _save_cache_index(self):
        """Guarda índice de caché."""
        index_path = Path(self.config.cache_dir) / "cache_index.json"
        try:
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(self._audio_cache, f)
        except Exception as e:
            print(f"⚠️ Error guardando caché: {e}")
    
    def _get_cache_key(self, text: str, voice: str, length_scale: float) -> str:
        """Genera clave única para caché."""
        data = f"{text}|{voice}|{length_scale}"
        return hashlib.md5(data.encode()).hexdigest()
    
    def is_installed(self) -> bool:
        """Verifica si Piper está instalado."""
        return self.piper_exe is not None and Path(self.piper_exe).exists()
    
    def get_available_voices(self) -> List[Dict[str, Any]]:
        """Lista voces instaladas localmente."""
        voices = []
        voices_path = Path(self.config.voices_dir)
        
        for onnx_file in voices_path.glob("*.onnx"):
            voice_id = onnx_file.stem
            config_file = onnx_file.with_suffix(".onnx.json")
            
            if config_file.exists():
                try:
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                    
                    voices.append({
                        "id": voice_id,
                        "name": SPANISH_VOICES.get(voice_id, {}).get("name", voice_id),
                        "gender": SPANISH_VOICES.get(voice_id, {}).get("gender", "unknown"),
                        "quality": SPANISH_VOICES.get(voice_id, {}).get("quality", "medium"),
                        "sample_rate": config.get("audio", {}).get("sample_rate", 22050),
                        "path": str(onnx_file),
                    })
                except Exception:
                    voices.append({
                        "id": voice_id,
                        "name": voice_id,
                        "path": str(onnx_file),
                    })
        
        return voices
    
    def download_voice(
        self,
        voice_id: str,
        progress_callback: Optional[Callable[..., Any]] = None
    ) -> bool:
        """
        Descarga una voz de HuggingFace.
        
        Args:
            voice_id: ID de la voz (ej: "es_ES-davefx-medium")
            progress_callback: Función para reportar progreso
        
        Returns:
            True si se descargó correctamente
        """
        if voice_id not in SPANISH_VOICES:
            print(f"❌ Voz no reconocida: {voice_id}")
            print(f"   Voces disponibles: {list(SPANISH_VOICES.keys())}")
            return False
        
        voice_info = SPANISH_VOICES[voice_id]
        voices_path = Path(self.config.voices_dir)
        
        model_path = voices_path / f"{voice_id}.onnx"
        config_path = voices_path / f"{voice_id}.onnx.json"
        
        # Verificar si ya existe
        if model_path.exists() and config_path.exists():
            print(f"ℹ️ Voz ya instalada: {voice_id}")
            return True
        
        print(f"📥 Descargando voz: {voice_info['name']}...")
        
        try:
            # Descargar modelo
            print(f"   Descargando modelo (~50-100MB)...")
            if progress_callback:
                progress_callback("model", 0, 100)
            
            urllib.request.urlretrieve(
                voice_info["url_model"],
                str(model_path)
            )
            
            if progress_callback:
                progress_callback("model", 100, 100)
            
            # Descargar configuración
            print(f"   Descargando configuración...")
            urllib.request.urlretrieve(
                voice_info["url_config"],
                str(config_path)
            )
            
            print(f"✅ Voz instalada: {voice_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error descargando voz: {e}")
            # Limpiar archivos parciales
            if model_path.exists():
                model_path.unlink()
            if config_path.exists():
                config_path.unlink()
            return False
    
    def ensure_voice(self, voice_id: Optional[str] = None) -> bool:
        """
        Asegura que una voz esté disponible, descargándola si es necesario.
        
        Args:
            voice_id: ID de la voz (None = usar default)
        
        Returns:
            True si la voz está disponible
        """
        voice_id = voice_id or self.config.default_voice
        
        model_path = Path(self.config.voices_dir) / f"{voice_id}.onnx"
        config_path = Path(self.config.voices_dir) / f"{voice_id}.onnx.json"
        
        if model_path.exists() and config_path.exists():
            return True
        
        return self.download_voice(voice_id)
    
    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        output_path: Optional[str] = None,
        slow_mode: bool = False,
        use_cache: bool = True
    ) -> str:
        """
        Sintetiza texto a audio.
        
        Args:
            text: Texto a sintetizar
            voice: ID de voz (None = default)
            output_path: Ruta de salida (None = temporal)
            slow_mode: Pronunciación más lenta para rehabilitación
            use_cache: Usar caché de audio
        
        Returns:
            Ruta al archivo WAV generado
        """
        if not self.is_installed():
            raise RuntimeError(
                "Piper no está instalado. Coloca el ejecutable de Piper en la carpeta piper/"
            )
        
        voice = voice or self.config.default_voice
        
        # Asegurar que la voz existe
        if not self.ensure_voice(voice):
            raise RuntimeError(f"No se pudo obtener la voz: {voice}")
        
        # Calcular escala de velocidad
        length_scale = self.config.slow_mode_scale if slow_mode else self.config.length_scale
        
        # Verificar caché
        cache_key = self._get_cache_key(text, voice, length_scale)
        
        if use_cache and self.config.enable_cache:
            if cache_key in self._audio_cache:
                cached_path = self._audio_cache[cache_key]
                if Path(cached_path).exists():
                    self._cache_stats["hits"] += 1
                    return cached_path
        
        self._cache_stats["misses"] += 1
        
        # Preparar rutas
        model_path = Path(self.config.voices_dir) / f"{voice}.onnx"
        
        if output_path is None:
            output_path = os.path.join(
                self.config.cache_dir,
                f"piper_{cache_key}.wav"
            )
        
        # Construir comando
        cmd = [
            self.piper_exe,
            "--model", str(model_path),
            "--output_file", output_path,
            "--length_scale", str(length_scale),
        ]
        
        try:
            # Ejecutar Piper
            process = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=30  # 30 segundos timeout
            )
            
            if process.returncode != 0:
                raise RuntimeError(f"Piper error: {process.stderr}")
            
            if not Path(output_path).exists():
                raise RuntimeError("Piper no generó archivo de salida")
            
            # Actualizar caché
            if use_cache and self.config.enable_cache:
                self._audio_cache[cache_key] = output_path
                self._save_cache_index()
            
            return output_path
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("Piper timeout - texto muy largo?")
        except Exception as e:
            raise RuntimeError(f"Error ejecutando Piper: {e}")
    
    async def synthesize_async(
        self,
        text: str,
        **kwargs
    ) -> str:
        """Versión asíncrona de synthesize."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.synthesize(text, **kwargs)
        )
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas de caché."""
        total = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = (self._cache_stats["hits"] / total * 100) if total > 0 else 0
        
        cache_size = sum(
            Path(p).stat().st_size
            for p in self._audio_cache.values()
            if Path(p).exists()
        ) / 1024**2
        
        return {
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "hit_rate": f"{hit_rate:.1f}%",
            "cached_items": len(self._audio_cache),
            "cache_size_mb": f"{cache_size:.1f}",
        }
    
    def clear_cache(self):
        """Limpia el caché de audio."""
        for path in self._audio_cache.values():
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
        
        self._audio_cache.clear()
        self._save_cache_index()
        self._cache_stats = {"hits": 0, "misses": 0}
        print("✅ Caché limpiado")


# ============================================================================
# CLASE HÍBRIDA: HybridTTS
# ============================================================================

class HybridTTS:
    """
    Motor TTS híbrido que usa Piper con fallbacks.
    
    Orden de preferencia:
    1. Piper (offline, rápido)
    2. Edge TTS (online, alta calidad)
    3. gTTS (online, backup)
    4. pyttsx3 (offline, baja calidad)
    """
    
    def __init__(self, piper_config: Optional[PiperConfig] = None):
        self.piper: Optional[PiperTTS] = None
        self.temp_dir = tempfile.gettempdir()
        
        # Estadísticas
        self._engine_usage = {
            "piper": 0,
            "edge_tts": 0,
            "gtts": 0,
            "pyttsx3": 0,
            "failed": 0,
        }
        
        # Inicializar Piper
        try:
            self.piper = PiperTTS(piper_config)
            if self.piper.is_installed():
                print("✅ Piper TTS disponible")
            else:
                print("⚠️ Piper no instalado, usando fallbacks")
        except Exception as e:
            print(f"⚠️ Error inicializando Piper: {e}")
        
        # Verificar fallbacks
        self._check_fallbacks()
    
    def _check_fallbacks(self):
        """Verifica disponibilidad de fallbacks."""
        self._has_edge_tts = importlib.util.find_spec("edge_tts") is not None
        self._has_gtts = importlib.util.find_spec("gtts") is not None
        self._has_pyttsx3 = importlib.util.find_spec("pyttsx3") is not None
        
        print(f"   Fallbacks: Edge={'✅' if self._has_edge_tts else '❌'}, "
              f"gTTS={'✅' if self._has_gtts else '❌'}, "
              f"pyttsx3={'✅' if self._has_pyttsx3 else '❌'}")
    
    async def synthesize(
        self,
        text: str,
        voice: str = "es-ES-AlvaroNeural",
        language: str = "es",
        slow_mode: bool = False,
        force_engine: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Sintetiza texto usando el mejor motor disponible.
        
        Args:
            text: Texto a sintetizar
            voice: Voz (formato depende del motor)
            language: Código de idioma
            slow_mode: Pronunciación lenta
            force_engine: Forzar motor específico
        
        Returns:
            Ruta al archivo de audio
        """
        # Motor forzado
        if force_engine:
            return await self._synth_with_engine(
                force_engine, text, voice, slow_mode
            )
        
        # Intentar en orden
        engines = []
        
        if self.piper and self.piper.is_installed():
            engines.append("piper")
        
        if self._has_edge_tts:
            engines.append("edge_tts")
        
        if self._has_gtts:
            engines.append("gtts")
        
        if self._has_pyttsx3:
            engines.append("pyttsx3")
        
        last_error = None
        for engine in engines:
            try:
                result = await self._synth_with_engine(
                    engine, text, voice, slow_mode
                )
                self._engine_usage[engine] += 1
                return result
            except Exception as e:
                print(f"⚠️ {engine} falló: {e}")
                last_error = e
        
        self._engine_usage["failed"] += 1
        raise RuntimeError(f"Todos los motores TTS fallaron: {last_error}")
    
    async def _synth_with_engine(
        self,
        engine: str,
        text: str,
        voice: str,
        slow_mode: bool
    ) -> str:
        """Sintetiza con un motor específico."""
        
        if engine == "piper":
            if self.piper is None:
                raise RuntimeError("Piper no está inicializado")
            return await self.piper.synthesize_async(
                text=text,
                slow_mode=slow_mode
            )
        
        elif engine == "edge_tts":
            import edge_tts
            output = os.path.join(self.temp_dir, f"edge_{datetime.now().timestamp()}.mp3")
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output)
            return output
        
        elif engine == "gtts":
            from gtts import gTTS  # pyright: ignore[reportMissingImports]
            output = os.path.join(self.temp_dir, f"gtts_{datetime.now().timestamp()}.mp3")
            
            def _gen():
                tts = gTTS(text=text, lang="es", slow=slow_mode)
                tts.save(output)
            
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _gen)
            return output
        
        elif engine == "pyttsx3":
            import pyttsx3  # pyright: ignore[reportMissingImports]
            output = os.path.join(self.temp_dir, f"pyttsx3_{datetime.now().timestamp()}.wav")
            
            def _gen():
                engine = pyttsx3.init()
                for v in engine.getProperty('voices'):
                    if "spanish" in v.name.lower():
                        engine.setProperty('voice', v.id)
                        break
                if slow_mode:
                    engine.setProperty('rate', 120)
                engine.save_to_file(text, output)
                engine.runAndWait()
            
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _gen)
            return output
        
        else:
            raise ValueError(f"Motor desconocido: {engine}")
    
    def preload_voice(self, voice_id: Optional[str] = None) -> bool:
        """Pre-carga una voz de Piper."""
        if self.piper:
            return self.piper.ensure_voice(voice_id)
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas de uso."""
        stats = {
            "engine_usage": self._engine_usage.copy(),
            "piper_installed": self.piper.is_installed() if self.piper else False,
        }
        
        if self.piper:
            stats["piper_cache"] = self.piper.get_cache_stats()
            stats["piper_voices"] = len(self.piper.get_available_voices())
        
        return stats


# ============================================================================
# UTILIDADES
# ============================================================================

class PronunciationCache:
    """Caché persistente de pronunciaciones para rehabilitación."""
    
    def __init__(
        self,
        cache_dir: str = "./cache/pronunciations",
        tts_engine: Optional[HybridTTS] = None
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.tts = tts_engine or HybridTTS()
        self.index: Dict[str, str] = {}
        self._load_index()
    
    def _load_index(self):
        index_path = self.cache_dir / "index.json"
        if index_path.exists():
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    self.index = json.load(f)
                self.index = {
                    k: v for k, v in self.index.items()
                    if Path(v).exists()
                }
            except Exception:
                self.index = {}
    
    def _save_index(self):
        index_path = self.cache_dir / "index.json"
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)
    
    async def get_or_generate(self, word: str, slow_mode: bool = True) -> str:
        """Obtiene audio de caché o genera nuevo."""
        key = word.lower().strip()
        
        if key in self.index and Path(self.index[key]).exists():
            return self.index[key]
        
        # Generar
        audio_path = await self.tts.synthesize(
            text=word,
            slow_mode=slow_mode
        )
        
        # Copiar a caché permanente
        permanent = self.cache_dir / f"{hashlib.md5(key.encode()).hexdigest()}.wav"
        shutil.copy(audio_path, permanent)
        
        self.index[key] = str(permanent)
        self._save_index()
        
        return str(permanent)
    
    async def pre_generate(
        self,
        words: List[str],
        progress_callback: Optional[Callable[..., Any]] = None
    ) -> int:
        """Pre-genera audio para lista de palabras."""
        generated = 0
        total = len(words)
        
        for i, word in enumerate(words):
            try:
                await self.get_or_generate(word)
                generated += 1
                
                if progress_callback:
                    progress_callback(i + 1, total, word)
                elif (i + 1) % 10 == 0:
                    print(f"   Progreso: {i + 1}/{total}")
            except Exception as e:
                print(f"   ⚠️ Error en '{word}': {e}")
        
        return generated


# ============================================================================
# SINGLETON
# ============================================================================

_tts_engine: Optional[HybridTTS] = None

def get_tts_engine(force_new: bool = False) -> HybridTTS:
    """Obtiene instancia singleton del motor TTS."""
    global _tts_engine
    if _tts_engine is None or force_new:
        _tts_engine = HybridTTS()
    return _tts_engine


# ============================================================================
# MAIN - Test
# ============================================================================

if __name__ == "__main__":
    async def test():
        print("🧪 Test de Piper TTS")
        print("=" * 50)
        
        # Test PiperTTS directo
        print("\n1. Probando PiperTTS directo...")
        try:
            piper = PiperTTS()
            
            if piper.is_installed():
                print("   Piper instalado ✅")
                
                # Asegurar voz
                if piper.ensure_voice():
                    print("   Voz disponible ✅")
                    
                    # Generar audio
                    path = piper.synthesize("Hola, esto es una prueba")
                    print(f"   Audio generado: {path} ✅")
                else:
                    print("   No se pudo obtener voz ❌")
            else:
                print("   Piper no instalado ⚠️")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Test HybridTTS
        print("\n2. Probando HybridTTS...")
        try:
            hybrid = HybridTTS()
            
            test_words = ["Buenos días", "Adiós", "Gracias"]
            
            for word in test_words:
                path = await hybrid.synthesize(word)
                print(f"   '{word}' -> {path} ✅")
            
            print(f"\n   Stats: {hybrid.get_stats()}")
        except Exception as e:
            print(f"   Error: {e}")
    
    asyncio.run(test())
