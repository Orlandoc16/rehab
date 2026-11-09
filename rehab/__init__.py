"""Capa web de Rehab Voice (FastAPI).

Estructura:
  settings.py   configuración leída de variables de entorno
  services.py   instancias compartidas: base de datos, motor de voz, motor de juegos
  web.py        plantillas, estáticos con caché, gzip
  security.py   sesión obligatoria, paciente activo, redirecciones seguras
  schemas.py    validación de los cuerpos JSON (Pydantic)
  routers/      rutas agrupadas por dominio
  main.py       crea la aplicación

La lógica de dominio sigue en los módulos de la raíz (database.py, voice_processor.py,
game_engine.py, auth.py).
"""
