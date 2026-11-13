"""Prepara las páginas de la app Android sin servidor (android/app/src/main/assets/www).

- Renderiza las plantillas en «app_mode»: las rutas /api/... las responde el servidor local en
  JavaScript (static/js/app/local-api.js) y la cabecera no depende de la sesión del servidor.
- Copia static/ (sin lo que solo sirve en el servidor: service worker y grabador de muestras).
- Exporta el contenido de la base de datos (categorías, palabras, comunicador) a
  static/app/content.json.

Se ejecuta antes de compilar la app (android/app/build.gradle lo hace solo en cada compilación).
Uso:  python tools/build_android_web.py
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

OUT = ROOT / "android" / "app" / "src" / "main" / "assets" / "www"

# ruta -> (plantilla, título); el archivo de salida es <ruta>.html ("/" -> index.html)
PAGES = {
    "index": ("index.html", "Rehab Voice"),
    "practice": ("practice.html", "Práctica - Rehab Voice"),
    "games": ("games.html", "Juegos - Rehab Voice"),
    "progress": ("progress.html", "Mi Progreso - Rehab Voice"),
    "communicator": ("communicator.html", "Comunicador - Rehab Voice"),
    "patients": ("app_patients.html", "Pacientes - Rehab Voice"),
}
# Solo para el servidor
SKIP_STATIC = {"sw.js", "jsconfig.sw.json", "manifest.webmanifest", "js/sw-register.js", "js/samples.js"}


def build() -> None:
    from export_app_content import export_content
    from database import Database
    from rehab.web import templates

    if OUT.exists():
        shutil.rmtree(OUT)
    static_out = OUT / "static"
    static_dir = ROOT / "static"
    for src in static_dir.rglob("*"):
        rel = src.relative_to(static_dir).as_posix()
        if src.is_dir() or rel in SKIP_STATIC:
            continue
        dst = static_out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    env = templates.env
    for name, (template, title) in PAGES.items():
        html = env.get_template(template).render(title=title, session=None, app_mode=True)
        (OUT / f"{name}.html").write_text(html, encoding="utf-8")

    db = Database()
    db.initialize()
    content = export_content(db.engine)
    (static_out / "app").mkdir(parents=True, exist_ok=True)
    (static_out / "app" / "content.json").write_text(
        json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    files = sum(1 for p in OUT.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1e6
    print(f"{OUT}: {files} archivos, {size:.1f} MB | {len(content['words'])} palabras, "
          f"{len(content['aac_pictograms'])} pictogramas")


if __name__ == "__main__":
    build()
