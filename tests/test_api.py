"""Tests de caracterización de la API y de las páginas.

Fijan el comportamiento actual para poder refactorizar (Sprint 2) con red de seguridad.
No cargan Whisper (STT_ENGINE=none) y usan una base de datos SQLite temporal.

Ejecutar:  python -m unittest discover -s tests -v
"""
import os
import re
import csv
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional

_TMP = tempfile.mkdtemp(prefix="rehab_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP) / 'test.db'}"
os.environ["STT_ENGINE"] = "none"

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
import auth  # noqa: E402
from rehab import security  # noqa: E402
from database import PICTOGRAM_IMAGES, word_image_key  # noqa: E402
from word_images import WORD_IMAGES  # noqa: E402

PROJECT = Path(__file__).resolve().parent.parent
PAGES = ["/", "/practice", "/games", "/progress", "/communicator"]


async def _fake_tts(text, voice="es-ES-ElviraNeural", speed="normal"):
    """Sin síntesis real: las rutas de práctica lanzan TTS en segundo plano."""
    return str(Path(_TMP) / "silence.mp3")


PASSWORD = "clave-de-prueba-123"


def login(c: TestClient, username: str = "tester", patient_id: Optional[str] = "default") -> None:
    r = c.post("/login", data={"username": username, "password": PASSWORD, "next": "/"})
    assert r.status_code in (200, 303), r.text  # 303 si el cliente no sigue redirecciones
    assert auth.SESSION_COOKIE in c.cookies
    if patient_id:
        c.post("/patients/select", data={"patient_id": patient_id, "next": "/"})


def setUpModule():
    global client
    app_module.voice_processor.text_to_speech = _fake_tts
    client = TestClient(app_module.app)
    client.__enter__()  # ejecuta el lifespan (crea tablas y datos iniciales)
    app_module.db.create_therapist("tester", "Terapeuta de Prueba", auth.hash_password(PASSWORD))
    login(client)


def tearDownModule():
    client.__exit__(None, None, None)
    shutil.rmtree(_TMP, ignore_errors=True)


class PagesTest(unittest.TestCase):
    def test_pages_render_with_compiled_css(self):
        for path in PAGES:
            with self.subTest(path=path):
                r = client.get(path)
                self.assertEqual(r.status_code, 200)
                html = r.text
                self.assertNotIn("cdn.tailwindcss.com", html)
                self.assertNotIn("fonts.googleapis.com", html)
                self.assertNotIn("cdnjs.cloudflare.com", html)
                self.assertIn("/static/css/fonts.css?v=", html)
                self.assertRegex(html, r'href="/static/css/app\.css\?v=[0-9a-f]{10}"')
                self.assertIn('id="mobile-menu-btn"', html)
                self.assertIn("/static/js/nav.js?v=", html)

    def test_active_nav_item(self):
        html = client.get("/practice").text
        self.assertIn('<a href="/practice"\n                        class="px-4 py-2 rounded-xl bg-white text-primary', html)


class AuthTest(unittest.TestCase):
    """Acceso solo para terapeutas y datos separados por paciente."""

    def anonymous(self) -> TestClient:
        return TestClient(app_module.app, follow_redirects=False)

    def test_password_hashing(self):
        h1, h2 = auth.hash_password("secreto-123"), auth.hash_password("secreto-123")
        self.assertNotEqual(h1, h2)  # sal distinta
        self.assertTrue(auth.verify_password("secreto-123", h1))
        self.assertFalse(auth.verify_password("otra-cosa", h1))
        self.assertFalse(auth.verify_password("x", "basura"))

    def test_everything_requires_login_except_public_files(self):
        c = self.anonymous()
        r = c.get("/practice")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/login?next=/practice")
        self.assertEqual(c.get("/api/categories").status_code, 401)
        self.assertEqual(c.get("/api/progress/default").status_code, 401)
        self.assertEqual(c.post("/api/progress", json={"score": 100}).status_code, 401)
        for public in ("/login", "/sw.js", "/static/css/app.css", "/static/manifest.webmanifest"):
            self.assertEqual(c.get(public).status_code, 200, public)

    def test_wrong_password(self):
        r = self.anonymous().post("/login", data={"username": "tester", "password": "incorrecta"})
        self.assertEqual(r.status_code, 401)
        self.assertIn("Usuario o contraseña incorrectos", r.text)
        r = self.anonymous().post("/login", data={"username": "no-existe", "password": "incorrecta"})
        self.assertEqual(r.status_code, 401)

    def test_login_is_rate_limited(self):
        saved = security.login_limiter
        security.login_limiter = auth.LoginRateLimiter(max_failures=3, lockout_s=60)
        try:
            c = self.anonymous()
            for _ in range(3):
                self.assertEqual(c.post("/login", data={"username": "tester", "password": "mal"}).status_code, 401)
            r = c.post("/login", data={"username": "tester", "password": PASSWORD})
            self.assertEqual(r.status_code, 429)  # bloqueado aunque la contraseña sea correcta
        finally:
            security.login_limiter = saved

    def test_no_open_redirect_after_login(self):
        r = self.anonymous().post("/login", data={"username": "tester", "password": PASSWORD, "next": "//evil.example"})
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/patients?next=/")

    def test_session_cookie_is_httponly(self):
        r = self.anonymous().post("/login", data={"username": "tester", "password": PASSWORD})
        cookie = r.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)

    def test_patient_must_be_selected(self):
        c = TestClient(app_module.app, follow_redirects=False)
        login(c, patient_id=None)
        self.assertEqual(c.get("/api/categories").status_code, 409)
        r = c.get("/progress")
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r.headers["location"].startswith("/patients"))

    def test_progress_is_isolated_per_patient(self):
        other = TestClient(app_module.app)
        login(other, patient_id=None)
        other.post("/patients/new", data={"name": "Paciente Aislado", "age": "70", "next": "/"})
        before_main = client.get("/api/progress/default").json()["stats"]["total_attempts"]

        word = other.get("/api/words/" + other.get("/api/categories").json()["categories"][0]["id"]).json()["words"][0]
        # El navegador intenta escribir en el paciente "default": el servidor usa el de la sesión
        other.post("/api/progress", json={"patient_id": "default", "word_id": word["id"], "score": 80})

        self.assertEqual(other.get("/api/progress/default").json()["stats"]["total_attempts"], 1)
        self.assertEqual(client.get("/api/progress/default").json()["stats"]["total_attempts"], before_main)

    def test_logout_ends_session(self):
        c = TestClient(app_module.app, follow_redirects=False)
        login(c)
        self.assertEqual(c.get("/api/categories").status_code, 200)
        r = c.post("/logout")
        self.assertEqual(r.headers["location"], "/login?logout=1")
        self.assertEqual(c.get("/api/categories").status_code, 401)

    def test_header_shows_active_patient(self):
        html = client.get("/practice").text
        self.assertIn("Paciente Demo", html)
        self.assertIn('action="/logout"', html)


