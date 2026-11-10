@echo off
title Rehab Voice 2025
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                                                              ║
echo ║   🎤 REHAB VOICE 2025                                        ║
echo ║   Aplicacion de Rehabilitacion Vocal con IA                  ║
echo ║                                                              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Verificar si existe el entorno virtual
if not exist "venv" (
    echo [*] Creando entorno virtual...
    python -m venv venv
)

REM Activar entorno virtual
echo [*] Activando entorno virtual...
call venv\Scripts\activate.bat

REM Verificar si las dependencias están instaladas
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo [*] Instalando dependencias...
    pip install -r requirements.txt
)

echo.
echo [*] Iniciando servidor...
echo [*] Abre tu navegador en: http://localhost:8000
echo [*] Presiona Ctrl+C para detener el servidor
echo.

REM Pagina /samples: grabar muestras de voz (con consentimiento) para afinar el reconocimiento.
REM Ponlo a 0 cuando haya suficientes muestras.
set EVAL_RECORDING=1

python app.py

pause
