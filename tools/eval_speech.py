"""Evalúa la precisión del análisis de voz con un set de audios etiquetados.

Para cada configuración del reconocimiento mide, usando la puntuación real de la app
(VoiceProcessor.analyze):
  - Sensibilidad:      % de pronunciaciones correctas que la app da por buenas
  - Falsos aprobados:  % de pronunciaciones incorrectas que la app da por buenas
  - Sesgo:             % de incorrectas en las que Whisper "oye" la palabra objetivo
  - Literal:           % de audios cuya transcripción coincide con lo que realmente se dijo
  - Latencia mediana por intento

Manifiesto CSV (como el que genera tools/make_eval_set.py; sirve igual para grabaciones reales):
  file,target,spoken,label,kind      label = correct | incorrect

Uso:
  python tools/eval_speech.py eval_audio/sintetico [--configs actual,sin_prompt] [--level 1]
  python tools/eval_speech.py eval_audio/clinica      # muestras reales grabadas en /samples
"""
import argparse
import contextlib
import csv
import io
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from voice_processor import VoiceProcessor  # noqa: E402

NEUTRAL_PROMPT = "Transcripción literal en español."


def make_configs(vp: VoiceProcessor):
    original = vp.transcribe_with_retry

    def with_prompt(prompt_fn):
        def run(audio_path, language="es", initial_prompt=None):
            return original(audio_path, language, initial_prompt=prompt_fn(initial_prompt))
        return run

    def single_pass(beam):
        def run(audio_path, language="es", initial_prompt=None):
            segments, _ = vp.model.transcribe(audio_path, language=language, beam_size=beam, best_of=beam,
                                              vad_filter=True, condition_on_previous_text=False)
            return " ".join(s.text for s in segments).strip()
        return run

    return {
        "actual": original,                                    # pista = palabra objetivo (comportamiento de hoy)
        "sin_prompt": with_prompt(lambda _p: None),            # sin pista
        "prompt_neutral": with_prompt(lambda _p: NEUTRAL_PROMPT),
        "sin_prompt_beam1": single_pass(1),                    # una sola pasada, más rápida
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--configs", default="actual,sin_prompt,prompt_neutral,sin_prompt_beam1")
    parser.add_argument("--level", type=int, default=None,
                        help="nivel de tolerancia; por defecto, el de cada audio (columna level) o 1")
    parser.add_argument("--model", default=None, help="modelo de faster-whisper a probar (tiny, base, small...)")
    parser.add_argument("--out", type=Path, help="CSV con el resultado por audio (por defecto, junto al set)")
    args = parser.parse_args()

    rows = list(csv.DictReader(open(args.dataset / "manifest.csv", encoding="utf-8")))
    with contextlib.redirect_stdout(io.StringIO()):
        vp = VoiceProcessor()
    if args.model:
        from faster_whisper import WhisperModel
        vp.model = WhisperModel(args.model, device="cpu", compute_type="int8")
    configs = make_configs(vp)
    chosen = [c.strip() for c in args.configs.split(",")]
    norm = vp._normalize_text

    detail = []
    summary = {}
    for name in chosen:
        vp.transcribe_with_retry = configs[name]
        stats = defaultdict(list)
        for row in rows:
            path = str(args.dataset / row["file"])
            t = time.perf_counter()
            with contextlib.redirect_stdout(io.StringIO()):
                level = args.level or int(row.get("level") or 1)
                result = vp.analyze(path, row["target"], level=level)
            elapsed = time.perf_counter() - t
            heard = norm(result.get("transcription") or "")
            ok = bool(result.get("is_correct"))
            stats["latency"].append(elapsed)
            stats["literal"].append(heard == norm(row["spoken"]))
            if row["label"] == "correct":
                stats["sens"].append(ok)
            else:
                stats["false_accept"].append(ok)
                stats["heard_target"].append(heard == norm(row["target"]))
                stats[f"fa_{row['kind']}"].append(ok)
            detail.append({"config": name, **row, "transcription": result.get("transcription"),
                           "score": result.get("scores", {}).get("final"), "is_correct": ok, "seconds": round(elapsed, 2)})
            print(f"  [{name}] {row['file']:45s} dijo={row['spoken']!r:18s} oyó={result.get('transcription')!r:22s} "
                  f"score={result.get('scores', {}).get('final')} {'APRUEBA' if ok else 'suspende'}", flush=True)
        summary[name] = stats

    pct = lambda xs: f"{100 * sum(xs) / len(xs):5.1f}%" if xs else "  n/a"
    print()
    print(f"Modelo {args.model or 'por defecto'} | Nivel {args.level or 'de cada audio'} | {len(rows)} audios ({sum(r['label'] == 'correct' for r in rows)} correctos)")
    print(f"{'configuración':18s} {'sensibilidad':>12s} {'falsos aprob.':>13s} {'sesgo':>7s} {'literal':>8s} {'latencia':>9s}")
    for name, s in summary.items():
        print(f"{name:18s} {pct(s['sens']):>12s} {pct(s['false_accept']):>13s} {pct(s['heard_target']):>7s} "
              f"{pct(s['literal']):>8s} {statistics.median(s['latency']):8.2f}s")
    kinds = sorted({k[3:] for s in summary.values() for k in s if k.startswith("fa_")})
    print("\nFalsos aprobados por tipo de error:")
    print(f"{'tipo':20s} " + " ".join(f"{n:>17s}" for n in summary))
    for kind in kinds:
        print(f"{kind:20s} " + " ".join(f"{pct(summary[n]['fa_' + kind]):>17s}" for n in summary))

    out = args.out or (args.dataset / "resultados.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(detail[0]))
        writer.writeheader()
        writer.writerows(detail)
    print(f"\nDetalle por audio: {out}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
