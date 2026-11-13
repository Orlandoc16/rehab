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

### 💬 Comunicador y práctica (mejoras traídas de la app móvil)
- **Barra rápida Sí / No / ¡Ayuda!** siempre a la vista; «¡Ayuda!» se dice al momento
- **Recientes**: las últimas frases dichas se repiten con un toque (se guardan en el equipo, por paciente)
- **Tablet u ordenador en horizontal**: el tablero a la izquierda y la frase a la derecha
- **Pista «Por sílabas»** en la práctica («ca, mi, nar», muy despacio) además de «Escuchar»
- **Veredicto claro** «Bien / Casi / Otra vez», y la velocidad de la voz modelo se recuerda por paciente
- **Progreso según la valoración del terapeuta**: porcentaje de correctos, barras diarias de
  correctos y por mejorar, e intentos marcados como «valorado por el terapeuta»
- La pantalla no se apaga durante la práctica y la voz modelo se calla al empezar a grabar
- **Ficha del paciente** (en *Pacientes* → «Editar ficha»): cambiar nombre, edad, diagnóstico y
  notas, o borrar al paciente con todo su progreso (pide confirmación; no se puede deshacer)

### 🧑‍⚕️ Para el trabajo diario del terapeuta
- **Informe para imprimir** (en *Progreso* → «Informe para imprimir», o `/report`): una hoja por
  paciente con el resumen del periodo (7 días, 30 días, 3 meses o todo), la evolución por semanas,
  las categorías, las palabras que más cuestan y las que domina, y un hueco para observaciones y
  firma. Se imprime o se guarda como PDF desde el navegador (solo en la web, no en la app Android).
- **Repaso de palabras difíciles** (en *Practicar*, primera opción del selector, o desde
  *Progreso*): una sesión con las palabras que el paciente falla, de cualquier categoría. Entra una
  palabra si acierta menos del 60 % de sus intentos o si falló la última vez; cada una se evalúa
  con su propio nivel.
- **Comunicador a medida de cada paciente** (en *Comunicador* → ⚙ → «Personalizar el tablero»):
  frases propias que se dicen con un toque (pestaña «Mis frases») y pictogramas que se ocultan si
  ese paciente no los usa. Se guarda en su ficha (`/api/aac/profile`) y funciona sin conexión.

### 🎮 Gamificación
- **Sistema de puntos** por cada intento
- **15+ logros** desbloqueables
- **Desafíos diarios** para mantener motivación
- **Rachas de práctica** con bonus

### 🕹️ Juegos (sin reloj y sin castigo)
Nueve juegos en `/games`, agrupados por lo que trabajan:

| Grupo | Juego | Qué se hace |
| --- | --- | --- |
| Hablar | **¿Qué es?** | Decir el nombre del dibujo. Pistas graduadas: primera sílaba y, si hace falta, la palabra entera para repetirla. |
| Hablar | **Palabras seguidas** | Decir diez palabras al ritmo de cada uno; cuenta la racha (sustituye a la «Ronda rápida» contrarreloj). |
| Hablar | **Voz larga** | Sostener «aaaa» para llevar un barco a la meta (3, 5 u 8 segundos). Solo mide el volumen: no graba ni envía audio. |
| Hablar | **Completa la frase** | Elegir la palabra que falta y después decir la frase entera. |
| Escuchar | **Escucha y elige** | Oír una palabra y tocar su dibujo; en el nivel 3 las opciones se parecen. |
| Escuchar | **Palabras parecidas** | Pares mínimos («pato / gato»): cuál se ha oído, o si dos palabras son iguales o distintas. |
| Escuchar | **Clasificar palabras** | A qué grupo pertenece; en el nivel 3 alterna con «¿cuál no pertenece?». |
| Ocio | **Parejas** | Encontrar parejas de pictogramas y nombrarlas (sustituye a «Memoria»). |
| Ocio | **Laberinto de voz** | Guiar al mono diciendo «Arriba», «Abajo»… |

- **Dificultad 1-3 que se ajusta sola**: sube si la última partida pasó del 85 % y baja si quedó por
  debajo del 50 %. El terapeuta puede cambiarla antes de empezar.
- **El micrófono ayuda, no juzga**: en los juegos de hablar siempre hay un botón «La dije bien» para
  el paciente o quien le acompaña, así que funcionan aunque no haya reconocimiento de voz.
- **Repaso**: «¿Qué es?» y «Palabras seguidas» sacan más a menudo las palabras que el paciente falla
  en la práctica.
