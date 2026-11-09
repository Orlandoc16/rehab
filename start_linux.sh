#!/bin/bash

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║   🎤 REHAB VOICE 2025                                        ║"
echo "║   Aplicación de Rehabilitación Vocal con IA                  ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Verificar si existe el entorno virtual
if [ ! -d "venv" ]; then
    echo "[*] Creando entorno virtual..."
    python3 -m venv venv
fi

# Activar entorno virtual
echo "[*] Activando entorno virtual..."
source venv/bin/activate

# Verificar si las dependencias están instaladas
if ! pip show fastapi > /dev/null 2>&1; then
    echo "[*] Instalando dependencias..."
    pip install -r requirements.txt
fi

echo ""
echo "[*] Iniciando servidor..."
echo "[*] Abre tu navegador en: http://localhost:8000"
echo "[*] Presiona Ctrl+C para detener el servidor"
echo ""

python app.py