class OfflineAppTest(unittest.TestCase):
    """Comunicador sin conexión: service worker en la raíz, manifest e iconos."""

    def test_service_worker_is_served_from_root_without_cache(self):
        r = client.get("/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r.headers["content-type"])
        self.assertEqual(r.headers["cache-control"], "no-cache")
        self.assertIn("/communicator", r.text)

    def test_manifest_and_icons(self):
        import json
        r = client.get("/static/manifest.webmanifest")
        self.assertEqual(r.status_code, 200)
        manifest = json.loads(r.text)
        self.assertEqual(manifest["display"], "standalone")
        for icon in manifest["icons"]:
            self.assertTrue((PROJECT / icon["src"].lstrip("/")).exists(), icon["src"])

    def test_pages_register_service_worker(self):
        for path in PAGES:
            with self.subTest(path=path):
                html = client.get(path).text
                self.assertIn("/static/js/sw-register.js?v=", html)
                self.assertIn('rel="manifest"', html)


class StaticFilesTest(unittest.TestCase):
    def test_versioned_assets_are_cached_for_a_year(self):
        html = client.get("/").text
        url = html.split('href="/static/css/app.css', 1)[1].split('"', 1)[0]
        r = client.get("/static/css/app.css" + url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["cache-control"], "public, max-age=31536000, immutable")

    def test_unversioned_assets_revalidate_hourly(self):
        r = client.get("/static/css/style.css")
        self.assertEqual(r.headers["cache-control"], "public, max-age=3600")

    def test_text_is_gzipped_but_images_are_not(self):
        css = client.get("/static/css/app.css", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(css.headers.get("content-encoding"), "gzip")
        img = client.get("/static/pictograms/arasaac/2445.webp", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(img.status_code, 200)
        self.assertNotIn("content-encoding", img.headers)


class WordsApiTest(unittest.TestCase):
    def test_categories(self):
        r = client.get("/api/categories")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.json()["categories"]), 0)

    def test_words_by_category(self):
        cat = client.get("/api/categories").json()["categories"][0]["id"]
        r = client.get(f"/api/words/{cat}", params={"level": 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["category"], cat)

    def test_practice_words_spaced_repetition(self):
        cat = client.get("/api/categories").json()["categories"][0]["id"]
        r = client.get(f"/api/words/practice/{cat}", params={"count": 3, "patient_id": "default"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["method"], "spaced_repetition")
        self.assertLessEqual(len(body["words"]), 3)
        for w in body["words"]:
            self.assertIn("practice_stats", w)


class ProgressAndGamesApiTest(unittest.TestCase):
    def test_save_progress_awards_points(self):
        word = client.get("/api/words/practice/" + client.get("/api/categories").json()["categories"][0]["id"]).json()["words"][0]
        r = client.post("/api/progress", json={"patient_id": "default", "word_id": word["id"], "score": 90})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])
        stats = client.get("/api/stats/default")
        self.assertEqual(stats.status_code, 200)

    def test_player_level_uses_server_points(self):
        """La tarjeta de nivel de /games sale de los puntos reales del paciente (antes, de localStorage)."""
        before = client.get("/api/games/level/default").json()
        self.assertEqual(set(before) >= {"level", "icon", "total_points", "progress_to_next", "next_level", "points_to_next"}, True)
        r = client.post("/api/progress", json={"word_id": "game_match", "score": 100, "transcription": "Juego: word_match"})
        after = client.get("/api/games/level/default").json()
        self.assertEqual(after["total_points"], before["total_points"] + r.json()["points_earned"])

    def test_games_page_loads_games_script(self):
        html = client.get("/games").text
        self.assertIn("/static/js/games.js", html)
        self.assertNotIn("webkitSpeechRecognition", html)  # la voz no sale hacia Google

    def test_complete_challenge_validates_input(self):
        # Validación Pydantic: cuerpo incompleto -> 422 con el detalle del campo
        r = client.post("/api/games/complete-challenge", json={})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"][0]["loc"], ["body", "challenge_id"])

    def test_progress_validation(self):
        word_id = client.get("/api/words/" + client.get("/api/categories").json()["categories"][0]["id"]).json()["words"][0]["id"]
        for bad in ({}, {"word_id": word_id}, {"word_id": word_id, "score": -5},
                    {"word_id": word_id, "score": "mucho"}, {"word_id": "", "score": 50}):
            with self.subTest(body=bad):
                self.assertEqual(client.post("/api/progress", json=bad).status_code, 422)

    def test_game_scores_above_100_are_clamped_not_rejected(self):
        # Juegos como Memoria envían nivel x 20 (p. ej. 120): se guarda como 100
        from database import Progress
        r = client.post("/api/progress", json={"word_id": "game_memory", "score": 120, "feedback": {"level": 6},
                                               "transcription": "Game: memory", "duration_ms": 12.6, "extra": "ignorado"})
        self.assertEqual(r.status_code, 200)
        session = app_module.db.SessionLocal()
        try:
            row = session.query(Progress).filter(Progress.word_id == "game_memory").one()
            self.assertEqual(row.score, 100)
            self.assertEqual(row.duration_ms, 13)
            self.assertEqual(row.patient_id, "default")
        finally:
            session.close()

    def test_custom_word_validation(self):
        self.assertEqual(client.post("/api/words", json={"word": ""}).status_code, 422)
        self.assertEqual(client.post("/api/words", json={"word": "mesa", "level": 9}).status_code, 422)
        self.assertEqual(client.post("/api/words", json={"word": "mesita", "category_id": "custom"}).status_code, 200)

    def test_complete_challenge_awards_points(self):
        ch = client.get("/api/games/daily-challenge").json()
        r = client.post("/api/games/complete-challenge",
                        json={"patient_id": "default", "challenge_id": ch["id"], "score": 90})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])

    def test_achievements(self):
        r = client.get("/api/games/achievements/default")
        self.assertEqual(r.status_code, 200)
        self.assertIn("unlocked", r.json())