- **Sin rojo ni tachados**: un fallo se señala con suavidad y se puede seguir probando.
- Las partidas se guardan aparte de los intentos de pronunciación (no alteran el progreso ni la
  repetición espaciada) y salen en una sección propia del informe.

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

### Paso 5: Crear la cuenta de terapeuta

La app requiere iniciar sesión. Las cuentas se crean en el propio equipo (no hay registro
desde la web, para que nadie ajeno pueda crearse una en la red de la clínica):

```bash
python tools/create_therapist.py
# Cambiar una contraseña (cierra sus sesiones abiertas):
python tools/create_therapist.py --username ana --reset-password
```

### Paso 6: Ejecutar la Aplicación

```bash
python app.py
```

Por defecto solo escucha en este equipo (`127.0.0.1`). Para desarrollo con recarga
automática: `RELOAD=1 python app.py`.

### Paso 7: Abrir en el Navegador

```
http://localhost:8000
```

Inicia sesión, elige (o crea) el paciente y empieza. El paciente activo se ve en la
cabecera; al pulsarlo se cambia.

---

## 🏥 Despliegue en la clínica (red local con HTTPS)

Las tablets necesitan **HTTPS**: sin él, los navegadores bloquean el micrófono y el modo
sin conexión. La app se queda escuchando solo en el PC de la clínica y **Caddy** la
publica en la red con HTTPS.

