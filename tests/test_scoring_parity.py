"""La puntuación en JavaScript (static/js/scoring.js, la que usa la app Android sin servidor)
debe dar EXACTAMENTE lo mismo que VoiceProcessor._score_transcription en Python.

Genera miles de casos (palabras y frases reales con errores típicos: omisiones, sustituciones,
palabras de más, tildes, mayúsculas, puntuación de Whisper...) y compara el resultado entero.
Ejecutar:  python -m unittest tests.test_scoring_parity -v   (si no hay Node, se omite)
"""
import contextlib
import io
import json
import math
import random
import shutil
import subprocess
import unittest
from pathlib import Path

from word_images import WORD_IMAGES

PROJECT = Path(__file__).resolve().parent.parent
SCORING = PROJECT / "static" / "js" / "scoring.js"
NODE = shutil.which("node")

EXTRA_TARGETS = [
    "adiós", "pingüino", "niño", "mañana", "corazón", "teléfono", "queso", "guitarra", "guerra",
    "rojo", "perro", "pero", "carro", "caro", "llave", "lluvia", "chocolate", "xilófono", "México",
    "examen", "hoy", "rey", "yo", "ayer", "whisky", "kilo", "zapato", "cielo", "gente", "agua",
    "¿Cómo estás?", "Buenos días, ¿qué tal?", "Quiero beber agua por favor", "el", "a", "sí",
]
WHISPER_NOISE = ["", " ", "...", "[BLANK_AUDIO]", "(Subtítulos realizados por la comunidad)", "¡Pero",
                 "Gracias.", "- ¿Qué?", "«hola»", "Sí, sí, sí.", "1 2 3", "Ñandú", "¿Eh?", "Ah", "Mmm"]
SWAPS = {"r": "l", "l": "r", "s": "", "n": "m", "ch": "s", "j": "h", "g": "j", "b": "v", "c": "k", "rr": "r",
         "ll": "y", "d": "t", "p": "b", "t": "d", "a": "e", "o": "u"}
FILLERS = ["el", "la", "eh", "yo", "quiero", "por favor", "este", "mmm", "un"]