class CorrectnessAndTherapistLabelTest(unittest.TestCase):
    """Una sola definición de «correcto», valoración del terapeuta y juegos fuera de las
    estadísticas de pronunciación. Cada prueba usa un paciente nuevo para no mezclar datos."""

    def setUp(self):
        self.c = TestClient(app_module.app)
        login(self.c, patient_id=None)
        self.c.post("/patients/new", data={"name": "Paciente Correctos", "next": "/"})
        cat = self.c.get("/api/categories").json()["categories"][0]["id"]
        self.words = self.c.get(f"/api/words/{cat}").json()["words"]

    def _daily_correct(self):
        return sum(d["correct"] for d in self.c.get("/api/stats/default").json()["daily_progress"])

    def test_games_do_not_count_as_speech_attempts(self):
        self.c.post("/api/progress", json={"word_id": "game_match", "score": 100})
        self.c.post("/api/progress", json={"word_id": self.words[0]["id"], "score": 40, "is_correct": False})
        progress = self.c.get("/api/progress/default").json()
        self.assertEqual(progress["stats"]["total_attempts"], 1)
        self.assertEqual(progress["stats"]["average_score"], 40)
        self.assertTrue(all(not a["word_id"].startswith("game_") for a in progress["recent_attempts"]))
        daily = self.c.get("/api/stats/default").json()["daily_progress"]
        self.assertEqual(sum(d["attempts"] for d in daily), 1)

    def test_level_threshold_and_therapist_decide_correctness(self):
        word_id = self.words[0]["id"]
        # 75 % pero el analizador dijo que no llegaba al umbral: no cuenta como correcto
        r = self.c.post("/api/progress", json={"word_id": word_id, "score": 75, "is_correct": False})
        attempt_id = r.json()["id"]
        self.assertEqual(self._daily_correct(), 0)
        # 62 % por encima del umbral del nivel 1: sí cuenta (antes hacía falta un 70)
        self.c.post("/api/progress", json={"word_id": word_id, "score": 62, "is_correct": True})
        self.assertEqual(self._daily_correct(), 1)

        # El terapeuta manda; quitar la valoración vuelve a la automática
        self.assertEqual(self.c.post(f"/api/progress/{attempt_id}/label", json={"correct": True}).status_code, 200)
        self.assertEqual(self._daily_correct(), 2)
        self.c.post(f"/api/progress/{attempt_id}/label", json={"correct": None})
        self.assertEqual(self._daily_correct(), 1)

    def test_label_only_for_own_speech_attempts(self):
        game_id = self.c.post("/api/progress", json={"word_id": "game_maze", "score": 100}).json()["id"]
        self.assertEqual(self.c.post(f"/api/progress/{game_id}/label", json={"correct": True}).status_code, 404)
        own = self.c.post("/api/progress", json={"word_id": self.words[0]["id"], "score": 50}).json()["id"]
        # Otro paciente (la sesión principal) no puede valorar intentos ajenos
        self.assertEqual(client.post(f"/api/progress/{own}/label", json={"correct": True}).status_code, 404)
        self.assertEqual(self.c.post("/api/progress/no-existe/label", json={"correct": True}).status_code, 404)

    def test_difficult_words_are_reported(self):
        hard, easy = self.words[0], self.words[1]
        for score in (30, 40):
            self.c.post("/api/progress", json={"word_id": hard["id"], "score": score})
        for score in (95, 100):
            self.c.post("/api/progress", json={"word_id": easy["id"], "score": score})
        difficult = self.c.get("/api/stats/default").json()["difficult_words"]
        self.assertEqual([(d["word"], d["attempts"], d["avg_score"]) for d in difficult], [(hard["word"], 2, 35.0)])

    def test_therapist_validation_removes_word_from_difficult(self):
        word = self.words[0]
        ids = [self.c.post("/api/progress", json={"word_id": word["id"], "score": 50, "is_correct": False}).json()["id"]
               for _ in range(2)]
        self.assertEqual([d["word"] for d in self.c.get("/api/stats/default").json()["difficult_words"]], [word["word"]])
        for pid in ids:
            self.c.post(f"/api/progress/{pid}/label", json={"correct": True})
        self.assertEqual(self.c.get("/api/stats/default").json()["difficult_words"], [])


