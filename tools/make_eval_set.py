"""Genera un set SINTÉTICO de audios para evaluar el reconocimiento y la puntuación.

Cada palabra objetivo se graba bien pronunciada y con errores típicos en rehabilitación
(sustitución u omisión de fonemas, simplificación de grupos consonánticos, otra palabra).
Las voces sintéticas son mucho más claras que las de un paciente: los resultados sirven para
comparar configuraciones y detectar sesgos, no como medida clínica definitiva. Para eso,
añade grabaciones reales al mismo manifiesto (ver tools/eval_speech.py).

Usa las voces locales de Piper (voices/piper/*.onnx) y ffmpeg. Uso:
  python tools/make_eval_set.py --out eval_audio/sintetico
"""
import argparse
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPER = ROOT / "piper" / ("piper.exe" if sys.platform == "win32" else "piper")
VOICES = sorted((ROOT / "voices" / "piper").glob("*.onnx"))

# (objetivo, lo que se dice, etiqueta, tipo de error)
CASES = [
    ("agua", "agua", "correct", "correcta"),
    ("agua", "aua", "incorrect", "omision"),
    ("agua", "leche", "incorrect", "otra_palabra"),
    ("gato", "gato", "correct", "correcta"),
    ("gato", "pato", "incorrect", "sustitucion"),
    ("gato", "ato", "incorrect", "omision"),
    ("perro", "perro", "correct", "correcta"),
    ("perro", "pelo", "incorrect", "sustitucion"),
    ("perro", "pero", "incorrect", "rotica_simple"),
    ("casa", "casa", "correct", "correcta"),
    ("casa", "tasa", "incorrect", "sustitucion"),
    ("casa", "cama", "incorrect", "otra_palabra"),
    ("mesa", "mesa", "correct", "correcta"),
    ("mesa", "misa", "incorrect", "sustitucion"),
    ("mesa", "meta", "incorrect", "sustitucion"),
    ("plátano", "plátano", "correct", "correcta"),
    ("plátano", "pátano", "incorrect", "grupo_consonantico"),
    ("plátano", "plátamo", "incorrect", "sustitucion"),
    ("tren", "tren", "correct", "correcta"),
    ("tren", "ten", "incorrect", "grupo_consonantico"),
    ("flor", "flor", "correct", "correcta"),
    ("flor", "for", "incorrect", "grupo_consonantico"),
    ("mariposa", "mariposa", "correct", "correcta"),
    ("mariposa", "maripa", "incorrect", "omision"),
    ("mariposa", "mapiposa", "incorrect", "sustitucion"),
    ("naranja", "naranja", "correct", "correcta"),
    ("naranja", "narana", "incorrect", "omision"),
    ("teléfono", "teléfono", "correct", "correcta"),
    ("teléfono", "telénofo", "incorrect", "metatesis"),
    ("libro", "libro", "correct", "correcta"),
    ("libro", "libo", "incorrect", "grupo_consonantico"),
    ("manzana", "manzana", "correct", "correcta"),
    ("manzana", "mazana", "incorrect", "omision"),
    ("gracias", "gracias", "correct", "correcta"),
    ("gracias", "gacias", "incorrect", "grupo_consonantico"),
    ("buenos días", "buenos días", "correct", "correcta"),
    ("buenos días", "buenas noches", "incorrect", "otra_palabra"),
    ("quiero agua", "quiero agua", "correct", "correcta"),
    ("quiero agua", "quiero leche", "incorrect", "otra_palabra"),
]


def synth(text: str, voice: Path, wav: Path) -> None:
    subprocess.run([str(PIPER), "--model", str(voice), "--output_file", str(wav)],
                   input=text.encode("utf-8"), check=True, capture_output=True)


def to_webm(mp3: Path, webm: Path) -> None:
    """Mismo formato que graba el navegador (MediaRecorder): WebM/Opus mono 48 kHz."""
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-af", "adelay=300,apad=pad_dur=0.4",
                    "-ac", "1", "-ar", "48000", "-c:a", "libopus", "-b:a", "32k", str(webm)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("eval_audio/sintetico"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if not PIPER.exists() or not VOICES:
        print("Faltan Piper (piper/) o voces (voices/piper/*.onnx)")
        return 1
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, (target, spoken, label, kind) in enumerate(CASES):
            for voice in VOICES:
                name = f"{i:02d}_{voice.stem.split('-')[0]}_{label}_{kind}.webm"
                wav = Path(tmp) / "a.wav"
                synth(spoken, voice, wav)
                to_webm(wav, args.out / name)
                rows.append({"file": name, "target": target, "spoken": spoken, "label": label, "kind": kind, "voice": voice.stem})
    with open(args.out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} audios en {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
