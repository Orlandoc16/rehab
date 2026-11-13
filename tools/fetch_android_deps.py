"""Descarga lo que necesita la app Android sin servidor y no se guarda en git (pesa mucho):

- whisper.cpp (código fuente, se compila con el NDK): reconocimiento de voz en la tablet.
- Modelo de Whisper (ggml): el mismo «base» que usa el servidor.
- sherpa-onnx (bibliotecas Android ya compiladas + su API Kotlin): ejecuta la voz Piper.
- Voz Piper es_MX-claude-high (la misma del servidor), convertida para sherpa-onnx.

Todo queda en android/third_party/ (ignorado por git). Versiones fijadas aquí.
Uso:  python tools/fetch_android_deps.py
"""
import hashlib
import io
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "android" / "third_party"

WHISPER_CPP = "v1.9.5"
WHISPER_MODEL = "ggml-base-q8_0.bin"   # misma precisión que base f16 en eval_audio y más rápido
SHERPA = "v1.13.8"   # la 2.x quitó espeak-ng: las voces Piper necesitan la 1.x
PIPER_VOICE = "vits-piper-es_MX-claude-high"   # fp32: la fp16 no carga en el onnxruntime de sherpa 1.x
ABIS = ("arm64-v8a", "x86_64")          # tablets + emulador

URLS = {
    "whisper.cpp": f"https://github.com/ggml-org/whisper.cpp/archive/refs/tags/{WHISPER_CPP}.zip",
    "model": f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{WHISPER_MODEL}",
    "sherpa": f"https://github.com/k2-fsa/sherpa-onnx/releases/download/{SHERPA}/sherpa-onnx-{SHERPA}-android.tar.bz2",
    "sherpa_tts_kt": f"https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/{SHERPA}/sherpa-onnx/kotlin-api/Tts.kt",
    "voice": f"https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/{PIPER_VOICE}.tar.bz2",
}


def download(url: str) -> bytes:
    print(f"  descargando {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "rehab-voice-build"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = r.read()
    print(f"    {len(data) / 1e6:.1f} MB  sha256 {hashlib.sha256(data).hexdigest()[:16]}")
    return data


def safe_extract_tar(data: bytes, mode: str, target: Path, members_filter=None) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode=mode) as tar:
        tar.extractall(target, members=[m for m in tar.getmembers() if not members_filter or members_filter(m)],
                       filter="data")


# Lo que necesita espeak-ng para el español (el resto de idiomas ocupa ~15 MB y no se usa)
ESPEAK_KEEP = {"phondata", "phondata-manifest", "phonindex", "phontab", "intonations", "es_dict"}


def stage_assets() -> None:
    """third_party/app_assets/ -> se añade a los assets de la APK (android/app/build.gradle):
    models/<modelo whisper> y tts/<voz> (con espeak-ng-data solo en español)."""
    out = DEST / "app_assets"
    shutil.rmtree(out, ignore_errors=True)
    (out / "models").mkdir(parents=True)
    shutil.copy2(DEST / "models" / WHISPER_MODEL, out / "models" / WHISPER_MODEL)
    src = DEST / "voice" / PIPER_VOICE
    dst = out / "tts" / "voice"
    dst.mkdir(parents=True)
    for f in src.iterdir():
        if f.is_file() and f.suffix in (".onnx", ".txt", ".json"):
            shutil.copy2(f, dst / ("model.onnx" if f.suffix == ".onnx" else f.name))
    espeak_src, espeak_dst = src / "espeak-ng-data", dst / "espeak-ng-data"
    espeak_dst.mkdir()
    for f in espeak_src.iterdir():
        if f.name in ESPEAK_KEEP:
            shutil.copy2(f, espeak_dst / f.name)
    # lang/ y voices/: solo las variantes del español
    for sub in ("lang", "voices"):
        for f in (espeak_src / sub).rglob("*"):
            rel = f.relative_to(espeak_src)
            if f.is_file() and (f.name.startswith("es") or sub == "voices"):
                (espeak_dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, espeak_dst / rel)


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)

    # 1. whisper.cpp (código fuente)
    wdir = DEST / "whisper.cpp"
    if not (wdir / "CMakeLists.txt").exists():
        print("whisper.cpp", WHISPER_CPP)
        data = download(URLS["whisper.cpp"])
        tmp = DEST / "_whisper_tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if ".." in Path(info.filename).parts:
                    raise ValueError(f"ruta sospechosa en el zip: {info.filename}")
            z.extractall(tmp)
        shutil.rmtree(wdir, ignore_errors=True)
        next(tmp.iterdir()).rename(wdir)
        shutil.rmtree(tmp, ignore_errors=True)

    # 2. modelo de Whisper
    mdir = DEST / "models"
    mdir.mkdir(exist_ok=True)
    if not (mdir / WHISPER_MODEL).exists():
        print("modelo", WHISPER_MODEL)
        (mdir / WHISPER_MODEL).write_bytes(download(URLS["model"]))

    # 3. sherpa-onnx: bibliotecas nativas de las ABI que se usan + API Kotlin
    sdir = DEST / "sherpa-onnx"
    if not (sdir / "jniLibs" / ABIS[0]).exists():
        print("sherpa-onnx", SHERPA)
        data = download(URLS["sherpa"])
        tmp = DEST / "_sherpa_tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        safe_extract_tar(data, "r:bz2", tmp, lambda m: any(f"/{abi}/" in f"/{m.name}/" for abi in ABIS))
        shutil.rmtree(sdir, ignore_errors=True)
        for abi in ABIS:
            found = next(p for p in tmp.rglob(abi) if p.is_dir())
            shutil.copytree(found, sdir / "jniLibs" / abi)
        shutil.rmtree(tmp, ignore_errors=True)
    kt = sdir / "kotlin" / "com" / "k2fsa" / "sherpa" / "onnx" / "Tts.kt"
    if not kt.exists():
        kt.parent.mkdir(parents=True, exist_ok=True)
        kt.write_bytes(download(URLS["sherpa_tts_kt"]))

    # 4. voz Piper para sherpa-onnx
    vdir = DEST / "voice"
    if not (vdir / PIPER_VOICE).exists():
        print("voz", PIPER_VOICE)
        data = download(URLS["voice"])
        shutil.rmtree(vdir, ignore_errors=True)
        safe_extract_tar(data, "r:bz2", vdir)

    stage_assets()
    for p in sorted(DEST.iterdir()):
        size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6
        print(f"{p.name:15s} {size:8.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
