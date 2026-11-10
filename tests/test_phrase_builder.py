"""Combinaciones del comunicador: static/js/phrase-builder.js con los pictogramas reales.

Ejecuta el JavaScript con Node (si no está instalado, se omite).
Ejecutar:  python -m unittest tests.test_phrase_builder -v
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="rehab_phrase_")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_TMP) / 'test.db'}")

from database import Database  # noqa: E402

PROJECT = Path(__file__).resolve().parent.parent
BUILDER = PROJECT / "static" / "js" / "phrase-builder.js"
NODE = shutil.which("node")

# Pictogramas del antiguo script de vocabulario: están en las bases de las clínicas, pero no en
# una base nueva (los siembra otro script), así que se definen aquí igual que allí.
LEGACY_ITEMS = {
    "aac_park": ("Parque", "Vamos al parque", "aac_places"),
    "aac_home_place": ("Casa", "Quiero ir a casa", "aac_places"),
    "aac_hospital": ("Doctor", "Necesito ir al doctor", "aac_places"),
    "aac_door": ("Puerta", "Abre la puerta por favor", "aac_home"),
}

# Pictogramas pulsados (en orden) → frase esperada
CASES = {
    "walk": "Quiero caminar",
    "walk son": "Quiero caminar con mi hijo",
    "son walk": "Quiero caminar con mi hijo",
    "son daughter walk": "Quiero caminar con mi hijo y mi hija",
    "walk listen son": "Quiero caminar y escuchar música con mi hijo",
    "pray priest": "Quiero rezar con el sacerdote",
    "call daughter": "Quiero llamar a mi hija",
    "toilet nurse": "Necesito que la enfermera me ayude a ir al baño",
    "help_up toilet nurse": "Necesito que la enfermera me ayude a levantarme e ir al baño",
    "shower comb caregiver": "Necesito que mi cuidador me ayude a bañarme y peinarme",
    "help_gen nurse": "Necesito que la enfermera me ayude",
    "company wife": "Quiero que mi esposa me acompañe",
    "company son daughter": "Quiero que mi hijo y mi hija me acompañen",
    "medicine son": "Hijo, necesito mi medicina",
    "glasses son": "Hijo, ¿dónde están mis lentes?",
    "pain_back doctor": "Doctor, me duele la espalda",
    "water son daughter": "Hijo e hija, quiero agua",
    "hello son": "Hola, hijo",
    "hello son medicine": "Hola, hijo. Necesito mi medicina",
    "son daughter": "Quiero ver a mi hijo y a mi hija",
    "doctor nurse": "Necesito al doctor y a la enfermera",
    "glasses read": "Necesito mis lentes para leer un libro",
    "help_up wheelchair": "Necesito mi silla de ruedas para levantarme",
    "phone call son": "Necesito el teléfono para llamar a mi hijo",
    "walk aac_park": "Quiero caminar por el parque",
    "go_out aac_park grandson": "Quiero salir al parque con mi nieto",
    "read aac_home_place": "Quiero leer un libro en casa",
    "aac_park son": "Vamos al parque con mi hijo",
    "aac_hospital daughter": "Necesito ir al doctor con mi hija",
    "coffee milk": "Quiero café con leche",
    "bread coffee": "Quiero pan y café",
    "more water": "Quiero más agua",
    "water please": "Quiero agua, por favor",
    "no water": "No quiero agua",
    "no pain": "No tengo dolor",
    "no thanks": "No, gracias",
    "yes water": "Sí, quiero agua",
    "tired sad": "Estoy cansado y triste",
    "pain_head pain_chest": "Me duelen la cabeza y el pecho",
    "tired cold sleep": "Estoy cansado, tengo frío y necesito dormir",
    "water medicine": "Quiero agua y necesito mi medicina",
    "cold aac_door": "Tengo frío. Abre la puerta por favor",
    "walk walk": "Quiero caminar",
}


@unittest.skipUnless(NODE, "Node.js no está instalado")
class PhraseBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = Database()
        db.initialize()
        cls.items = {i["id"]: i for i in db.get_aac_config()["items"]}
        cls.all_items = {**{k: {"id": k, "label": label, "default_phrase": phrase, "category_id": cat, "grammar": None}
                            for k, (label, phrase, cat) in LEGACY_ITEMS.items()}, **cls.items}

    def test_combinations(self):
        payload = {name: [self.all_items[i] for i in name.split()] for name in CASES}
        script = (
            "const fs=require('fs'),vm=require('vm'),ctx={};vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(BUILDER))},'utf8'),ctx);"
            "let d='';process.stdin.setEncoding('utf8').on('data',c=>d+=c).on('end',()=>{"
            "const cases=JSON.parse(d),out={};"
            "for(const k in cases){const items=cases[k].map(i=>({...i,grammar:i.grammar?JSON.parse(i.grammar):{}}));"
            "out[k]=ctx.buildPhrase(items);}"
            "process.stdout.write(JSON.stringify(out));});"
        )
        result = subprocess.run([NODE, "-e", script], input=json.dumps(payload).encode("utf-8"),
                                capture_output=True, check=True, timeout=30)
        got = json.loads(result.stdout.decode("utf-8"))
        for name, expected in CASES.items():
            with self.subTest(pictogramas=name):
                self.assertEqual(got[name], expected)

    def test_every_pictogram_alone_says_its_phrase(self):
        """Un solo pictograma no cambia: dice su frase de siempre."""
        payload = {i: [item] for i, item in self.items.items()}
        script = (
            "const fs=require('fs'),vm=require('vm'),ctx={};vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(BUILDER))},'utf8'),ctx);"
            "let d='';process.stdin.setEncoding('utf8').on('data',c=>d+=c).on('end',()=>{"
            "const cases=JSON.parse(d),out={};for(const k in cases)out[k]=ctx.buildPhrase(cases[k]);"
            "process.stdout.write(JSON.stringify(out));});"
        )
        result = subprocess.run([NODE, "-e", script], input=json.dumps(payload).encode("utf-8"),
                                capture_output=True, check=True, timeout=30)
        got = json.loads(result.stdout.decode("utf-8"))
        for i, item in self.items.items():
            self.assertEqual(got[i], item["default_phrase"].strip(), i)


if __name__ == "__main__":
    unittest.main()
