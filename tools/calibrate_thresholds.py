"""Propone el ajuste de los umbrales de acierto por nivel a partir de datos reales etiquetados.

Fuentes (se pueden combinar):
  1. Valoraciones del terapeuta en la práctica («Bien dicho» / «No era correcto»): se leen de la
     base de datos junto con lo que oyó el reconocedor. No necesitan audio.
  2. Resultados de tools/eval_speech.py sobre las muestras de /samples (--results CSV, columnas
     target, transcription, label, config), p. ej. eval_audio/clinica/resultados.csv.

Para cada nivel vuelve a puntuar cada transcripción con la puntuación actual de la app, prueba
desplazamientos del umbral (-15 a +15) y muestra la sensibilidad (correctas aprobadas) y los
falsos aprobados (incorrectas aprobadas). Recomienda el desplazamiento con mejor equilibrio que
no aumente los falsos aprobados del umbral actual en más de 5 puntos. No cambia nada: los
umbrales están en VoiceProcessor._get_tolerance_threshold (base_thresholds).

Uso:
  python tools/calibrate_thresholds.py                       # base de datos de la app
  python tools/calibrate_thresholds.py --results eval_audio/clinica/resultados.csv --config actual
  python tools/calibrate_thresholds.py --min 10              # mínimo de intentos por nivel
"""
import argparse
import contextlib
import csv
import io
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STT_ENGINE", "none")  # solo se puntúa texto: no hace falta cargar Whisper

with contextlib.redirect_stdout(io.StringIO()):
    from database import GAME_PREFIX, Database, Progress, Word  # noqa: E402
    from voice_processor import VoiceProcessor  # noqa: E402

OFFSETS = range(-15, 16)


def from_database():
    db = Database()
    session = db.SessionLocal()
    try:
        rows = (session.query(Progress.transcription, Progress.therapist_correct, Progress.feedback, Word.word, Word.level)
                .join(Word, Progress.word_id == Word.id)
                .filter(Progress.therapist_correct.is_not(None), ~Progress.word_id.like(GAME_PREFIX + "%"))
                .all())
        out = []
        for t, c, fb, w, lvl in rows:
            # Nivel elegido en la práctica y exigencia del paciente con los que se puntuó el intento
            # (se guardan en feedback); los intentos antiguos usan el nivel de la palabra
            try:
                meta = json.loads(fb or "{}")
            except ValueError:
                meta = {}
            level = meta.get("practice_level") or lvl or 1
            out.append({"target": w, "heard": t or "", "correct": bool(c), "level": int(level),
                        "tolerance": float(meta.get("tolerance") or 0), "source": "terapeuta"})
        return out
    finally:
        session.close()


def from_results(path: Path, config: str):
    out = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if config and r.get("config") and r["config"] != config:
                continue
            if r.get("label") not in ("correct", "incorrect"):
                continue
            out.append({"target": r["target"], "heard": r.get("transcription", ""),
                        "correct": r["label"] == "correct", "level": int(r.get("level") or 1), "source": "muestras"})
    return out


def rates(items, offset):
    ok = [i for i in items if i["correct"]]
    bad = [i for i in items if not i["correct"]]
    sens = sum(i["score"] >= i["threshold"] + offset for i in ok) / len(ok) * 100 if ok else None
    fa = sum(i["score"] >= i["threshold"] + offset for i in bad) / len(bad) * 100 if bad else None
    return sens, fa


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, help="CSV de tools/eval_speech.py con las muestras de /samples")
    parser.add_argument("--config", default="actual", help="configuración del CSV de resultados (por defecto: actual)")
    parser.add_argument("--no-db", action="store_true", help="no leer las valoraciones del terapeuta")
    parser.add_argument("--min", type=int, default=20, help="mínimo de intentos etiquetados por nivel")
    args = parser.parse_args()

    items = [] if args.no_db else from_database()
    if args.results:
        items += from_results(args.results, args.config)
    if not items:
        print("No hay datos etiquetados todavía.\n"
              "- Valora intentos en la práctica con «Bien dicho» / «No era correcto», o\n"
              "- graba muestras en /samples y ejecuta tools/eval_speech.py eval_audio/clinica,\n"
              "y vuelve a lanzar esta herramienta.")
        return 1

    with contextlib.redirect_stdout(io.StringIO()):
        vp = VoiceProcessor()
        for i in items:
            r = vp._score_transcription(i["heard"], i["target"], i["level"], i.get("tolerance", 0))
            i["score"], i["threshold"] = r["scores"]["final"], r["scores"]["threshold"]

    by_level = defaultdict(list)
    for i in items:
        by_level[i["level"]].append(i)
    sources = defaultdict(int)
    for i in items:
        sources[i["source"]] += 1
    print(f"Intentos etiquetados: {len(items)} ({', '.join(f'{k}: {v}' for k, v in sources.items())})\n")

    for level in sorted(by_level):
        data = by_level[level]
        n_ok = sum(i["correct"] for i in data)
        print(f"Nivel {level}: {len(data)} intentos ({n_ok} bien dichos, {len(data) - n_ok} mal dichos)")
        if len(data) < args.min or n_ok == 0 or n_ok == len(data):
            print(f"   pocos datos para recomendar (hacen falta {args.min}, con bien y mal dichos)\n")
            continue
        sens0, fa0 = rates(data, 0)
        best, best_bal = 0, None
        for off in OFFSETS:
            sens, fa = rates(data, off)
            if fa > fa0 + 5:
                continue
            bal = (sens + (100 - fa)) / 2
            if best_bal is None or bal > best_bal + 0.01 or (abs(bal - best_bal) <= 0.01 and abs(off) < abs(best)):
                best, best_bal = off, bal
        for off in sorted({-10, -5, 0, 5, 10, best}):
            sens, fa = rates(data, off)
            mark = "  <- actual" if off == 0 else ("  <- recomendado" if off == best else "")
            print(f"   umbral {off:+3d}: sensibilidad {sens:5.1f}%  falsos aprobados {fa:5.1f}%{mark}")
        if best == 0:
            print("   El umbral actual ya es el mejor equilibrio.\n")
        else:
            print(f"   Recomendación: {'bajar' if best < 0 else 'subir'} el umbral del nivel {level} "
                  f"{abs(best)} puntos (base_thresholds en voice_processor.py).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