class CalibrateThresholdsToolTest(unittest.TestCase):
    def test_uses_therapist_labels_and_recommends_per_level(self):
        import subprocess
        import sys
        c = TestClient(app_module.app)
        login(c, patient_id=None)
        c.post("/patients/new", data={"name": "Paciente Calibrar", "next": "/"})
        word = c.get("/api/words/" + c.get("/api/categories").json()["categories"][0]["id"],
                     params={"level": 1}).json()["words"][0]
        for heard, ok in ((word["word"], True), ("xyz", False)):
            pid = c.post("/api/progress", json={"word_id": word["id"], "score": 50, "transcription": heard}).json()["id"]
            c.post(f"/api/progress/{pid}/label", json={"correct": ok})
        out = subprocess.run([sys.executable, str(PROJECT / "tools/calibrate_thresholds.py"), "--min", "2"],
                             capture_output=True, text=True, encoding="utf-8",
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"}).stdout
        self.assertIn("terapeuta: 2", out)
        self.assertIn("Nivel 1: 2 intentos (1 bien dichos, 1 mal dichos)", out)
        self.assertIn("<- actual", out)


class PhoneticHintTest(unittest.TestCase):
    def test_seeded_words_use_correct_syllables(self):
        words = {w["word"]: w["phonetic_hint"] for w in app_module.db.get_all_words()}
        for word, hint in {"agua": "a-gua", "por favor": "por fa-vor", "tengo": "ten-go"}.items():
            if word in words:
                self.assertEqual(words[word], hint)

    def test_old_hints_are_fixed_but_custom_hints_kept(self):
        from database import Word
        session = app_module.db.SessionLocal()
        try:
            session.add_all([Word(id="hint_old", word="pierna", category_id="custom", level=1, phonetic_hint="pi-erna"),
                             Word(id="hint_mine", word="pierna", category_id="custom", level=1, phonetic_hint="PIER-na")])
            session.commit()
        finally:
            session.close()
        app_module.db._refresh_phonetic_hints()
        session = app_module.db.SessionLocal()
        try:
            self.assertEqual(session.get(Word, "hint_old").phonetic_hint, "pier-na")
            self.assertEqual(session.get(Word, "hint_mine").phonetic_hint, "PIER-na")
            session.query(Word).filter(Word.id.in_(["hint_old", "hint_mine"])).delete()
            session.commit()
        finally:
            session.close()


class SpeakApiTest(unittest.TestCase):
    """La voz se sirve con su tipo real y, si no hay motor, la página recibe un 503 claro."""

    def _with_tts(self, fake):
        original = app_module.voice_processor.text_to_speech
        app_module.voice_processor.text_to_speech = fake
        self.addCleanup(setattr, app_module.voice_processor, "text_to_speech", original)

    def test_wav_is_served_as_wav(self):
        wav = Path(_TMP) / "voz.wav"
        wav.write_bytes(b"RIFF0000WAVEfmt ")

        async def fake(text, voice="", speed="normal"):
            return str(wav)
        self._with_tts(fake)
        r = client.get("/api/speak/hola")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "audio/wav")

    def test_no_voice_engine_returns_503(self):
        from voice_processor import NoVoiceAvailableError

        async def fake(text, voice="", speed="normal"):
            raise NoVoiceAvailableError("sin motor")
        self._with_tts(fake)
        self.assertEqual(client.get("/api/speak/hola").status_code, 503)

    def test_online_voices_are_off_by_default(self):
        import voice_processor
        self.assertFalse(voice_processor.TTS_ONLINE)


