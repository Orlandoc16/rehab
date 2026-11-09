@echo off
REM Arranca Rehab Voice para la red de la clinica, detras de Caddy (HTTPS).
REM Caddy se arranca aparte:  caddy run --config deploy\Caddyfile
title Rehab Voice (clinica)
cd /d "%~dp0.."
call venv\Scripts\activate.bat
REM Solo escucha en este equipo: las tablets entran por Caddy (https://IP-del-PC)
set HOST=127.0.0.1
set PORT=8000
REM La cookie de sesion solo viaja por HTTPS
set COOKIE_SECURE=1
python app.py
pause
