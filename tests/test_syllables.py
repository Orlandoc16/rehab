"""Separación silábica de la pista que se muestra bajo la palabra (syllables.py)."""
import unittest

from syllables import syllabify

CASES = {
    # errores del algoritmo anterior
    "agua": "a-gua",
    "por favor": "por fa-vor",
    "tengo": "ten-go",
    "pierna": "pier-na",
    "arroz": "a-rroz",
    "alegría": "a-le-grí-a",
    "necesito ayuda": "ne-ce-si-to a-yu-da",
    # dígrafos y qu / gu
    "leche": "le-che",
    "calle": "ca-lle",
    "perro": "pe-rro",
    "quiero": "quie-ro",
    "guitarra": "gui-ta-rra",
    "pingüino": "pin-güi-no",
    # grupos consonánticos
    "gracias": "gra-cias",
    "abrazo": "a-bra-zo",
    "hospital": "hos-pi-tal",
    "instante": "ins-tan-te",
    "transporte": "trans-por-te",
    "obstrucción": "obs-truc-ción",
    # diptongos, hiatos, y, h
    "ciudad": "ciu-dad",
    "buenos días": "bue-nos dí-as",
    "país": "pa-ís",
    "reír": "re-ír",
    "aéreo": "a-é-re-o",
    "hoy": "hoy",
    "muy": "muy",
    "Paraguay": "Pa-ra-guay",
    "ahora": "a-ho-ra",
    "cacahuete": "ca-ca-hue-te",
    # mayúsculas y puntuación
    "¿Dónde está el baño?": "Dón-de es-tá el ba-ño",
    "": "",
}


class SyllabifyTest(unittest.TestCase):
    def test_cases(self):
        for text, expected in CASES.items():
            with self.subTest(text=text):
                self.assertEqual(syllabify(text), expected)


if __name__ == "__main__":
    unittest.main()