1. **IP fija para el PC** de la clínica (reserva DHCP en el router). Consulta la IP con `ipconfig`.
2. **Instala Caddy** (https://caddyserver.com/download) y edita `deploy/Caddyfile`:
   cambia `192.168.1.50` por esa IP.
3. **Permite el puerto 443** en el Firewall de Windows para Caddy.
4. **Crea las cuentas** de los terapeutas: `python tools/create_therapist.py`.
5. **Arranca** la app con `deploy\start_clinic.bat` y, en otra ventana,
   `caddy run --config deploy\Caddyfile`.
6. **Instala el certificado de Caddy en cada tablet (una sola vez).** Caddy crea una
   autoridad certificadora local; en Windows su certificado está en
   `%AppData%\Caddy\pki\authorities\local\root.crt`. Cópialo a la tablet y:
   - **Android:** Ajustes → Seguridad → Cifrado y credenciales → Instalar un certificado →
     Certificado de CA.
   - **iPad:** abre el archivo (AirDrop o correo) → Ajustes → Perfil descargado → Instalar;
     después Ajustes → General → Información → Ajustes de confianza de certificados →
     activa el certificado.
7. En la tablet abre `https://IP-del-PC`, inicia sesión y, desde el menú del navegador,
   **"Añadir a pantalla de inicio"**: la app queda instalada y el comunicador funciona
   aunque falle la red.

> Guarda una copia del archivo `root.crt` y de la carpeta `data/` (la base de datos con los
> pacientes). La carpeta `data/` contiene datos de salud: no la subas a GitHub ni la
> compartas.

---

## 📁 Estructura del Proyecto

```
├── app.py                 # Punto de entrada (python app.py / uvicorn app:app)
├── rehab/                 # Capa web (FastAPI)
│   ├── main.py            # Crea la aplicación: middlewares, estáticos y routers
│   ├── settings.py        # Configuración (variables de entorno)
│   ├── services.py        # Instancias compartidas: base de datos, voz, juegos
│   ├── security.py        # Sesión obligatoria y paciente activo
│   ├── schemas.py         # Validación de los cuerpos JSON (Pydantic)
│   ├── web.py             # Plantillas, estáticos con caché, gzip
│   └── routers/           # accounts, pages, speech, content, progress, samples
├── database.py            # Modelos y consultas (SQLAlchemy); PICTOGRAM_IMAGES del comunicador
├── word_images.py         # Pictograma de cada palabra de práctica
├── voice_processor.py     # Reconocimiento (Whisper) y puntuación de la pronunciación
├── piper_tts.py           # Síntesis de voz local (Piper)
├── game_engine.py         # Puntos, logros y desafíos
├── auth.py                # Contraseñas, tokens de sesión, límite de intentos
├── templates/             # base.html, partials/_ui.html (cabecera) y las páginas
├── static/                # CSS compilado, JS, fuentes, iconos, pictogramas, sw.js
├── tests/                 # python -m unittest discover -s tests
├── tools/                 # Cuentas, iconos, pictogramas, evaluación del reconocimiento de voz
├── deploy/                # Caddyfile y arranque para la red de la clínica
└── data/                  # Base de datos SQLite (datos de pacientes: fuera de git)
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

## 🛠️ Desarrollo

### Estilos (Tailwind CSS compilado)

Las plantillas extienden `templates/base.html`, y la cabecera común es la macro
`site_header` de `templates/partials/_ui.html`. El CSS de Tailwind **se compila**
(ya no se usa el CDN): la configuración está en `tailwind.config.js` y el resultado,
`static/css/app.css`, se incluye en el repositorio, así que para ejecutar la app no
hace falta Node.

Si cambias clases de Tailwind en las plantillas o en `static/js/`, regenera el CSS
(requiere Node.js):

```bash
npm install
npm run build:css     # o: npm run watch:css  mientras desarrollas
```

Los archivos estáticos se enlazan con `{{ asset('ruta') }}`, que añade un hash del
contenido (`?v=...`): el navegador los guarda en caché un año y la URL cambia sola
cuando el archivo cambia.

### Comunicador sin conexión (PWA)

Al abrir cualquier página, el service worker (`static/sw.js`, servido en `/sw.js`) guarda
el comunicador: página, estilos, fuentes, iconos, configuración y todas las imágenes de
pictogramas. Si se cae la red o el servidor, el comunicador sigue funcionando:

- las frases ya dichas suenan con la voz guardada;
- las nuevas usan la voz del propio dispositivo (`speechSynthesis`).

La app se puede instalar en la pantalla de inicio (`static/manifest.webmanifest`).
Si cambias la lógica de caché, sube la versión `CACHE` en `static/sw.js`.

> Los navegadores solo activan el service worker (y el micrófono) con **HTTPS** o en
> `localhost`.

### Iconos (Font Awesome reducido)

La app sirve un **subconjunto local** de Font Awesome Free 6.5 (estilo sólido) con solo
los iconos que usa: `static/vendor/fontawesome/`. Si añades un icono nuevo (en una
plantilla, en el JS o en un pictograma de la base de datos), regenera el subconjunto;
el test `IconsTest` avisa si falta alguno:

```bash
pip install -r requirements-dev.txt
npm pack @fortawesome/fontawesome-free@6.5.0
tar -xzf fortawesome-fontawesome-free-6.5.0.tgz
python tools/build_icons.py --fa-dir package --db data/rehab_voice.db
```

### Pictogramas (licencia libre)

Las ilustraciones son las mismas que usa la app móvil (`static/pictograms/libre/`): Mulberry
Symbols y OpenMoji (CC BY-SA 4.0) y algunos dibujos propios. **Se pueden usar con fines
comerciales** manteniendo la atribución, que aparece al pie del comunicador, la práctica y los
juegos; qué símbolo es cada archivo está en `static/pictograms/libre/ATRIBUCION.md`. Antes eran
de ARASAAC, cuya licencia (CC BY-NC-SA) no permite el uso comercial.

Cada pictograma se asigna en `PICTOGRAM_IMAGES` (`database.py`); al arrancar, la app actualiza
las bases de datos existentes. Las imágenes se generan en el proyecto de la app móvil
(`npm run pictograms`, a partir de `scripts/pictograms/map.json`): para cambiar o añadir una,
genérala allí y copia el `.webp` a `static/pictograms/libre/`.

Las **palabras de práctica** también tienen su pictograma (`word_images.py`, clave
`categoría/palabra`). Si la palabra es el mismo concepto que un pictograma del comunicador, usa
la misma imagen; las palabras abstractas («puedo hacerlo», «desafío») no llevan imagen. Una
palabra nueva con el mismo texto que una del mapa recibe su imagen automáticamente.

### Muestras de voz reales (evaluar el reconocimiento)

Los audios de `tools/make_eval_set.py` son voces sintéticas: para saber cuánto acierta la app con
pacientes reales hacen falta grabaciones reales. Con `EVAL_RECORDING=1`, la página **/samples**
(enlace en *Pacientes*) permite al terapeuta grabar al paciente diciendo una palabra y marcar si
la pronunció bien (y, si no, qué dijo). Pide confirmar el consentimiento y **no guarda quién es el
paciente**. Las muestras van a `eval_audio/clinica/` (fuera de git) y se evalúan con:

```bash
python tools/eval_speech.py eval_audio/clinica
```

Unas decenas de muestras por tipo de error ya dan una idea fiable de la sensibilidad y de los
falsos aprobados.

### Ajustar los umbrales de acierto

`tools/calibrate_thresholds.py` propone, por nivel, cuánto subir o bajar el umbral de acierto
(`base_thresholds` en `voice_processor.py`). Usa datos reales etiquetados:

- las valoraciones del terapeuta en la práctica («Bien dicho» / «No era correcto»), que se
  guardan con lo que oyó el reconocedor (no hace falta audio), y
- los resultados de `eval_speech.py` sobre las muestras de /samples.

```bash
python tools/calibrate_thresholds.py
python tools/calibrate_thresholds.py --results eval_audio/clinica/resultados.csv
```

Necesita al menos 20 intentos etiquetados por nivel, con bien y mal dichos. No cambia nada por
sí sola: revisa la recomendación antes de tocar los umbrales. Para un paciente concreto, mejor
usar «Ajustes del paciente → Exigencia al puntuar».

### Tests

```bash
python -m unittest discover -s tests -v
```

Comprobación de tipos: `npx pyright` (Python) y `npm run check:js` (JavaScript:
`nav.js`, `sw-register.js` y el service worker).

No cargan Whisper ni generan audio, y usan una base de datos temporal.

### Variables de entorno

| Variable | Por defecto | Uso |
|---|---|---|
| `DATABASE_URL` | SQLite en `data/` | Base de datos (SQLite o PostgreSQL) |
| `STT_ENGINE` | `faster_whisper` | Motor de voz: `faster_whisper`, `whisper`, `vosk` o `none` (sin modelo, para desarrollo y tests) |
| `WHISPER_MODEL` | `base` | Modelo de faster-whisper. `small` aprueba menos errores de pronunciación pero es ~3 veces más lento (ver `tools/eval_speech.py`) |
| `SPEECH_CONCURRENCY` | `1` | Transcripciones simultáneas (Whisper usa la CPU) |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Dirección de escucha de `python app.py`. En la clínica se queda en `127.0.0.1` y Caddy publica la app |
| `COOKIE_SECURE` | `0` | `1` cuando se sirve con HTTPS: la cookie de sesión solo viaja cifrada (lo pone `deploy/start_clinic.bat`) |
| `RELOAD` | `0` | `1` para recargar al guardar cambios (desarrollo) |
| `ALLOWED_ORIGINS` | vacío | Orígenes CORS permitidos, separados por comas (solo si otra web llama a la API) |
| `TTS_ONLINE` | `0` | `1` permite las voces **en línea** (Edge de Microsoft, gTTS de Google) si Piper falla. Desactivadas porque enviarían fuera las frases del paciente; sin voz del servidor, las páginas usan la del dispositivo |
| `EVAL_RECORDING` | `0` | `1` activa la página /samples para grabar muestras de voz etiquetadas |
| `EVAL_AUDIO_DIR` | `eval_audio/clinica` | Dónde se guardan esas muestras |

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

La voz principal es **Piper** (local, sin conexión). Si no está disponible, las páginas usan la
voz del propio dispositivo. Las voces de Edge TTS solo se usan con `TTS_ONLINE=1`
(ver *Variables de entorno*); en ese caso, las disponibles son:

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
- `GET /api/games/summary/{patient_id}` - Partidas de cada juego (última nota y dificultad, mejor nota)

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
- Verifica que Piper esté instalado (carpetas `piper/` y `voices/`): es la voz del servidor
- Sin voz del servidor, la app usa la del dispositivo: comprueba que el sistema tenga una voz en español

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
| **Piper** | Voz local (Text-to-Speech sin conexión) |
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
- Piper (Rhasspy) por la voz local sin conexión
- La comunidad de FastAPI
- Todos los profesionales de fonoaudiología que inspiraron este proyecto

---

*¡Que cada palabra sea un paso hacia la recuperación! 🎤✨*

---

## Créditos y licencias

- **Pictogramas:** [Mulberry Symbols](https://mulberrysymbols.org) (© Steve Lee) y
  [OpenMoji](https://openmoji.org), ambos con licencia
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.es), y algunos dibujos propios.
  Permiten el uso comercial manteniendo la atribución y compartiendo las imágenes (no el código)
  con la misma licencia. Detalles en `static/pictograms/libre/ATRIBUCION.md`.
- **Iconos:** Font Awesome Free 6.5 (iconos CC BY 4.0, fuente SIL OFL 1.1, código MIT).
- **Fuente:** Poppins (SIL Open Font License 1.1).
