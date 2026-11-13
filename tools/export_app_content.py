"""Exporta el contenido de la base de datos (categorías, palabras y comunicador) para la app
Android sin servidor (static/js/app/local-api.js lo carga en la base del dispositivo).

Se exporta de la base de datos y no del código porque las clínicas tienen más contenido del que
siembra database.py (lo añadió un script antiguo).

Uso:  python tools/export_app_content.py salida.json      (usa DATABASE_URL o data/rehab_voice.db)
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

TABLES = {
    "categories": ["id", "name", "description", "icon", "color", "order_num"],
    "words": ["id", "word", "category_id", "level", "phonetic_hint", "image_url", "audio_url", "tips", "created_at"],
    "aac_categories": ["id", "label", "color", "icon", "order_num"],
    "aac_pictograms": ["id", "category_id", "label", "icon_src", "grammar", "default_phrase"],
}


def _value(v):
    """Fechas como las guarda SQLAlchemy en SQLite ('YYYY-MM-DD HH:MM:SS.ffffff')."""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S.%f")
    return v


def export_content(engine) -> dict:
    content = {}
    with engine.connect() as conn:
        for table, cols in TABLES.items():
            # Sin ORDER BY: el orden natural (rowid en SQLite) es el que ven las consultas sin orden
            # (p. ej. el desempate de la repetición espaciada); la app inserta en este mismo orden.
            rows = conn.execute(text(f"SELECT {', '.join(cols)} FROM {table}")).all()
            content[table] = [{c: _value(v) for c, v in zip(cols, row)} for row in rows]
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    content["version"] = digest[:16]
    return content


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    from database import Database
    db = Database()
    db.initialize()
    content = export_content(db.engine)
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{out}: {len(content['categories'])} categorías, {len(content['words'])} palabras, "
          f"{len(content['aac_pictograms'])} pictogramas (versión {content['version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
