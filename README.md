# 🎤 Rehab Voice 2025

> **Aplicación de Rehabilitación Vocal con Inteligencia Artificial**

Una aplicación web moderna para ayudar a personas en rehabilitación vocal a practicar y mejorar su pronunciación de manera progresiva, desde palabras básicas hasta frases completas.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)
![Whisper](https://img.shields.io/badge/OpenAI-Whisper-orange.svg)
![License](https://img.shields.io/badge/License-MIT-purple.svg)

---

## ✨ Características Principales

### 🎙️ Reconocimiento de Voz
- **Whisper (OpenAI)**: Motor principal con 50% menos errores
- **Comparación fonética**: Algoritmos Soundex, Metaphone, Double Metaphone
- **Análisis en tiempo real**: Feedback inmediato sobre pronunciación

### 📈 Progresión Estructurada
- **5 niveles de dificultad**: De palabras simples a frases complejas
- **9 categorías**: Necesidades básicas, comida, emociones, familia, etc.
- **+200 palabras/frases** preconfiguradas en español

### 🎮 Gamificación
- **Sistema de puntos** por cada intento
- **15+ logros** desbloqueables
- **Desafíos diarios** para mantener motivación
- **Rachas de práctica** con bonus

### 📊 Seguimiento de Progreso
- **Estadísticas detalladas** por sesión y acumuladas
- **Gráficos de evolución** temporal
- **Identificación de palabras difíciles**

---

## 🚀 Instalación Rápida

### Requisitos Previos
- Python 3.9 o superior
- FFmpeg (para procesamiento de audio)
- Micrófono funcional

### Paso 1: Clonar/Descargar el Proyecto

```bash
# Si descargaste el ZIP, descomprímelo
# O clona el repositorio
cd rehab_voice_2025
```

### Paso 2: Crear Entorno Virtual

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### Paso 3: Instalar Dependencias

```bash
pip install -r requirements.txt
```

### Paso 4: Instalar FFmpeg

**Windows:**
```bash
# Con Chocolatey
choco install ffmpeg

# O descargar de https://ffmpeg.org/download.html
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Mac:**
```bash
brew install ffmpeg
```

### Paso 5: Ejecutar la Aplicación

```bash
python app.py
```

O con uvicorn directamente:
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Paso 6: Abrir en el Navegador

```
http://localhost:8000
```

---

## 📁 Estructura del Proyecto

```
rehab_voice_2025/
├── app.py                 # Aplicación principal FastAPI
├── voice_processor.py     # Procesamiento de voz (Whisper)
├── database.py            # Base de datos SQLite
├── game_engine.py         # Sistema de gamificación
├── requirements.txt       # Dependencias Python
├── README.md              # Este archivo
│
├── static/
│   ├── css/
│   │   └── style.css      # Estilos personalizados
│   ├── js/
│   │   └── app.js         # JavaScript principal
│   └── audio/             # Audios generados (TTS)
│
├── templates/
│   ├── index.html         # Página principal
│   ├── practice.html      # Página de práctica
│   ├── games.html         # Página de juegos
│   └── progress.html      # Página de progreso
│
├── data/
│   └── rehab_voice.db     # Base de datos SQLite (se crea automáticamente)
│
└── models/                # Modelos de voz (opcional)
```

---

## 🎯 Cómo Usar

### 1. Práctica de Palabras

1. Ve a **"Practicar"** desde el menú
2. Selecciona una **categoría** (ej: Necesidades Básicas)
3. Elige el **nivel** de dificultad
4. Haz clic en **"Cargar"** para ver las palabras
5. Selecciona una palabra de la lista
6. Escucha la pronunciación correcta con el botón 🔊
7. Presiona el botón rojo 🎤 para grabar tu voz
8. Recibe **feedback inmediato** con puntuación y consejos

### 2. Sistema de Niveles

| Nivel | Contenido | Ejemplo |
|-------|-----------|---------|
| 1 | Palabras simples | "agua", "pan", "sí" |
| 2 | Palabras compuestas | "desayuno", "comida" |
| 3 | Frases cortas | "quiero agua" |
| 4 | Frases medias | "necesito ir al baño" |
| 5 | Frases largas | "me gustaría un poco de agua por favor" |

### 3. Categorías Disponibles

- 🏠 **Necesidades Básicas**: sí, no, ayuda, agua, baño
- 🍽️ **Comida y Bebida**: pan, leche, hambre, sed
- ❤️ **Cuerpo y Salud**: dolor, cabeza, mano, descansar
- 😊 **Emociones**: feliz, triste, miedo, amor
- 👨‍👩‍👧 **Familia**: mamá, papá, hermano, familia
- 📍 **Lugares**: casa, hospital, baño, cuarto
- 🕐 **Tiempo**: hoy, mañana, ahora, luego
- 🏃 **Acciones**: comer, beber, dormir, caminar
- 💬 **Frases Comunes**: gracias, por favor, buenos días

---

## 🔧 Configuración Avanzada

### Cambiar el Modelo de Whisper

En `voice_processor.py`, línea ~45:

```python
# Opciones: tiny, base, small, medium, large
self.whisper_model = whisper.load_model("base")  # Cambiar aquí
```

| Modelo | Tamaño | Velocidad | Precisión |
|--------|--------|-----------|-----------|
| tiny | 39 MB | Muy rápido | Básica |
| base | 74 MB | Rápido | Buena |
| small | 244 MB | Medio | Muy buena |
| medium | 769 MB | Lento | Excelente |
| large | 1550 MB | Muy lento | Máxima |

### Agregar Palabras Personalizadas

**Vía API:**
```bash
curl -X POST http://localhost:8000/api/words \
  -H "Content-Type: application/json" \
  -d '{"word": "nueva palabra", "category_id": "basic_needs", "level": 2}'
```

**Directamente en base de datos:**
```python
from database import Database
db = Database()
db.add_word({
    "word": "mi palabra",
    "category_id": "custom",
    "level": 1,
    "phonetic_hint": "mi-pa-la-bra"
})
```

### Configurar Voces TTS

En `voice_processor.py`, las voces disponibles son:

```python
# Español España
"es-ES-AlvaroNeural"   # Masculina
"es-ES-ElviraNeural"   # Femenina

# Español México
"es-MX-DaliaNeural"    # Femenina
"es-MX-JorgeNeural"    # Masculino

# Español Argentina
"es-AR-ElenaNeural"    # Femenina

# Español Colombia
"es-CO-GonzaloNeural"  # Masculino
```

---

## 📡 API Endpoints

### Voz
- `POST /api/analyze-voice` - Analiza audio y compara con palabra objetivo
- `POST /api/transcribe` - Solo transcribe audio
- `GET /api/speak/{text}` - Genera audio TTS

### Palabras
- `GET /api/categories` - Lista categorías
- `GET /api/words/{category}?level=1` - Palabras por categoría
- `POST /api/words` - Agregar palabra personalizada

### Progreso
- `GET /api/progress/{patient_id}` - Progreso del paciente
- `POST /api/progress` - Guardar intento
- `GET /api/stats/{patient_id}` - Estadísticas detalladas

### Juegos
- `GET /api/games/daily-challenge` - Desafío del día
- `GET /api/games/achievements/{patient_id}` - Logros

---

## 🐛 Solución de Problemas

### "No se pudo acceder al micrófono"
- Asegúrate de dar permisos de micrófono en el navegador
- Usa HTTPS o localhost (los navegadores bloquean audio en HTTP)

### "Whisper no disponible"
```bash
pip install openai-whisper
# También necesitas FFmpeg instalado
```

### "Error al reproducir audio"
- Verifica que `edge-tts` esté instalado
- Comprueba conexión a internet (TTS usa servicios online)

### La base de datos no se crea
```bash
# Crear carpeta data manualmente
mkdir data
python -c "from database import Database; Database().initialize()"
```

---

## 🤝 Tecnologías Utilizadas

| Tecnología | Uso |
|------------|-----|
| **FastAPI** | Backend web moderno y rápido |
| **Whisper** | Reconocimiento de voz de OpenAI |
| **Edge TTS** | Text-to-Speech de Microsoft |
| **SQLite** | Base de datos ligera |
| **Tailwind CSS** | Estilos modernos |
| **Chart.js** | Gráficos de progreso |

---

## 📜 Licencia

Este proyecto es de código abierto bajo licencia MIT.

---

## 👨‍💻 Desarrollado por

**Orlando** - Agent Dragon  
Proyecto de rehabilitación vocal con IA - 2025

---

## 🙏 Agradecimientos

- OpenAI por Whisper
- Microsoft por Edge TTS
- La comunidad de FastAPI
- Todos los profesionales de fonoaudiología que inspiraron este proyecto

---

*¡Que cada palabra sea un paso hacia la recuperación! 🎤✨*
