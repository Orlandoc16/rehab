"""Muestras de voz etiquetadas por el terapeuta, para medir la precisión del reconocimiento con
pacientes reales (tools/eval_speech.py).

Desactivado por defecto (EVAL_RECORDING=1 para activarlo): guarda la voz de pacientes. Cada
muestra exige confirmar el consentimiento y NO guarda quién es el paciente. Los audios y el
manifiesto van a EVAL_AUDIO_DIR (por defecto eval_audio/clinica/, fuera de git):

    manifest.csv   file,target,spoken,label,kind,level   (el formato de tools/eval_speech.py)
    AAAAMMDD/<id>.webm
"""
import csv
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from .. import settings
from ..web import page

router = APIRouter()

FIELDS = ["file", "target", "spoken", "label", "kind", "level"]
MAX_BYTES = 5 * 1024 * 1024   # ~5 MB: de sobra para unos segundos de voz
_manifest_lock = threading.Lock()


def _require_enabled() -> None:
    if not settings.EVAL_RECORDING:
        raise HTTPException(status_code=403, detail="La grabación de muestras está desactivada (EVAL_RECORDING=1).")


def _append_sample(audio: bytes, row: Dict[str, str]) -> Dict[str, int]:
    """Guarda el audio y añade su fila al manifiesto. Devuelve el recuento actual."""
    base = Path(settings.EVAL_AUDIO_DIR)
    day = datetime.now().strftime("%Y%m%d")
    (base / day).mkdir(parents=True, exist_ok=True)
    rel = f"{day}/{uuid.uuid4().hex[:12]}.webm"
    (base / rel).write_bytes(audio)
    manifest = base / "manifest.csv"
    with _manifest_lock:
        new = not manifest.exists()
        with open(manifest, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                writer.writeheader()
            writer.writerow({**row, "file": rel})
    return _count()


def _count() -> Dict[str, int]:
    manifest = Path(settings.EVAL_AUDIO_DIR) / "manifest.csv"
    counts = {"total": 0, "correct": 0, "incorrect": 0}
    if manifest.exists():
        with open(manifest, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                counts["total"] += 1
                if row.get("label") in counts:
                    counts[row["label"]] += 1
    return counts


@router.get("/samples", response_class=HTMLResponse)
async def samples_page(request: Request):
    """Página para grabar muestras de voz etiquetadas."""
    return page(request, "samples.html", "Muestras de voz - Rehab Voice", enabled=settings.EVAL_RECORDING)


@router.get("/api/samples/summary")
async def samples_summary():
    _require_enabled()
    return await run_in_threadpool(_count)


@router.post("/api/samples")
async def save_sample(
    audio_file: UploadFile = File(...),
    target: str = Form(...),
    label: str = Form(...),
    spoken: str = Form(""),
    level: int = Form(1),
    consent: str = Form(""),
):
    """Guarda una muestra: el audio, la palabra pedida y si el terapeuta la juzga correcta."""
    _require_enabled()
    if consent != "1":
        raise HTTPException(status_code=400, detail="Falta confirmar el consentimiento del paciente.")
    target = target.strip()
    spoken = spoken.strip()
    if label not in ("correct", "incorrect"):
        raise HTTPException(status_code=422, detail="label debe ser 'correct' o 'incorrect'.")
    if not target or len(target) > 200 or len(spoken) > 200:
        raise HTTPException(status_code=422, detail="Palabra vacía o demasiado larga.")
    audio = await audio_file.read(MAX_BYTES + 1)
    if not audio:
        raise HTTPException(status_code=422, detail="El audio está vacío.")
    if len(audio) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="El audio es demasiado largo.")
    row = {
        "target": target,
        # Si es correcta, lo dicho es la palabra; si no, lo que anotó el terapeuta (puede quedar vacío)
        "spoken": target if label == "correct" else spoken,
        "label": label,
        "kind": "real",
        "level": str(max(1, min(5, level))),
    }
    counts = await run_in_threadpool(_append_sample, audio, row)
    return {"saved": True, **counts}
