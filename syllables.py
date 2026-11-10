"""Separación silábica del español para la pista que se muestra bajo la palabra ("a-gua",
"ten-go", "por fa-vor").

Reglas (RAE, ortografía):
- ch, ll, rr y qu / gu (ante e, i) cuentan como una sola consonante.
- Grupos inseparables que van con la vocal siguiente: pr br tr dr cr gr fr pl bl cl gl fl.
- Entre vocales: 1 consonante -> V-CV; 2 -> VC-CV (salvo grupo inseparable: V-CCV);
  3 -> VC-CCV si las dos últimas forman grupo, si no VCC-CV; 4 -> VCC-CCV.
- Vocales: dos abiertas (a, e, o) forman hiato; una cerrada con tilde (í, ú) también; las demás
  combinaciones son diptongo o triptongo. La "y" final o ante consonante es vocal ("hoy", "muy").
- La "h" es una consonante más ("a-ho-ra").
"""
import re

_VOWELS = set("aeiouáéíóúü")
_STRONG = set("aeoáéóíú")          # abiertas, y cerradas con tilde (rompen el diptongo)
_CLUSTERS = {"pr", "br", "tr", "dr", "cr", "gr", "fr", "pl", "bl", "cl", "gl", "fl"}
_DIGRAPHS = ("ch", "ll", "rr")


def _units(word: str):
    """Divide la palabra en unidades (texto original, tipo 'V' o 'C')."""
    low = word.lower()
    units = []
    i = 0
    while i < len(word):
        c = low[i]
        two = low[i:i + 2]
        nxt = low[i + 2:i + 3]
        if two in _DIGRAPHS:
            units.append((word[i:i + 2], "C"))
            i += 2
        elif two in ("qu", "gu") and nxt in ("e", "i", "é", "í"):
            # la u no suena: "que", "gui"
            units.append((word[i:i + 2], "C"))
            i += 2
        elif c == "y":
            # vocal al final de palabra o ante consonante ("hoy", "muy"); si no, consonante
            after = low[i + 1:i + 2]
            is_vowel = (after == "" or after not in _VOWELS) and i > 0
            units.append((word[i], "V" if is_vowel else "C"))
            i += 1
        elif c in _VOWELS:
            units.append((word[i], "V"))
            i += 1
        else:
            units.append((word[i], "C"))
            i += 1
    return units


def _split_consonants(cons):
    """Cuántas consonantes del grupo intervocálico se quedan en la sílaba anterior."""
    n = len(cons)
    if n <= 1:
        return 0
    last_two = (cons[-2] + cons[-1]).lower()
    if n == 2:
        return 0 if last_two in _CLUSTERS else 1
    if n == 3:
        return 1 if last_two in _CLUSTERS else 2
    return n - 2


def split_word(word: str):
    """Sílabas de una palabra: split_word("agua") -> ["a", "gua"]."""
    units = _units(word)
    if not any(kind == "V" for _, kind in units):
        return [word] if word else []

    # Núcleos vocálicos: rachas de vocales, partidas en los hiatos
    nuclei = []          # lista de (inicio, fin) en índices de units
    i = 0
    while i < len(units):
        if units[i][1] != "V":
            i += 1
            continue
        start = i
        while i + 1 < len(units) and units[i + 1][1] == "V":
            a, b = units[i][0].lower(), units[i + 1][0].lower()
            if a in _STRONG and b in _STRONG:
                break                     # hiato: a-e, e-o, í-a, a-ú...
            i += 1
        nuclei.append((start, i))
        i += 1

    # Dónde empieza cada sílaba (la primera, en 0)
    starts = [0]
    for (_, end_prev), (start_next, _) in zip(nuclei, nuclei[1:]):
        cons = [units[k][0] for k in range(end_prev + 1, start_next)]
        starts.append(end_prev + 1 + _split_consonants(cons))
    starts.append(len(units))

    return ["".join(u for u, _ in units[a:b]) for a, b in zip(starts, starts[1:])]


def syllabify(text: str) -> str:
    """Pista silábica de una palabra o frase: "por favor" -> "por fa-vor"."""
    words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", text or "")
    return " ".join("-".join(split_word(w)) for w in words)
