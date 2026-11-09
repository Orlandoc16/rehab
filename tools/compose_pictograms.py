"""Compone pictogramas A COLOR a partir de piezas de ARASAAC.

Algunos conceptos solo existen en ARASAAC en blanco y negro (p. ej. los parentescos). Este
script los compone con figuras a color de ARASAAC (el mismo estilo que el resto del tablero)
y marca a la persona con un círculo rojo, como hace ARASAAC en "esposo" o "esposa".

La licencia de ARASAAC (CC BY-NC-SA 4.0) permite obras derivadas no comerciales con
atribución y la misma licencia: ver static/pictograms/arasaac/LICENSE.txt.

Uso (requiere Pillow, ver requirements-dev.txt):
    python tools/compose_pictograms.py            # genera todos
    python tools/compose_pictograms.py hijo vecino   # solo algunos

Las piezas se descargan una vez en cache/arasaac_src (ignorado por git). Cada resultado se
guarda en static/pictograms/arasaac/c_<nombre>.webp (256 px, fondo blanco).
"""
from __future__ import annotations

import math
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "cache" / "arasaac_src"
OUT = ROOT / "static" / "pictograms" / "arasaac"

SIZE = 500          # se compone a 500 px y se reduce a 256 px (bordes suaves)
FINAL = 256
RED = (227, 30, 36, 255)
BLACK = (0, 0, 0, 255)

# Piezas de ARASAAC (identificador -> qué es)
MAN, WOMAN = 4665, 24621            # hombre, mujer
BOY, GIRL = 7176, 27509             # niño, niña (el niño es el mismo del resto del tablero)
GRANDPA, GRANDMA = 23718, 23710     # abuelo, abuela
RINGS = 24887                       # anillos de boda (se recortan de la escena)
HOUSE = 2317                        # casa
PATIENT_IN_BED = 39532              # paciente tumbado en la cama (el mismo niño del tablero)
BOY_HEAD = 2485                     # cabeza del niño, a color
HUNGRY, THIRSTY = 7272, 7273        # «tener hambre» / «sediento»: se usa solo su bocadillo a color


def piece(pid: int) -> Image.Image:
    """Descarga (una vez) la pieza de 500 px con fondo transparente y la recorta a su contenido."""
    path = SRC / f"{pid}.png"
    if not path.exists():
        SRC.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(f"https://static.arasaac.org/pictograms/{pid}/{pid}_500.png",
                                     headers={"User-Agent": "rehab-voice-tools"})
        with urllib.request.urlopen(req, timeout=30) as r:
            path.write_bytes(r.read())
    img = Image.open(path).convert("RGBA")
    return img.crop(img.getchannel("A").getbbox())


def crop_colored(img: Image.Image, bottom_fraction: float = 0.35, pad: int = 7) -> Image.Image:
    """Recorta solo la parte A COLOR de la pieza (p. ej. los anillos dorados, sin las figuras
    negras de la escena original), con un pequeño margen para conservar su contorno."""
    hsv = img.convert("RGB").convert("HSV")
    sat = hsv.getchannel("S").point([255 if v > 90 else 0 for v in range(256)])
    alpha = img.getchannel("A").point([255 if v > 128 else 0 for v in range(256)])
    mask = Image.composite(sat, Image.new("L", img.size, 0), alpha)
    # Solo la zona de abajo (donde están los anillos): arriba hay caras con tono de piel
    mask.paste(0, (0, 0, img.width, int(img.height * (1 - bottom_fraction))))
    bbox = mask.getbbox()
    if bbox is None:
        raise ValueError("la pieza no tiene zona a color")
    x0, y0, x1, y1 = bbox
    return img.crop((max(0, x0 - pad), max(0, y0 - pad), min(img.width, x1 + pad), min(img.height, y1 + pad)))


def scaled(img: Image.Image, height: int) -> Image.Image:
    return img.resize((max(1, round(img.width * height / img.height)), height), Image.Resampling.LANCZOS)


def place(canvas: Image.Image, img: Image.Image, height: int, cx: int, bottom: int) -> tuple[int, int, int, int]:
    """Pega la pieza con la altura dada, centrada en cx y apoyada en bottom. Devuelve su caja."""
    s = scaled(img, height)
    margin = 8   # nunca cortar la figura en el borde
    x = min(max(cx - s.width // 2, margin), SIZE - margin - s.width)
    y = bottom - s.height
    canvas.alpha_composite(s, (x, y))
    return x, y, x + s.width, y + s.height


def ring(canvas: Image.Image, box: tuple[int, int, int, int], pad: int = 16, width: int = 11) -> None:
    """Círculo rojo que marca a la persona (convención de ARASAAC)."""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(canvas)
    d.ellipse((x0 - pad, y0 - pad, x1 + pad, y1 + pad), outline=RED, width=width)


def new_canvas() -> Image.Image:
    return Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))


# --- Composiciones -----------------------------------------------------------------------

