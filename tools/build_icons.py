"""Genera un subconjunto de Font Awesome Free (estilo sólido) con solo los iconos que usa la app.

Resultado (en static/vendor/fontawesome/):
  css/fontawesome.subset.css         CSS original de Font Awesome sin las reglas de iconos no usados
  webfonts/fa-solid-900.<hash>.woff2 fuente reducida a esos iconos (nombre con hash: caché larga)
  LICENSE.txt                        licencia de Font Awesome Free

Los iconos se buscan en las plantillas, el JavaScript y el código Python (los pictogramas del
comunicador se guardan en la base de datos con nombres como "fa-apple-whole"). Con --db se
incluyen además los iconos de una base de datos SQLite existente.

Uso (requiere: pip install -r requirements-dev.txt):
  npm pack @fortawesome/fontawesome-free@6.5.0 && tar -xzf fortawesome-fontawesome-free-6.5.0.tgz
  python tools/build_icons.py --fa-dir package --db data/rehab_voice.db
"""
import argparse
import hashlib
import io
import re
import shutil
import sqlite3
import sys
from pathlib import Path

from fontTools import subset  # pyright: ignore[reportMissingImports]  (requirements-dev.txt)
from fontTools.ttLib import TTFont  # pyright: ignore[reportMissingImports]

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "vendor" / "fontawesome"
SOURCES = ["templates/**/*.html", "static/js/**/*.js", "*.py"]
ICON_NAME = re.compile(r"\bfa-[a-z0-9]+(?:-[a-z0-9]+)*\b")
ICON_RULE = re.compile(r"^\.(fa-[a-z0-9-]+)::?before$")
SOLID_FACE_URL = "../webfonts/fa-solid-900.woff2"


def names_in_code() -> set:
    found = set()
    for pattern in SOURCES:
        for path in ROOT.glob(pattern):
            if "vendor" in path.parts or "node_modules" in path.parts:
                continue
            found.update(ICON_NAME.findall(path.read_text(encoding="utf-8", errors="ignore")))
    return found


def names_in_db(db_path: Path) -> set:
    found = set()
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for table, column in (("aac_pictograms", "icon_src"), ("aac_categories", "icon"), ("categories", "icon")):
            try:
                for (value,) in con.execute(f"SELECT {column} FROM {table}"):
                    found.update(ICON_NAME.findall(value or ""))
            except sqlite3.OperationalError:
                pass
    finally:
        con.close()
    return found


def split_rules(css: str):
    """Divide el CSS minificado en reglas de primer nivel (selector, cuerpo) y at-rules."""
    i, n = 0, len(css)
    while i < n:
        start = css.find("{", i)
        if start == -1:
            break
        prelude = css[i:start]
        depth, j = 1, start + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        yield prelude.strip(), css[start + 1:j - 1]
        i = j


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fa-dir", required=True, type=Path, help="carpeta 'package' de @fortawesome/fontawesome-free")
    parser.add_argument("--db", type=Path, action="append", default=[], help="base de datos SQLite con más iconos (repetible)")
    args = parser.parse_args()

    css = (args.fa_dir / "css" / "all.min.css").read_text(encoding="utf-8")
    used = names_in_code()
    for db in args.db:
        used |= names_in_db(db)

    kept_rules, codepoints, defined = [], set(), set()
    for prelude, body in split_rules(css):
        selectors = [s.strip() for s in prelude.split(",")]
        matches = [ICON_RULE.match(s) for s in selectors]
        icon_names = [m.group(1) for m in matches if m is not None]
        if len(icon_names) == len(selectors) and body.startswith("content:"):
            defined.update(icon_names)
            keep = [s for s, name in zip(selectors, icon_names) if name in used]
            if keep:
                kept_rules.append(",".join(keep) + "{" + body + "}")
                cp = re.search(r'content:"\\([0-9a-f]+)"', body)
                if cp:
                    codepoints.add(int(cp.group(1), 16))
            continue
        if prelude.startswith("@font-face"):
            # Solo la fuente sólida (la única que usa la app); se descartan brands, regular y v4.
            if 'font-family:"Font Awesome 6 Free"' in body and "font-weight:900" in body:
                kept_rules.append(prelude + "{" + body + "}")
            continue
        kept_rules.append(prelude + "{" + body + "}")

    modifiers = {"fa-solid", "fa-regular", "fa-brands", "fa-spin", "fa-fw", "fa-lg", "fa-xs", "fa-sm", "fa-pulse"}
    unknown = sorted(n for n in used - defined if n not in modifiers and not re.match(r"fa-\d+x$", n)
                     and not any(r.startswith("." + n) or "." + n + "{" in r or "." + n + "," in r for r in kept_rules))

    # Fuente reducida
    # recalcTimestamp=False: mismos iconos -> mismos bytes -> mismo hash (no invalida la caché)
    font = TTFont(str(args.fa_dir / "webfonts" / "fa-solid-900.woff2"), recalcTimestamp=False)
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = []
    options.name_IDs = ["*"]
    options.notdef_outline = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=sorted(codepoints))
    subsetter.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    data = buf.getvalue()
    font_name = f"fa-solid-900.{hashlib.sha256(data).hexdigest()[:10]}.woff2"

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "css").mkdir(parents=True)
    (OUT / "webfonts").mkdir()
    (OUT / "webfonts" / font_name).write_bytes(data)
    out_css = "".join(kept_rules).replace(SOLID_FACE_URL, f"../webfonts/{font_name}")
    # Solo se distribuye la versión woff2: quitar el respaldo .ttf (daría 404)
    out_css = re.sub(r',url\(\.\./webfonts/fa-solid-900\.ttf\) format\("truetype"\)', "", out_css)
    assert ".ttf" not in out_css, "queda una referencia a .ttf en el CSS de iconos"
    assert font_name in out_css, "no se encontró la @font-face sólida"
    header = ("/*! Font Awesome Free 6.5.0 (subconjunto generado por tools/build_icons.py; no editar a mano)"
              f" - {len(codepoints)} iconos. Licencia: static/vendor/fontawesome/LICENSE.txt */\n")
    (OUT / "css" / "fontawesome.subset.css").write_text(header + out_css, encoding="utf-8", newline="")
    shutil.copy(args.fa_dir / "LICENSE.txt", OUT / "LICENSE.txt")

    original_font = (args.fa_dir / "webfonts" / "fa-solid-900.woff2").stat().st_size
    print(f"Iconos usados: {len(used & defined)} | glifos: {len(codepoints)}")
    print(f"CSS:    {len(css) // 1024} KB -> {len(header + out_css) // 1024} KB")
    print(f"Fuente: {original_font // 1024} KB -> {len(data) // 1024} KB ({font_name})")
    if unknown:
        print(f"AVISO: {len(unknown)} nombres no existen en Font Awesome 6.5 (no se verán): {', '.join(unknown)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