class SamplesApiTest(unittest.TestCase):
    """Muestras de voz etiquetadas: desactivadas por defecto, con consentimiento y sin datos del paciente."""

    def setUp(self):
        from rehab import settings
        self.settings = settings
        self.dir = Path(_TMP) / "muestras"
        shutil.rmtree(self.dir, ignore_errors=True)
        self.addCleanup(setattr, settings, "EVAL_RECORDING", settings.EVAL_RECORDING)
        self.addCleanup(setattr, settings, "EVAL_AUDIO_DIR", settings.EVAL_AUDIO_DIR)
        settings.EVAL_AUDIO_DIR = self.dir

    def _post(self, **fields):
        data = {"target": "perro", "label": "correct", "consent": "1", "level": "2", **fields}
        return client.post("/api/samples", data=data, files={"audio_file": ("m.webm", b"audio-de-prueba", "audio/webm")})

    def test_disabled_by_default(self):
        self.settings.EVAL_RECORDING = False
        self.assertEqual(self._post().status_code, 403)
        self.assertIn("desactivada", client.get("/samples").text)

    def test_saves_audio_and_manifest_row(self):
        self.settings.EVAL_RECORDING = True
        r = self._post()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["total"], 1)
        r = self._post(label="incorrect", spoken="pero")
        self.assertEqual(r.json(), {"saved": True, "total": 2, "correct": 1, "incorrect": 1})
        rows = list(csv.DictReader(open(self.dir / "manifest.csv", encoding="utf-8")))
        self.assertEqual([(x["target"], x["spoken"], x["label"], x["level"]) for x in rows],
                         [("perro", "perro", "correct", "2"), ("perro", "pero", "incorrect", "2")])
        self.assertEqual((self.dir / rows[0]["file"]).read_bytes(), b"audio-de-prueba")
        # Sin datos del paciente en el manifiesto
        self.assertEqual(list(rows[0]), ["file", "target", "spoken", "label", "kind", "level"])

    def test_requires_consent_and_valid_label(self):
        self.settings.EVAL_RECORDING = True
        self.assertEqual(self._post(consent="").status_code, 400)
        self.assertEqual(self._post(label="regular").status_code, 422)
        self.assertFalse((self.dir / "manifest.csv").exists())