def family(adult_left: int, adult_right: int, child: int) -> Image.Image:
    """Dos adultos y, delante y en el centro, el niño o la niña marcado."""
    c = new_canvas()
    place(c, piece(adult_left), 430, 95, 492)
    place(c, piece(adult_right), 430, 405, 492)
    box = place(c, piece(child), 250, 250, 470)
    ring(c, box, pad=22)
    return c


def spouse(target: int, partner: int, target_right: bool) -> Image.Image:
    """La pareja con los anillos de boda encima; la persona nombrada, marcada."""
    c = new_canvas()
    rings = crop_colored(piece(RINGS))
    place(c, rings, 85, 250, 100)
    tx, px = (345, 140) if target_right else (155, 360)
    place(c, piece(partner), 360, px, 488)
    box = place(c, piece(target), 360, tx, 488)
    ring(c, box, pad=14)
    return c


def neighbor() -> Image.Image:
    """Dos casas juntas y, delante de la de al lado, el vecino marcado."""
    c = new_canvas()
    house = piece(HOUSE)
    place(c, house, 215, 125, 300)
    place(c, house, 215, 375, 300)
    box = place(c, piece(MAN), 280, 375, 482)
    ring(c, box, pad=12)
    return c


def curved_arrow(canvas: Image.Image, center: tuple[int, int], radius: int, start: float, end: float) -> None:
    """Flecha curva roja con borde negro (sentido horario de start a end, en grados)."""
    d = ImageDraw.Draw(canvas)
    cx, cy = center
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    d.arc(box, start, end - 6, fill=BLACK, width=30)
    d.arc(box, start + 1, end - 7, fill=RED, width=18)
    # Punta: triángulo tangente al arco en el ángulo final
    a = math.radians(end)
    tip = (cx + radius * math.cos(a + 0.12), cy + radius * math.sin(a + 0.12))
    base = (cx + radius * math.cos(a - 0.10), cy + radius * math.sin(a - 0.10))
    nx, ny = math.cos(a), math.sin(a)       # dirección radial
    w = 34
    pts = [tip, (base[0] + nx * w, base[1] + ny * w), (base[0] - nx * w, base[1] - ny * w)]
    d.polygon(pts, fill=RED, outline=BLACK, width=5)


def reposition() -> Image.Image:
    """El paciente en la cama con una flecha de giro: «necesito cambiar de posición»."""
    c = new_canvas()
    bed = piece(PATIENT_IN_BED)
    height = min(270, round(470 * bed.height / bed.width))   # ancha pero sin salirse
    place(c, bed, height, 250, 492)
    # La flecha va por encima del paciente, sin tocarlo
    curved_arrow(c, (250, 245), 175, 198, 342)
    return c


def crop_box(img: Image.Image, left: float, top: float, right: float, bottom: float) -> Image.Image:
    """Recorta una zona (fracciones del ancho/alto) y la ajusta a su contenido."""
    part = img.crop((int(img.width * left), int(img.height * top), int(img.width * right), int(img.height * bottom)))
    bbox = part.getchannel("A").getbbox()
    return part.crop(bbox) if bbox else part


def thinking_of(source: int) -> Image.Image:
    """La cabeza del niño a color pensando en algo (el bocadillo de la pieza original, arriba a la derecha)."""
    c = new_canvas()
    place(c, piece(BOY_HEAD), 300, 190, 492)
    bubble = crop_box(piece(source), 0.55, 0.0, 1.0, 0.45)
    place(c, bubble, 215, 375, 235)
    return c


COMPOSITIONS = {
    "hijo": lambda: family(MAN, WOMAN, BOY),
    "hija": lambda: family(MAN, WOMAN, GIRL),
    "nieto": lambda: family(GRANDPA, GRANDMA, BOY),
    "nieta": lambda: family(GRANDPA, GRANDMA, GIRL),
    "esposo": lambda: spouse(MAN, WOMAN, target_right=True),
    "esposa": lambda: spouse(WOMAN, MAN, target_right=False),
    "vecino": neighbor,
    "acomodarme": reposition,
    # Palabras de práctica
    "hambre": lambda: thinking_of(HUNGRY),
    "sed": lambda: thinking_of(THIRSTY),
}


def save(img: Image.Image, name: str) -> Path:
    white = Image.new("RGBA", img.size, (255, 255, 255, 255))
    white.alpha_composite(img)
    out = OUT / f"c_{name}.webp"
    white.convert("RGB").resize((FINAL, FINAL), Image.Resampling.LANCZOS).save(out, "WEBP", quality=85, method=6)
    return out


def main(names: list[str]) -> None:
    unknown = set(names) - set(COMPOSITIONS)
    if unknown:
        sys.exit(f"Desconocidos: {', '.join(sorted(unknown))}. Disponibles: {', '.join(COMPOSITIONS)}")
    for name in names or list(COMPOSITIONS):
        out = save(COMPOSITIONS[name](), name)
        print(f"{name:12s} -> {out.relative_to(ROOT).as_posix()} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1:])
