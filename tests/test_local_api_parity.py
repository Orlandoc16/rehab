"""El «servidor local» de la app Android (static/js/app/local-api.js, sobre node:sqlite) debe
responder lo mismo que el servidor Python (database.py + game_engine.py + rehab/routers).

Se ejecuta el mismo guion de peticiones en los dos (pacientes, intentos, juegos, valoraciones del
terapeuta, ajustes de voz, errores de validación) y se comparan las respuestas, salvo lo que es
distinto por naturaleza (identificadores y fechas).
Ejecutar:  python -m unittest tests.test_local_api_parity -v   (si no hay Node, se omite)
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

_TMP = tempfile.mkdtemp(prefix="rehab_parity_svc_")
# rehab.routers.speech crea los servicios al importarse: sin Whisper y sin tocar la base real
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_TMP) / 'services.db'}")
os.environ.setdefault("STT_ENGINE", "none")

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))
NODE = shutil.which("node")
JS = [PROJECT / "static" / "js" / f for f in ("scoring.js", "syllables.js", "app/local-api.js")]

VOLATILE = {"id", "created_at", "updated_at", "unlocked_at", "timestamp", "last_practiced", "patient_id",
            "active_patient_id", "consent_at"}


def steps(words, games=("game_match", "game_maze")):
    """Guion de peticiones. "$N" en una ruta = el id devuelto por el paso N."""
    w = [x["id"] for x in words]
    s = [
        ("GET", "/api/progress/default", None),                      # 0: sin paciente -> 409
        ("POST", "/api/app/patients", {"name": "Ana", "age": "71", "diagnosis": "afasia"}),
        ("POST", "/api/app/patients", {"name": "  Bruno  "}),
        ("POST", "/api/app/patients", {"name": ""}),                 # 422
        ("POST", "/api/app/patients/select", {"patient_id": "$1"}),
        ("GET", "/api/categories", None),
        ("GET", "/api/words/basic_needs?level=1", None),
        ("GET", "/api/words/basic_needs?level=0", None),
        ("GET", "/api/words/no_existe", None),
        ("GET", "/api/aac/config", None),
        ("GET", "/api/words/practice/basic_needs?level=1&count=5", None),
        ("GET", "/api/words/practice/food_drink?count=50", None),
        ("GET", "/api/progress/default", None),
        ("GET", "/api/stats/default", None),
        ("GET", "/api/games/level/default", None),
        ("GET", "/api/games/achievements/default", None),
        ("GET", "/api/speech-settings", None),
    ]
    attempts = [
        (w[0], 95, True, 1234.6, {"level": "excellent", "tips": ["¡Bien! ñ"]}),
        (w[0], 40, False, 900, None),
        (w[0], 55.55, None, None, {"score": 55.55}),
        (w[1], 72.5, True, 2000, None),
        (w[1], 130, None, 10, None),            # se acota a 100
        (w[2], 30, False, None, None),
        (w[2], 20, False, None, None),
        (w[2], 66, None, None, None),
        (w[3], 0, False, 0, None),
        (games[0], 80, None, 45000, {"game": "match"}),
        (games[1], 100, None, None, None),
    ]
    first_attempt = len(s)
    for word_id, score, ok, dur, fb in attempts:
        body = {"word_id": word_id, "score": score, "attempt_number": 1, "transcription": "algo  ",
                "patient_id": "otro"}
        if ok is not None:
            body["is_correct"] = ok
        if dur is not None:
            body["duration_ms"] = dur
        if fb is not None:
            body["feedback"] = fb
        s.append(("POST", "/api/progress", body))
    s += [
        ("POST", "/api/progress", {"word_id": w[0], "score": -1}),           # 422
        ("POST", "/api/progress", {"score": 50}),                            # 422
        ("POST", f"/api/progress/${first_attempt + 1}/label", {"correct": True}),
        ("POST", f"/api/progress/${first_attempt + 5}/label", {"correct": False}),
        ("POST", f"/api/progress/${first_attempt + 6}/label", {"correct": None}),
        ("POST", f"/api/progress/${first_attempt + 9}/label", {"correct": True}),   # juego -> 404
        ("POST", "/api/progress/no-existe/label", {"correct": True}),              # 404
        ("GET", "/api/progress/default", None),
        ("GET", "/api/stats/default", None),
        ("GET", "/api/words/practice/basic_needs?level=1&count=5", None),
        ("GET", "/api/words/practice/basic_needs?count=3", None),
        ("GET", "/api/words/difficult/default", None),
        ("GET", "/api/words/difficult/default?limit=1", None),
        ("GET", "/api/words/review/default", None),
        ("GET", "/api/words/review/default?limit=2", None),
        # Comunicador a medida: pictogramas ocultos y frases propias
        ("GET", "/api/aac/profile", None),
        ("POST", "/api/aac/profile", {"hidden": ["walk", " rest ", "walk", ""], "phrases": ["  Quiero ver a Lucía ", "Café con leche"]}),
        ("POST", "/api/aac/profile", {"phrases": ["Solo esta", "Solo esta"]}),      # hidden se conserva
        ("POST", "/api/aac/profile", {"phrases": "no es una lista"}),              # 422
        ("POST", "/api/aac/profile", {"phrases": ["x" * 121]}),                    # 422
        ("POST", "/api/aac/profile", {"hidden": [1, 2]}),                          # 422
        ("POST", "/api/aac/profile", {"phrases": [f"frase {i}" for i in range(41)]}),   # 422
        ("GET", "/api/aac/profile", None),
        ("GET", "/api/games/level/default", None),
        ("GET", "/api/games/achievements/default", None),
        ("POST", "/api/speech-settings", {"disorder": "afasia", "tolerance": -5, "pause_s": 2.5}),
        ("POST", "/api/speech-settings", {"tolerance": 99}),                 # 422
        ("POST", "/api/speech-settings", {"severity": "grave", "max_recording_s": 20, "slow_voice": False}),
        ("POST", "/api/speech-settings", {"slow_voice": "no"}),              # 422
        ("GET", "/api/speech-settings", None),
        ("POST", "/api/app/patients/select", {"patient_id": "$2"}),
        ("GET", "/api/progress/default", None),
        ("GET", "/api/stats/default", None),
        ("GET", "/api/games/level/default", None),
        ("GET", "/api/speech-settings", None),
        ("GET", "/api/app/patients", None),
    ]
    # Ficha del paciente: editar y borrar (el paciente activo, $2, tiene intentos, puntos y logros)
    s += [
        ("POST", "/api/app/patients/$1", {"name": " Ana María ", "age": "72", "notes": "Prefiere la tarde"}),
        ("POST", "/api/app/patients/$1", {"name": "", "age": "72"}),          # 422
        ("POST", "/api/app/patients/$1", {"name": "Ana", "age": "200"}),       # 422
        ("POST", "/api/app/patients/no-existe", {"name": "Nadie"}),           # 404
        ("GET", "/api/app/patients", None),
        ("POST", "/api/app/patients/$2/delete", None),
        ("POST", "/api/app/patients/$2/delete", None),                         # 404: ya no existe
        ("GET", "/api/app/patients", None),
        ("GET", "/api/progress/default", None),                                # sin paciente activo -> 409
        ("POST", "/api/app/patients/select", {"patient_id": "$1"}),
        ("GET", "/api/progress/default", None),
    ]
    return s


# ------------------------------------------------------------------- lado Python

class PythonServer:
    """Las mismas rutas que rehab/routers, sobre una base SQLite temporal propia."""

    def __init__(self, url):
        old = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        try:
            from database import Database
            from game_engine import GameEngine
            self.db = Database()
            self.db.initialize()
            self.games = GameEngine()
        finally:
            if old is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old
        self.patient = None

    def call(self, method, path, body):
        from pydantic import ValidationError
        from rehab.schemas import AacProfile, PatientCreate, ProgressCreate, TherapistLabel
        from rehab.routers.speech import SpeechSettings
        u = urlparse(path)
        q = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
        p = u.path
        db, ge = self.db, self.games
        try:
            if p == "/api/app/patients" and method == "POST":
                data = PatientCreate(**{**body, "age": body.get("age") or None})
                self.patient = db.register_patient(data.model_dump())
                return 200, {"patient_id": self.patient, "success": True}
            if p.startswith("/api/app/patients/") and p.endswith("/delete"):
                target = p.split("/")[4]
                if not db.delete_patient(target):
                    return 404, {"detail": "Paciente no encontrado"}
                if self.patient == target:
                    self.patient = None
                return 200, {"success": True}
            if p.startswith("/api/app/patients/") and p != "/api/app/patients/select":
                data = PatientCreate(**{**body, "age": body.get("age") or None})
                if not db.update_patient(p.split("/")[4], data.model_dump(exclude={"therapist"})):
                    return 404, {"detail": "Paciente no encontrado"}
                return 200, {"success": True}
            if p == "/api/app/patients/select":
                self.patient = body["patient_id"]
                return 200, {"success": True, "patient_id": self.patient}
            if p == "/api/app/patients":
                # La app no crea el «Paciente Demo» que siembra el servidor
                patients = [x for x in db.list_patients() if x["id"] != "default"]
                return 200, {"patients": patients, "active_patient_id": self.patient}
            if p == "/api/categories":
                return 200, {"categories": db.get_categories()}
            if p == "/api/aac/config":
                return 200, db.get_aac_config()
            if p == "/api/games/daily-challenge":
                return 200, ge.get_daily_challenge()
            if p.startswith("/api/words/") and not p.startswith(("/api/words/practice/", "/api/words/difficult/",
                                                                 "/api/words/review/")):
                cat, level = unquote(p.split("/")[3]), int(q.get("level", 1))
                return 200, {"words": db.get_words(cat, level), "category": cat, "level": level}
            if self.patient is None:
                return 409, {"detail": "Elige un paciente"}
            pid = self.patient
            if p.startswith("/api/words/practice/"):
                cat = unquote(p.split("/")[4])
                level = int(q["level"]) if q.get("level") else None
                words = db.get_words_for_practice(pid, cat, level, int(q.get("count", 10)))
                return 200, {"words": words, "category": cat, "level": level, "patient_id": pid,
                             "method": "spaced_repetition"}
            if p.startswith("/api/words/review/"):
                words = db.get_review_words(pid, int(q.get("limit", 20)))
                return 200, {"words": words, "patient_id": pid, "count": len(words)}
            if p == "/api/aac/profile":
                if method == "POST":
                    return 200, db.set_aac_profile(pid, AacProfile(**body).model_dump())
                return 200, db.get_aac_profile(pid)
            if p.startswith("/api/words/difficult/"):
                words = db.get_difficult_words(pid, int(q.get("limit", 10)))
                return 200, {"words": words, "patient_id": pid, "count": len(words)}
            if p.startswith("/api/progress/") and p.endswith("/label"):
                label = TherapistLabel(**body)
                pr_id = unquote(p.split("/")[3])
                if not db.set_therapist_label(pid, pr_id, label.correct):
                    return 404, {"detail": "Intento no encontrado"}
                return 200, {"success": True, "id": pr_id, "correct": label.correct}
            if p.startswith("/api/progress/"):
                return 200, db.get_progress(pid)
            if p == "/api/progress":
                record = ProgressCreate(**body).as_record(pid)
                progress_id = db.save_progress(record)
                points = ge.calculate_points(record)
                return 200, {"success": True, "id": progress_id, "points_earned": points,
                             "total_points": db.get_total_points(pid)}
            if p.startswith("/api/stats/"):
                return 200, db.get_detailed_stats(pid)
            if p.startswith("/api/games/level/"):
                return 200, ge.get_player_level(pid)
            if p.startswith("/api/games/achievements/"):
                return 200, ge.get_achievements(pid)
            if p == "/api/speech-settings":
                if method == "POST":
                    s = SpeechSettings(**body)
                    profile = s.model_dump(exclude_none=True, exclude={"cloud_speech"})
                    if profile:
                        db.set_speech_profile(pid, profile)
                consent = db.get_cloud_speech_consent(pid)
                return 200, {"cloud_speech": consent is not None, "consent_at": None,
                             "profile": db.get_speech_profile(pid)}
        except ValidationError:
            return 422, {"detail": "validación"}
        raise AssertionError(f"ruta sin traducir en el test: {method} {path}")


def resolve(path, ids):
    for n in sorted(ids, key=lambda k: -len(str(k))):
        path = path.replace(f"${n}", str(ids[n]))
    return path


def run_python(server, script):
    from fastapi.encoders import jsonable_encoder
    out, ids = [], {}
    for i, (method, path, body) in enumerate(script):
        if isinstance(body, dict):
            body = {k: (ids[int(v[1:])] if isinstance(v, str) and v.startswith("$") else v) for k, v in body.items()}
        status, resp = server.call(method, resolve(path, ids), body)
        resp = json.loads(json.dumps(jsonable_encoder(resp)))
        if isinstance(resp, dict):
            ids[i] = resp.get("id") or resp.get("patient_id")
        out.append({"status": status, "body": resp})
    return out


# ------------------------------------------------------------------- lado JavaScript

NODE_RUNNER = r"""
const fs = require('fs'), vm = require('vm');
const { DatabaseSync } = require('node:sqlite');
const ctx = { URL, URLSearchParams, crypto, console };
vm.createContext(ctx);
for (const f of JSON.parse(process.argv[1])) vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
let input = '';
process.stdin.setEncoding('utf8').on('data', (c) => (input += c)).on('end', async () => {
    const { content, script, dbPath } = JSON.parse(input);
    const sqlite = new DatabaseSync(dbPath);
    const db = {
        all: (sql, params = []) => sqlite.prepare(sql).all(...params),
        run: (sql, params = []) => sqlite.prepare(sql).run(...params),
    };
    const api = ctx.RehabLocalApi.create({ db });
    api.init(content);
    api.init(content);   // idempotente
    const out = [], ids = {};
    const resolve = (p) => Object.keys(ids).sort((a, b) => b.length - a.length).reduce((s, n) => s.split('$' + n).join(ids[n]), p);
    for (let i = 0; i < script.length; i++) {
        let [method, path, body] = script[i];
        if (body && typeof body === 'object') {
            body = Object.fromEntries(Object.entries(body).map(([k, v]) => [k, typeof v === 'string' && v.startsWith('$') ? ids[v.slice(1)] : v]));
        }
        const r = await api.handle(method, resolve(path), body);
        if (r.body && typeof r.body === 'object') ids[i] = r.body.id || r.body.patient_id;
        out.push(r);
    }
    process.stdout.write(JSON.stringify(out));
});
"""


def normalize(value, key=None):
    if key in VOLATILE:
        return "<volátil>" if value is not None else None
    if key in ("feedback", "achievement_data") and isinstance(value, str):
        try:
            return normalize(json.loads(value))
        except ValueError:
            return value
    if isinstance(value, dict):
        return {k: normalize(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


@unittest.skipUnless(NODE, "Node.js no está instalado")
class LocalApiParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from export_app_content import export_content
        cls.tmp = tempfile.mkdtemp(prefix="rehab_parity_")
        cls.py = PythonServer(f"sqlite:///{Path(cls.tmp) / 'py.db'}")
        cls.content = export_content(cls.py.db.engine)

    @classmethod
    def tearDownClass(cls):
        cls.py.db.engine.dispose()
        cls.py.games.db.engine.dispose()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def assert_same(self, py, js, path):
        if isinstance(py, bool) or isinstance(js, bool):
            self.assertEqual(py, js, path)
        elif isinstance(py, (int, float)) and isinstance(js, (int, float)):
            self.assertTrue(math.isclose(py, js, rel_tol=1e-9, abs_tol=1e-9), f"{path}: {py} != {js}")
        elif isinstance(py, dict) and isinstance(js, dict):
            self.assertEqual(sorted(py), sorted(js), f"{path}: claves distintas")
            for k in py:
                self.assert_same(py[k], js[k], f"{path}.{k}")
        elif isinstance(py, list) and isinstance(js, list):
            self.assertEqual(len(py), len(js), f"{path}: longitud distinta")
            for i, (a, b) in enumerate(zip(py, js)):
                self.assert_same(a, b, f"{path}[{i}]")
        else:
            self.assertEqual(py, js, path)

    def test_same_responses(self):
        words = [w for w in self.content["words"] if w["category_id"] == "basic_needs" and w["level"] == 1]
        self.assertGreaterEqual(len(words), 4)
        script = steps(words)
        py = run_python(self.py, script)
        res = subprocess.run(
            [NODE, "-e", NODE_RUNNER, json.dumps([str(f) for f in JS])],
            input=json.dumps({"content": self.content, "script": script,
                              "dbPath": str(Path(self.tmp) / "js.db")}).encode("utf-8"),
            capture_output=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stderr.decode("utf-8", "replace"))
        js = json.loads(res.stdout.decode("utf-8"))
        self.assertEqual(len(py), len(js))
        for i, ((method, path, _), a, b) in enumerate(zip(script, py, js)):
            with self.subTest(paso=i, peticion=f"{method} {path}"):
                self.assertEqual(a["status"], b["status"], f"código HTTP (JS: {b['body']})")
                if a["status"] == 200:
                    self.assert_same(normalize(a["body"]), normalize(b["body"]), "respuesta")


if __name__ == "__main__":
    unittest.main()