class AacApiTest(unittest.TestCase):
    def test_pictogram_images_exist(self):
        items = {i["id"]: i for i in client.get("/api/aac/config").json()["items"]}
        for pid, image in PICTOGRAM_IMAGES.items():
            with self.subTest(pictogram=pid):
                # Todas las imágenes del mapa existen (algunos pictogramas solo están en bases antiguas)
                self.assertTrue((PROJECT / image.lstrip("/")).exists(), image)
                if pid in items:
                    self.assertEqual(items[pid]["icon_src"], image)
        # Las del seed integrado (comida, bebida, gente) están siempre en una base nueva
        self.assertGreaterEqual(sum(pid in items for pid in PICTOGRAM_IMAGES), 25)


class PictogramLicenseTest(unittest.TestCase):
    def test_arasaac_attribution_and_license(self):
        html = client.get("/communicator").text
        self.assertIn("ARASAAC", html)
        self.assertIn("Sergio Palao", html)
        self.assertIn("CC BY-NC-SA", html)
        self.assertTrue((PROJECT / "static/pictograms/arasaac/LICENSE.txt").exists())

    def test_all_illustrations_are_arasaac(self):
        # Estilo uniforme: todas las ilustraciones son de ARASAAC y no quedan archivos sin usar
        folder = PROJECT / "static/pictograms"
        images = list(PICTOGRAM_IMAGES.values()) + list(WORD_IMAGES.values())
        self.assertTrue(all(img.startswith("/static/pictograms/arasaac/") for img in images))
        on_disk = {p.relative_to(PROJECT).as_posix() for p in folder.rglob("*.webp")}
        used = {img.lstrip("/") for img in images}
        self.assertEqual(on_disk, used)

    def test_practice_words_have_their_image(self):
        # Clave robusta a mayúsculas, tildes y signos; la ñ se conserva
        self.assertEqual(word_image_key("time", "¿Mañana?"), "time/mañana")
        self.assertEqual(word_image_key("animals", "Pingüino"), "animals/pinguino")
        words = [w for cat in client.get("/api/categories").json()["categories"]
                 for level in range(1, 6)
                 for w in client.get(f"/api/words/{cat['id']}?level={level}").json()["words"]]
        with_image = [w for w in words if w.get("image_url")]
        self.assertGreater(len(with_image), len(words) * 0.8)
        self.assertTrue(with_image, "las palabras de práctica deben traer su imagen")
        for w in with_image:
            self.assertEqual(w["image_url"], WORD_IMAGES[word_image_key(w["category_id"], w["word"])])


class IconsTest(unittest.TestCase):
    """El subconjunto de Font Awesome contiene todos los iconos que usa la app."""

    ICON = re.compile(r"\bfa-[a-z0-9]+(?:-[a-z0-9]+)*\b")
    MODIFIERS = {"fa-spin"}

    def test_every_used_icon_is_in_the_subset(self):
        css = (PROJECT / "static/vendor/fontawesome/css/fontawesome.subset.css").read_text(encoding="utf-8")
        defined = set(re.findall(r"\.(fa-[a-z0-9-]+)::?before", css))
        used = set()
        for pattern in ("templates/**/*.html", "static/js/**/*.js"):
            for path in PROJECT.glob(pattern):
                used |= set(self.ICON.findall(path.read_text(encoding="utf-8")))
        aac = client.get("/api/aac/config").json()
        for row in aac["items"] + aac["categories"]:
            used |= set(self.ICON.findall(row.get("icon_src") or row.get("icon") or ""))
        missing = sorted(used - defined - self.MODIFIERS)
        self.assertEqual(missing, [], "Faltan iconos: regenera con tools/build_icons.py")

    def test_hashed_icon_font_is_immutable_and_not_gzipped(self):
        font = next((PROJECT / "static/vendor/fontawesome/webfonts").glob("fa-solid-900.*.woff2"))
        r = client.get(f"/static/vendor/fontawesome/webfonts/{font.name}", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["cache-control"], "public, max-age=31536000, immutable")
        self.assertNotIn("content-encoding", r.headers)