def variants(target: str, rnd: random.Random):
    out = {target, target.upper(), target.capitalize() + ".", f"¡{target}!", f"¿{target}?", f" {target} ",
           f"{target}, {target}", f"[música] {target}", f"- {target} -"}
    letters = list(target)
    if len(letters) > 1:
        for _ in range(3):
            i = rnd.randrange(len(letters))
            out.add("".join(letters[:i] + letters[i + 1:]))          # omisión
        out.add(target[: max(1, len(target) // 2)])                    # truncada
        out.add(target[::-1])                                           # disparate
        i = rnd.randrange(len(letters) - 1)
        out.add("".join(letters[:i] + [letters[i + 1], letters[i]] + letters[i + 2:]))  # metátesis
    for a, b in SWAPS.items():
        if a in target:
            out.add(target.replace(a, b, 1))
    for f in rnd.sample(FILLERS, 3):
        out.add(f"{f} {target}")
        out.add(f"{target} {f}")
    out.add(f"{rnd.choice(FILLERS)} {target} {rnd.choice(FILLERS)} {rnd.choice(FILLERS)}")
    out.add(" ".join([target] + rnd.sample(FILLERS, 4)))                # demasiadas palabras extra
    out.add(rnd.choice(WHISPER_NOISE))
    return sorted(out)


def build_cases(seed: int = 7):
    rnd = random.Random(seed)
    targets = sorted({k.split("/", 1)[1] for k in WORD_IMAGES}) + EXTRA_TARGETS
    cases = []
    for t in targets:
        for v in variants(t, rnd):
            cases.append({"t": v, "w": t, "l": rnd.randint(0, 6), "o": rnd.choice([0, 0, -15, -7, 5, 15, 30])})
    for v in WHISPER_NOISE:
        for t in ("agua", "buenos dias"):
            cases.append({"t": v, "w": t, "l": 1, "o": 0})
    cases.append({"t": "agua", "w": "", "l": 1, "o": 0})
    return cases


def strip_volatile(result):
    result = dict(result)
    result.pop("timestamp", None)
    return result


def assert_close(test, py, js, path="resultado"):
    if isinstance(py, bool) or isinstance(js, bool):
        test.assertEqual(py, js, path)
    elif isinstance(py, (int, float)) and isinstance(js, (int, float)):
        test.assertTrue(math.isclose(py, js, rel_tol=1e-9, abs_tol=1e-9), f"{path}: {py} != {js}")
    elif isinstance(py, dict) and isinstance(js, dict):
        test.assertEqual(sorted(py), sorted(js), f"{path}: claves distintas")
        for k in py:
            assert_close(test, py[k], js[k], f"{path}.{k}")
    elif isinstance(py, (list, tuple)) and isinstance(js, list):
        test.assertEqual(len(py), len(js), f"{path}: longitud distinta")
        for i, (a, b) in enumerate(zip(py, js)):
            assert_close(test, a, b, f"{path}[{i}]")
    else:
        test.assertEqual(py, js, path)


@unittest.skipUnless(NODE, "Node.js no está instalado")
class ScoringParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("STT_ENGINE", "none")
        from voice_processor import VoiceProcessor
        with contextlib.redirect_stdout(io.StringIO()):
            cls.vp = VoiceProcessor.__new__(VoiceProcessor)  # sin cargar modelos: solo la puntuación
            cls.vp.phonetic_cache = {}

    def run_js(self, cases):
        script = (
            "const fs=require('fs'),vm=require('vm'),ctx={};vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(SCORING))},'utf8'),ctx);"
            "let d='';process.stdin.setEncoding('utf8').on('data',c=>d+=c).on('end',()=>{"
            "const out=JSON.parse(d).map(c=>ctx.RehabScoring.scoreTranscription(c.t,c.w,c.l,c.o));"
            "process.stdout.write(JSON.stringify(out));});"
        )
        res = subprocess.run([NODE, "-e", script], input=json.dumps(cases).encode("utf-8"),
                             capture_output=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stderr.decode("utf-8", "replace"))
        return json.loads(res.stdout.decode("utf-8"))

    def test_same_result_as_python(self):
        cases = build_cases()
        self.assertGreater(len(cases), 3000)
        js = self.run_js(cases)
        failures = 0
        for case, got in zip(cases, js):
            with contextlib.redirect_stdout(io.StringIO()):
                expected = self.vp._score_transcription(case["t"], case["w"], case["l"], case["o"])
            with self.subTest(oido=case["t"], objetivo=case["w"], nivel=case["l"], ajuste=case["o"]):
                try:
                    assert_close(self, strip_volatile(expected), strip_volatile(got))
                except AssertionError:
                    failures += 1
                    if failures > 15:
                        self.fail("demasiadas diferencias; se corta aquí")
                    raise

    def test_metaphone_matches(self):
        words = sorted({w for k in WORD_IMAGES for w in k.split("/", 1)[1].split()} |
                       {"xilofono", "examen", "hoy", "rey", "whisky", "guerra", "pinguino", "nandu", "llave"})
        script = (
            "const fs=require('fs'),vm=require('vm'),ctx={};vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(SCORING))},'utf8'),ctx);"
            "let d='';process.stdin.setEncoding('utf8').on('data',c=>d+=c).on('end',()=>{"
            "process.stdout.write(JSON.stringify(JSON.parse(d).map(w=>ctx.RehabScoring.spanishMetaphone(w))));});"
        )
        res = subprocess.run([NODE, "-e", script], input=json.dumps(words).encode("utf-8"),
                             capture_output=True, check=True, timeout=60)
        for w, code in zip(words, json.loads(res.stdout.decode("utf-8"))):
            self.assertEqual(self.vp._spanish_metaphone(w), code, w)

    def test_syllables_match(self):
        """static/js/syllables.js == syllables.py (pista silábica bajo cada palabra)."""
        from syllables import syllabify
        rnd = random.Random(3)
        texts = sorted({k.split("/", 1)[1] for k in WORD_IMAGES}) + EXTRA_TARGETS + [
            "ahora", "hoy", "muy", "rey", "yo", "ayer", "guion", "pingüino", "construir", "instrumento",
            "transporte", "abstracto", "País", "baúl", "aéreo", "poeta", "Queso", "GUITARRA", "Ñandú",
            "biología", "cigüeña", "chocolate", "llorar", "perro", "", "123", "¿Qué tal?", "x", "hmm"]
        texts += ["".join(rnd.choice("aeiouyhrlsnctpbgqcñüáé") for _ in range(rnd.randint(1, 9))) for _ in range(400)]
        script = (
            "const fs=require('fs'),vm=require('vm'),ctx={};vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(PROJECT / 'static' / 'js' / 'syllables.js'))},'utf8'),ctx);"
            "let d='';process.stdin.setEncoding('utf8').on('data',c=>d+=c).on('end',()=>{"
            "process.stdout.write(JSON.stringify(JSON.parse(d).map(t=>ctx.RehabSyllables.syllabify(t))));});"
        )
        res = subprocess.run([NODE, "-e", script], input=json.dumps(texts).encode("utf-8"),
                             capture_output=True, check=True, timeout=60)
        for t, got in zip(texts, json.loads(res.stdout.decode("utf-8"))):
            self.assertEqual(syllabify(t), got, t)


if __name__ == "__main__":
    unittest.main()