class VoiceApiTest(unittest.TestCase):
    """El motor de voz se sustituye por un doble para no depender de Whisper."""

    def setUp(self):
        self.vp = app_module.voice_processor
        self.saved = {name: getattr(self.vp, name) for name in ("transcribe", "analyze")}
        self.seen_paths = []

        def fake_transcribe(audio_path: str, language: str = "es", initial_prompt: Optional[str] = None) -> str:
            self.seen_paths.append(audio_path)
            return "agua"

        self.alternatives = None

        self.tolerance = None

        def fake_analyze(audio_path: str, target_word: str, level: int = 1, alternatives=None,
                         tolerance_offset: float = 0) -> Dict[str, Any]:
            self.seen_paths.append(audio_path)
            self.alternatives = alternatives
            self.tolerance = tolerance_offset
            return {"transcription": "agua", "target": target_word, "level": level}

        self.vp.transcribe = fake_transcribe
        self.vp.analyze = fake_analyze

    def tearDown(self):
        for name, fn in self.saved.items():
            setattr(self.vp, name, fn)

    def test_transcribe_cleans_up_temp_file(self):
        r = client.post("/api/transcribe", files={"audio_file": ("a.webm", b"fake-audio", "audio/webm")})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"transcription": "agua", "success": True})
        self.assertFalse(os.path.exists(self.seen_paths[0]))

    def test_analyze_clamps_level_and_cleans_up(self):
        r = client.post("/api/analyze-voice",
                        files={"audio_file": ("a.webm", b"fake-audio", "audio/webm")},
                        data={"target_word": "agua", "level": "9"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["level"], 5)
        self.assertFalse(os.path.exists(self.seen_paths[0]))

    def _analyze_with_browser(self, heard):
        return client.post("/api/analyze-voice", files={"audio_file": ("a.webm", b"fake-audio", "audio/webm")},
                           data={"target_word": "agua", "browser_transcripts": heard})

    def test_browser_transcripts_need_patient_consent(self):
        """Lo que oye el navegador (Google) solo se usa si el paciente lo consintió."""
        self.assertEqual(client.post("/api/speech-settings", json={"cloud_speech": False}).json()["cloud_speech"], False)
        self._analyze_with_browser('["agua"]')
        self.assertEqual(self.alternatives, [])

        r = client.post("/api/speech-settings", json={"cloud_speech": True})
        self.assertTrue(r.json()["cloud_speech"])
        self.assertIsNotNone(r.json()["consent_at"])
        self.assertTrue(client.get("/api/speech-settings").json()["cloud_speech"])
        self._analyze_with_browser('["  ", 5, "' + "x" * 500 + '", "agua"]')
        self.assertEqual(self.alternatives, ["x" * 200])   # se limpian, se acotan y solo cuenta la primera
        self._analyze_with_browser("no es json")
        self.assertEqual(self.alternatives, [])

        client.post("/api/speech-settings", json={"cloud_speech": False})
        self.assertIsNone(client.get("/api/speech-settings").json()["consent_at"])

    def test_speech_profile_is_per_patient_and_validated(self):
        c = TestClient(app_module.app)
        login(c, patient_id=None)
        c.post("/patients/new", data={"name": "Paciente Perfil", "next": "/"})
        self.assertEqual(c.get("/api/speech-settings").json()["profile"],
                         {"disorder": "", "severity": "", "max_recording_s": 12, "pause_s": 1.8, "tolerance": 0})
        r = c.post("/api/speech-settings", json={"disorder": "disartria", "max_recording_s": 20, "tolerance": -5})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["profile"]["pause_s"], 1.8)          # lo no enviado se conserva
        self.assertFalse(r.json()["cloud_speech"])                     # y no toca el consentimiento
        c.post("/api/speech-settings", json={"pause_s": 3.5})
        self.assertEqual(c.get("/api/speech-settings").json()["profile"],
                         {"disorder": "disartria", "severity": "", "max_recording_s": 20, "pause_s": 3.5, "tolerance": -5})
        for bad in ({"max_recording_s": 60}, {"pause_s": 0.2}, {"tolerance": 40}, {"disorder": "gripe"}):
            with self.subTest(body=bad):
                self.assertEqual(c.post("/api/speech-settings", json=bad).status_code, 422)
        # La exigencia la lee el servidor del perfil del paciente y la pasa al análisis
        c.post("/api/analyze-voice", files={"audio_file": ("a.webm", b"fake-audio", "audio/webm")}, data={"target_word": "agua"})
        self.assertEqual(self.tolerance, -5)
        # El paciente de la sesión principal no se ve afectado
        self.assertEqual(client.get("/api/speech-settings").json()["profile"]["tolerance"], 0)

    def test_errors_return_500_and_still_clean_up(self):
        def boom(audio_path: str, language: str = "es", initial_prompt: Optional[str] = None) -> str:
            self.seen_paths.append(audio_path)
            raise RuntimeError("fallo simulado")

        self.vp.transcribe = boom
        r = client.post("/api/transcribe", files={"audio_file": ("a.webm", b"x", "audio/webm")})
        self.assertEqual(r.status_code, 500)
        self.assertFalse(os.path.exists(self.seen_paths[0]))


class AnalyzeCombinationTest(unittest.TestCase):
    """analyze() sin pista y combinando lo local con lo que oyó el navegador."""

    def setUp(self):
        self.vp = app_module.voice_processor
        self.saved = self.vp.transcribe_with_retry
        self.prompts = []

        def fake(audio_path, language="es", initial_prompt=None):
            self.prompts.append(initial_prompt)
            return "pero"            # Whisper oye mal la palabra

        self.vp.transcribe_with_retry = fake

    def tearDown(self):
        self.vp.transcribe_with_retry = self.saved

    def test_no_target_hint_is_given_to_whisper(self):
        r = self.vp.analyze("x.webm", "agua")
        self.assertEqual(self.prompts, [None])
        self.assertEqual(r["engine"], "local")
        self.assertFalse(r["is_correct"])

    def test_best_of_browser_and_local(self):
        r = self.vp.analyze("x.webm", "agua", alternatives=["agua"])
        self.assertTrue(r["is_correct"])
        self.assertEqual(r["engine"], "browser")
        self.assertEqual(self.prompts, [])       # el navegador ya oyó la palabra: no hace falta Whisper
        r = self.vp.analyze("x.webm", "perro", alternatives=["gato"])
        self.assertEqual(r["engine"], "local")    # «pero» se parece más a «perro» que «gato»


class ScoringTest(unittest.TestCase):
    """Puntuación sin Whisper: palabras de más, frases y ajuste de exigencia por paciente."""

    def setUp(self):
        self.vp = app_module.voice_processor

    def score(self, heard, target, level=1, tolerance=0):
        return self.vp._score_transcription(heard, target, level, tolerance)

    def test_extra_words_are_not_a_pronunciation_error(self):
        for heard, target in (("agua por favor", "agua"), ("el perro", "perro"), ("sí sí", "sí"),
                              ("quiero agua por favor", "quiero agua"), ("buenos días doctor", "buenos días")):
            with self.subTest(heard=heard):
                r = self.score(heard, target, 1 if " " not in target else 3)
                self.assertTrue(r["is_correct"], r["scores"]["final"])
                self.assertLess(r["scores"]["final"], 100)                 # pequeña penalización
                self.assertEqual(r["transcription"], heard)                # se muestra lo que se oyó

    def test_wrong_or_missing_words_still_fail(self):
        for heard, target in (("pero", "perro"), ("aua", "agua"), ("quiero agua", "quiero agua por favor"),
                              ("necesito ir al baño", "necesito ayuda"),
                              ("gracias a todos por ver el vídeo", "gracias")):  # demasiadas de más
            with self.subTest(heard=heard):
                self.assertFalse(self.score(heard, target, 1 if " " not in target else 3)["is_correct"])

    def test_near_miss_is_casi_not_retry(self):
        r = self.score("pero", "perro")
        self.assertEqual(r["feedback"]["level"], "fair")

    def test_patient_tolerance_moves_threshold(self):
        normal = self.score("pero", "perro")
        tolerant = self.score("pero", "perro", tolerance=-15)
        self.assertEqual(tolerant["scores"]["threshold"], normal["scores"]["threshold"] - 15)
        self.assertFalse(normal["is_correct"])
        self.assertTrue(tolerant["is_correct"])
        self.assertEqual(self.score("perro", "perro", tolerance=40)["scores"]["threshold"],
                         normal["scores"]["threshold"] + 15)             # el ajuste está acotado


if __name__ == "__main__":
    unittest.main()
