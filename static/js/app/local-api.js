// @ts-check
/**
 * «Servidor local» de la app Android sin servidor: responde a las mismas rutas /api/... que
 * FastAPI (rehab/routers/*), con las mismas respuestas, sobre una base SQLite del dispositivo
 * con el mismo esquema que database.py. Así las páginas funcionan sin cambios.
 *
 * Traduce database.py y game_engine.py. tests/test_local_api_parity.py ejecuta los mismos
 * escenarios aquí (Node + node:sqlite) y en Python y exige el mismo resultado.
 *
 * Uso:
 *   const api = RehabLocalApi.create({ db, recognizer, now });
 *   api.init(content);                       // crea tablas y carga el contenido (palabras, pictogramas)
 *   const { status, body } = await api.handle('GET', '/api/categories?x=1', null);
 *
 * db: { all(sql, params) -> filas (objetos), run(sql, params) }  (síncrono)
 * recognizer (opcional): { transcribe(audioBlob, { prompt, retry }) -> Promise<string> }
 * Script clásico: expone el global `RehabLocalApi`. Necesita RehabScoring y RehabSyllables.
 */
var RehabLocalApi = (function () {
    'use strict';

    const GAME_PREFIX = 'game_';
    const SPEECH_PROFILE_DEFAULTS = { disorder: '', severity: '', max_recording_s: 12, pause_s: 1.8, tolerance: 0, slow_voice: true };
    const DISORDERS = ['', 'afasia', 'disartria', 'apraxia', 'mixto', 'otro'];
    const SEVERITIES = ['', 'leve', 'moderada', 'grave'];
    const SCHEMA_VERSION = 1;

    const ACHIEVEMENTS = {
        first_word: { name: 'Primera Palabra', description: 'Completaste tu primera palabra correctamente', icon: '🌟', points: 10 },
        perfect_10: { name: 'Perfecto 10', description: '10 palabras perfectas seguidas', icon: '🎯', points: 50 },
        category_master: { name: 'Maestro de Categoría', description: 'Completaste todas las palabras de una categoría', icon: '🏆', points: 100 },
        daily_streak_3: { name: 'Racha de 3 días', description: 'Practicaste 3 días seguidos', icon: '🔥', points: 30 },
        daily_streak_7: { name: 'Racha de 7 días', description: 'Practicaste una semana completa', icon: '💪', points: 70 },
        daily_streak_30: { name: 'Racha de 30 días', description: '¡Un mes completo de práctica!', icon: '👑', points: 300 },
        level_up: { name: 'Subir de Nivel', description: 'Avanzaste al siguiente nivel', icon: '⬆️', points: 25 },
        phrase_master: { name: 'Maestro de Frases', description: 'Completaste 10 frases correctamente', icon: '💬', points: 80 },
        speed_demon: { name: 'Velocista', description: 'Completaste 5 palabras en menos de 1 minuto', icon: '⚡', points: 40 },
        comeback_kid: { name: 'Nunca Rendirse', description: 'Mejoraste una palabra difícil después de 5 intentos', icon: '🦸', points: 60 },
        explorer: { name: 'Explorador', description: 'Probaste todas las categorías', icon: '🗺️', points: 50 },
        night_owl: { name: 'Búho Nocturno', description: 'Practicaste después de las 10pm', icon: '🦉', points: 15 },
        early_bird: { name: 'Madrugador', description: 'Practicaste antes de las 7am', icon: '🐦', points: 15 },
        century: { name: 'Centenario', description: '100 palabras completadas', icon: '💯', points: 100 },
        thousand: { name: 'Mil Palabras', description: '1000 intentos realizados', icon: '🎉', points: 200 },
    };

    const DAILY_CHALLENGES = [
        { type: 'complete_words', title: 'Palabras del Día', description: 'Completa {count} palabras hoy', count: 10, points: 20 },
        { type: 'perfect_score', title: 'Perfección', description: 'Consigue {count} puntuaciones perfectas (>90%)', count: 5, points: 30 },
        { type: 'category_focus', title: 'Enfoque', description: "Practica {count} palabras de la categoría '{category}'", count: 8, category: null, points: 25 },
        { type: 'level_challenge', title: 'Desafío de Nivel', description: 'Completa {count} palabras del nivel {level}', count: 5, level: null, points: 35 },
        { type: 'time_challenge', title: 'Contra Reloj', description: 'Completa {count} palabras en menos de 5 minutos', count: 8, points: 40 },
    ];

    const LEVELS = [
        [0, 'Principiante', '🌱'], [100, 'Aprendiz', '🌿'], [300, 'Practicante', '🌳'], [600, 'Avanzado', '⭐'],
        [1000, 'Experto', '🌟'], [1500, 'Maestro', '💫'], [2500, 'Gran Maestro', '👑'], [5000, 'Leyenda', '🏆'],
    ];

    const SCHEMA = [
        `CREATE TABLE IF NOT EXISTS patients (id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, age INTEGER,
            diagnosis VARCHAR, therapist VARCHAR, notes TEXT, cloud_speech_consent_at DATETIME, speech_profile TEXT,
            aac_profile TEXT, created_at DATETIME, updated_at DATETIME)`,
        `CREATE TABLE IF NOT EXISTS categories (id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, description VARCHAR,
            icon VARCHAR, color VARCHAR, order_num INTEGER)`,
        `CREATE TABLE IF NOT EXISTS words (id VARCHAR PRIMARY KEY, word VARCHAR NOT NULL, category_id VARCHAR,
            level INTEGER, phonetic_hint VARCHAR, image_url VARCHAR, audio_url VARCHAR, tips TEXT, created_at DATETIME)`,
        `CREATE INDEX IF NOT EXISTS ix_words_category_level ON words (category_id, level)`,
        `CREATE TABLE IF NOT EXISTS progress (id VARCHAR PRIMARY KEY, patient_id VARCHAR NOT NULL, word_id VARCHAR NOT NULL,
            attempt_number INTEGER, score FLOAT, transcription TEXT, feedback TEXT, duration_ms INTEGER,
            auto_correct BOOLEAN, therapist_correct BOOLEAN, created_at DATETIME)`,
        `CREATE INDEX IF NOT EXISTS ix_progress_patient_word ON progress (patient_id, word_id)`,
        `CREATE INDEX IF NOT EXISTS ix_progress_patient_created ON progress (patient_id, created_at)`,
        `CREATE TABLE IF NOT EXISTS achievements (id VARCHAR PRIMARY KEY, patient_id VARCHAR NOT NULL,
            achievement_type VARCHAR NOT NULL, achievement_data TEXT, unlocked_at DATETIME)`,
        `CREATE INDEX IF NOT EXISTS ix_achievements_patient ON achievements (patient_id)`,
        `CREATE TABLE IF NOT EXISTS points (id VARCHAR PRIMARY KEY, patient_id VARCHAR NOT NULL, points INTEGER NOT NULL,
            reason VARCHAR, created_at DATETIME)`,
        `CREATE INDEX IF NOT EXISTS ix_points_patient ON points (patient_id)`,
        `CREATE TABLE IF NOT EXISTS aac_categories (id VARCHAR PRIMARY KEY, label VARCHAR NOT NULL, color VARCHAR,
            icon VARCHAR, order_num INTEGER)`,
        `CREATE TABLE IF NOT EXISTS aac_pictograms (id VARCHAR PRIMARY KEY, category_id VARCHAR, label VARCHAR NOT NULL,
            icon_src VARCHAR, grammar TEXT, default_phrase VARCHAR)`,
        // Solo de la app: paciente activo, versión del contenido...
        `CREATE TABLE IF NOT EXISTS app_state (key VARCHAR PRIMARY KEY, value TEXT)`,
    ];

    const COLUMNS = {
        patients: ['id', 'name', 'age', 'diagnosis', 'therapist', 'notes', 'cloud_speech_consent_at', 'speech_profile', 'aac_profile', 'created_at', 'updated_at'],
        categories: ['id', 'name', 'description', 'icon', 'color', 'order_num'],
        words: ['id', 'word', 'category_id', 'level', 'phonetic_hint', 'image_url', 'audio_url', 'tips', 'created_at'],
        progress: ['id', 'patient_id', 'word_id', 'attempt_number', 'score', 'transcription', 'feedback', 'duration_ms', 'auto_correct', 'therapist_correct', 'created_at'],
        achievements: ['id', 'patient_id', 'achievement_type', 'achievement_data', 'unlocked_at'],
        aac_categories: ['id', 'label', 'color', 'icon', 'order_num'],
        aac_pictograms: ['id', 'category_id', 'label', 'icon_src', 'grammar', 'default_phrase'],
    };
    const DATETIME_COLS = new Set(['created_at', 'updated_at', 'unlocked_at', 'cloud_speech_consent_at']);
    const BOOL_COLS = new Set(['auto_correct', 'therapist_correct']);
    const FLOAT_COLS = new Set(['score']);

    // ---------------------------------------------------------------- utilidades «como Python»

    class HttpError extends Error {
        /** @param {number} status @param {any} detail */
        constructor(status, detail) { super(String(detail)); this.status = status; this.detail = detail; }
    }

    /** round(x, n) de Python: redondeo al par sobre el valor binario exacto. */
    function pyRound(x, n = 0) {
        if (x === null || x === undefined || !Number.isFinite(x)) return x;
        const neg = x < 0;
        const s = Math.abs(x).toFixed(100);              // decimal exacto del double
        const [ip, fp] = s.split('.');
        const keep = fp.slice(0, n), rest = fp.slice(n);
        let digits = BigInt(ip + keep);
        const first = rest.charCodeAt(0) - 48;
        const tail = /[1-9]/.test(rest.slice(1));
        if (first > 5 || (first === 5 && (tail || digits % 2n === 1n))) digits += 1n;
        let str = digits.toString().padStart(n + 1, '0');
        const val = Number(n ? `${str.slice(0, -n)}.${str.slice(-n)}` : str);
        return neg ? -val : val;
    }

    /** json.dumps de Python (separadores ", " ": " y ensure_ascii) para lo que se guarda en texto. */
    function pyJsonDumps(value) {
        const ascii = (/** @type {string} */ s) => s.replace(/[\u007f-￿]/g, (c) => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
        const enc = (v) => {
            if (v === null || v === undefined) return 'null';
            if (typeof v === 'boolean') return v ? 'true' : 'false';
            if (typeof v === 'number') return Number.isInteger(v) && !Object.is(v, -0) ? String(v) : String(v);
            if (typeof v === 'string') return ascii(JSON.stringify(v));
            if (Array.isArray(v)) return '[' + v.map(enc).join(', ') + ']';
            return '{' + Object.keys(v).map((k) => ascii(JSON.stringify(k)) + ': ' + enc(v[k])).join(', ') + '}';
        };
        return enc(value);
    }

    const shortUuid = () => {
        const c = globalThis.crypto;
        if (c && typeof c.randomUUID === 'function') return c.randomUUID().slice(0, 8);
        return Math.random().toString(16).slice(2, 10).padEnd(8, '0');
    };

    /** Fecha UTC «naive» como la guarda SQLAlchemy en SQLite: 'YYYY-MM-DD HH:MM:SS.ffffff'. */
    function dbTimestamp(d) {
        const p = (/** @type {number} */ n, w = 2) => String(n).padStart(w, '0');
        return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ` +
            `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}.${p(d.getUTCMilliseconds(), 3)}000`;
    }

    /** datetime.isoformat() de lo guardado (sin fracción si los microsegundos son 0). */
    function isoFromDb(v) {
        if (v === null || v === undefined || v === '') return null;
        let s = String(v).replace(' ', 'T');
        s = s.replace(/\.0+$/, '');
        return s;
    }

    /** Milisegundos UTC de una fecha guardada. */
    function msFromDb(v) {
        const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?/);
        if (!m) return NaN;
        const frac = (m[7] || '0').padEnd(6, '0').slice(0, 6);
        return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) + Number(frac) / 1000;
    }

    const localDate = (/** @type {Date} */ d) =>
        `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

    function isAttemptCorrect(score, autoCorrect, therapistCorrect) {
        if (therapistCorrect !== null && therapistCorrect !== undefined) return Boolean(therapistCorrect);
        if (autoCorrect !== null && autoCorrect !== undefined) return Boolean(autoCorrect);
        return (score || 0) >= 70;
    }
    const CORRECT_SQL = `CASE WHEN therapist_correct IS NOT NULL THEN therapist_correct
        WHEN auto_correct IS NOT NULL THEN auto_correct ELSE score >= 70 END`;
    const NOT_GAME = `word_id NOT LIKE '${GAME_PREFIX}%'`;

    /** Fila de SQLite -> dict como Database._to_dict + jsonable_encoder. */
    function toDict(table, row) {
        /** @type {Record<string, any>} */
        const out = {};
        for (const c of COLUMNS[table]) {
            let v = row[c];
            if (v === undefined) v = null;
            if (v !== null && DATETIME_COLS.has(c)) v = isoFromDb(v);
            else if (v !== null && BOOL_COLS.has(c)) v = Boolean(v);
            else if (v !== null && FLOAT_COLS.has(c)) v = Number(v);
            out[c] = v;
        }
        return out;
    }

    /** Generador pseudoaleatorio con semilla (el desafío del día es el mismo todo el día). */
    function seededRandom(seedText) {
        let h = 1779033703 ^ seedText.length;
        for (let i = 0; i < seedText.length; i++) {
            h = Math.imul(h ^ seedText.charCodeAt(i), 3432918353);
            h = (h << 13) | (h >>> 19);
        }
        let a = h >>> 0;
        return () => {
            a = (a + 0x6D2B79F5) | 0;
            let t = Math.imul(a ^ (a >>> 15), 1 | a);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    }

    // ---------------------------------------------------------------- validación (pydantic)

    const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
    const err422 = (msg) => new HttpError(422, [{ msg }]);
    const str = (v) => (typeof v === 'string' ? v.trim() : v);

    function validateProgress(body) {
        if (!isObj(body)) throw err422('cuerpo no válido');
        const wordId = str(body.word_id);
        if (typeof wordId !== 'string' || wordId.length < 1 || wordId.length > 64) throw err422('word_id');
        const score = typeof body.score === 'string' && body.score.trim() !== '' ? Number(body.score) : body.score;
        if (typeof score !== 'number' || !Number.isFinite(score) || score < 0) throw err422('score');
        /** @type {Record<string, any>} */
        const rec = { word_id: wordId, score: Math.min(score, 100), attempt_number: 1, transcription: '' };
        if (body.attempt_number !== undefined && body.attempt_number !== null) {
            const a = body.attempt_number;
            if (!Number.isInteger(a) || a < 1 || a > 10000) throw err422('attempt_number');
            rec.attempt_number = a;
        }
        if (body.transcription !== undefined && body.transcription !== null) {
            const t = str(body.transcription);
            if (typeof t !== 'string' || t.length > 500) throw err422('transcription');
            rec.transcription = t;
        }
        if (body.feedback !== undefined && body.feedback !== null) {
            if (!isObj(body.feedback)) throw err422('feedback');
            rec.feedback = body.feedback;
        }
        if (body.duration_ms !== undefined && body.duration_ms !== null) {
            const d = body.duration_ms;
            if (typeof d !== 'number' || d < 0 || d > 3600000) throw err422('duration_ms');
            rec.duration_ms = pyRound(d);
        }
        if (body.is_correct !== undefined && body.is_correct !== null) {
            if (typeof body.is_correct !== 'boolean') throw err422('is_correct');
            rec.is_correct = body.is_correct;
        }
        return rec;
    }

    function validateSpeechSettings(body) {
        if (!isObj(body)) throw err422('cuerpo no válido');
        /** @type {Record<string, any>} */
        const out = {};
        if (body.cloud_speech !== undefined && body.cloud_speech !== null) {
            if (typeof body.cloud_speech !== 'boolean') throw err422('cloud_speech');
            out.cloud_speech = body.cloud_speech;
        }
        const pick = (key, ok) => {
            if (body[key] === undefined || body[key] === null) return;
            if (!ok(body[key])) throw err422(key);
            out[key] = body[key];
        };
        pick('disorder', (v) => DISORDERS.includes(v));
        pick('severity', (v) => SEVERITIES.includes(v));
        pick('max_recording_s', (v) => Number.isInteger(v) && v >= 5 && v <= 30);
        pick('pause_s', (v) => typeof v === 'number' && v >= 1 && v <= 5);
        pick('tolerance', (v) => Number.isInteger(v) && v >= -15 && v <= 15);
        pick('slow_voice', (v) => typeof v === 'boolean');
        return out;
    }

    // ---------------------------------------------------------------- la API

    /**
     * @param {{ db: { all: (sql: string, params?: any[]) => any[], run: (sql: string, params?: any[]) => any },
     *           recognizer?: { transcribe: (audio: any, opts: { prompt?: string|null }) => Promise<string> },
     *           now?: () => Date }} deps
     */
    function create(deps) {
        const { db } = deps;
        const now = deps.now || (() => new Date());
        // Marcas de tiempo estrictamente crecientes (dos intentos en el mismo milisegundo no empatan)
        let lastStamp = '';
        let seq = 0;
        const stamp = () => {
            const base = dbTimestamp(now()).slice(0, -3);
            seq = base === lastStamp ? seq + 1 : 0;
            lastStamp = base;
            return base + String(Math.min(seq, 999)).padStart(3, '0');
        };
        const all = (sql, params = []) => db.all(sql, params);
        const one = (sql, params = []) => db.all(sql, params)[0];
        const run = (sql, params = []) => db.run(sql, params);

        // ---- estado de la app (paciente activo)
        const getState = (key) => { const r = one('SELECT value FROM app_state WHERE key = ?', [key]); return r ? r.value : null; };
        const setState = (key, value) => run('INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)', [key, value]);

        function currentPatient() {
            const id = getState('patient_id');
            if (!id || !one('SELECT id FROM patients WHERE id = ?', [id])) throw new HttpError(409, 'Elige un paciente');
            return id;
        }

        /** Crea las tablas y carga/actualiza el contenido (categorías, palabras, comunicador). */
        function init(content) {
            for (const s of SCHEMA) run(s);
            // Columnas añadidas después: las instalaciones anteriores no las tienen
            if (!all('PRAGMA table_info(patients)').some((c) => c.name === 'aac_profile')) {
                run('ALTER TABLE patients ADD COLUMN aac_profile TEXT');
            }
            if (!content) return;
            if (getState('content_version') === String(content.version)) return;
            const upsert = (table, rows) => {
                const cols = COLUMNS[table];
                const sql = `INSERT OR REPLACE INTO ${table} (${cols.join(', ')}) VALUES (${cols.map(() => '?').join(', ')})`;
                for (const r of rows) run(sql, cols.map((c) => (r[c] === undefined ? null : r[c])));
            };
            run('BEGIN');
            try {
                upsert('categories', content.categories || []);
                upsert('words', content.words || []);
                // El comunicador se sustituye entero (no tiene datos del paciente)
                run('DELETE FROM aac_categories');
                run('DELETE FROM aac_pictograms');
                upsert('aac_categories', content.aac_categories || []);
                upsert('aac_pictograms', content.aac_pictograms || []);
                setState('content_version', String(content.version));
                setState('schema_version', String(SCHEMA_VERSION));
                run('COMMIT');
            } catch (e) {
                run('ROLLBACK');
                throw e;
            }
        }

        // ---- database.py

        const getCategories = () => all('SELECT * FROM categories ORDER BY order_num').map((r) => toDict('categories', r));

        function getWords(categoryId, level) {
            const rows = level
                ? all('SELECT * FROM words WHERE category_id = ? AND level = ? ORDER BY level, word', [categoryId, level])
                : all('SELECT * FROM words WHERE category_id = ? ORDER BY level, word', [categoryId]);
            return rows.map((r) => toDict('words', r));
        }

        function addWord(data) {
            const id = shortUuid();
            const word = data.word;
            const categoryId = data.category_id || 'custom';
            run(`INSERT INTO words (id, word, category_id, level, phonetic_hint, image_url, tips, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
                [id, word, categoryId, data.level || 1, data.phonetic_hint || RehabSyllables.syllabify(word || ''),
                    null, data.tips || '', stamp()]);
            return id;
        }

        function saveProgress(rec) {
            const id = shortUuid();
            run(`INSERT INTO progress (id, patient_id, word_id, attempt_number, score, transcription, feedback,
                 duration_ms, auto_correct, therapist_correct, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)`,
                [id, rec.patient_id, rec.word_id, rec.attempt_number ?? 1, rec.score ?? null, rec.transcription ?? null,
                    pyJsonDumps(rec.feedback ?? {}), rec.duration_ms ?? null,
                    rec.is_correct === undefined || rec.is_correct === null ? null : (rec.is_correct ? 1 : 0),
                    stamp()]);
            return id;
        }

        function getProgress(patientId) {
            const t = one(`SELECT COUNT(id) AS n, COUNT(DISTINCT word_id) AS u, AVG(score) AS a, MAX(score) AS m,
                           SUM(CASE WHEN (${CORRECT_SQL}) THEN 1 ELSE 0 END) AS c
                           FROM progress WHERE patient_id = ? AND ${NOT_GAME}`, [patientId]);
            const total = t.n || 0, correct = t.c || 0;
            const practiced = new Map(all(
                `SELECT w.category_id AS c, COUNT(DISTINCT p.word_id) AS n, AVG(p.score) AS a
                 FROM progress p JOIN words w ON p.word_id = w.id
                 WHERE p.patient_id = ? AND p.${NOT_GAME} GROUP BY w.category_id`, [patientId]).map((r) => [r.c, r]));
            const totals = new Map(all('SELECT category_id AS c, COUNT(id) AS n FROM words GROUP BY category_id').map((r) => [r.c, r.n]));
            const byCategory = all('SELECT * FROM categories ORDER BY order_num').map((cat) => {
                const p = practiced.get(cat.id);
                return {
                    id: cat.id, name: cat.name, icon: cat.icon,
                    words_practiced: p ? p.n : 0,
                    avg_score: pyRound((p && p.a) || 0, 1),
                    total_words: totals.get(cat.id) || 0,
                };
            });
            const recent = all(
                `SELECT p.*, w.word AS _word FROM progress p LEFT OUTER JOIN words w ON p.word_id = w.id
                 WHERE p.patient_id = ? AND p.${NOT_GAME} ORDER BY p.created_at DESC LIMIT 20`, [patientId])
                .map((r) => {
                    const d = toDict('progress', r);
                    return {
                        ...d,
                        word: r._word !== null && r._word !== undefined ? r._word : 'Unknown',
                        correct: isAttemptCorrect(d.score, d.auto_correct, d.therapist_correct),
                    };
                });
            return {
                patient_id: patientId,
                stats: {
                    total_attempts: total,
                    unique_words: t.u || 0,
                    average_score: pyRound(t.a || 0, 1),
                    best_score: t.m || 0,
                    correct_attempts: correct,
                    correct_rate: total ? pyRound(correct * 100 / total) : 0,
                },
                by_category: byCategory,
                recent_attempts: recent,
            };
        }

        function getDetailedStats(patientId) {
            const rows = all(`SELECT * FROM progress WHERE patient_id = ? AND ${NOT_GAME} ORDER BY created_at`, [patientId]);
            /** @type {Map<string, {attempts:number,total_score:number,correct:number}>} */
            const daily = new Map();
            const counts = new Map(), scores = new Map(), correctBy = new Map();
            for (const p of rows) {
                const date = String(p.created_at).slice(0, 10);
                if (!daily.has(date)) daily.set(date, { attempts: 0, total_score: 0, correct: 0 });
                const score = p.score || 0;
                const d = daily.get(date);
                d.attempts += 1;
                d.total_score += score;
                const ok = isAttemptCorrect(p.score, p.auto_correct === null ? null : Boolean(p.auto_correct),
                    p.therapist_correct === null ? null : Boolean(p.therapist_correct));
                if (ok) d.correct += 1;
                correctBy.set(p.word_id, (correctBy.get(p.word_id) || 0) + (ok ? 1 : 0));
                if (!counts.has(p.word_id)) { counts.set(p.word_id, 0); scores.set(p.word_id, 0); }
                counts.set(p.word_id, counts.get(p.word_id) + 1);
                scores.set(p.word_id, scores.get(p.word_id) + score);
            }
            const dailyProgress = [...daily.keys()].sort().map((date) => {
                const d = daily.get(date);
                return { date, attempts: d.attempts, avg_score: d.total_score / d.attempts, correct: d.correct };
            });
            const top = [], difficult = [];
            for (const [wid, count] of counts) {
                const w = one('SELECT word FROM words WHERE id = ?', [wid]);
                if (!w) continue;
                const entry = { word: w.word, attempts: count, avg_score: pyRound(scores.get(wid) / count, 1) };
                top.push(entry);
                const rate = (correctBy.get(wid) || 0) / count;
                if (count >= 2 && rate < 0.5) difficult.push({ ...entry, correct_rate: pyRound(rate * 100) });
            }
            top.sort((a, b) => b.attempts - a.attempts);
            difficult.sort((a, b) => a.correct_rate - b.correct_rate || a.avg_score - b.avg_score);
            return { daily_progress: dailyProgress.slice(-30), top_words: top.slice(0, 10), difficult_words: difficult.slice(0, 10) };
        }

        function setTherapistLabel(patientId, progressId, correct) {
            const p = one('SELECT patient_id, word_id FROM progress WHERE id = ?', [progressId]);
            if (!p || p.patient_id !== patientId || String(p.word_id).startsWith(GAME_PREFIX)) return false;
            run('UPDATE progress SET therapist_correct = ? WHERE id = ?', [correct === null ? null : (correct ? 1 : 0), progressId]);
            return true;
        }

        function getSpeechProfile(patientId) {
            const p = one('SELECT speech_profile FROM patients WHERE id = ?', [patientId]);
            let stored = {};
            if (p && p.speech_profile) { try { stored = JSON.parse(p.speech_profile) || {}; } catch (_) { stored = {}; } }
            /** @type {Record<string, any>} */
            const out = {};
            for (const [k, v] of Object.entries(SPEECH_PROFILE_DEFAULTS)) out[k] = k in stored ? stored[k] : v;
            return out;
        }

        function setSpeechProfile(patientId, updates) {
            const p = one('SELECT speech_profile FROM patients WHERE id = ?', [patientId]);
            if (!p) return null;
            let current = {};
            if (p.speech_profile) { try { current = JSON.parse(p.speech_profile) || {}; } catch (_) { current = {}; } }
            for (const [k, v] of Object.entries(updates)) if (k in SPEECH_PROFILE_DEFAULTS) current[k] = v;
            run('UPDATE patients SET speech_profile = ?, updated_at = ? WHERE id = ?', [pyJsonDumps(current), stamp(), patientId]);
            return getSpeechProfile(patientId);
        }

        function getCloudConsent(patientId) {
            const p = one('SELECT cloud_speech_consent_at FROM patients WHERE id = ?', [patientId]);
            return p ? p.cloud_speech_consent_at : null;
        }

        function speechSettings(patientId) {
            const consent = getCloudConsent(patientId);
            return { cloud_speech: consent !== null && consent !== undefined, consent_at: isoFromDb(consent),
                profile: getSpeechProfile(patientId) };
        }

        function listPatients() {
            return all(`SELECT pa.*, COUNT(pr.id) AS _n, MAX(pr.created_at) AS _last FROM patients pa
                        LEFT OUTER JOIN progress pr ON pr.patient_id = pa.id GROUP BY pa.id ORDER BY pa.name`)
                .map((r) => ({ ...toDict('patients', r), attempts: r._n || 0, last_practiced: isoFromDb(r._last) }));
        }

        function registerPatient(data) {
            const id = shortUuid();
            const ts = stamp();
            run(`INSERT INTO patients (id, name, age, diagnosis, therapist, notes, created_at, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
                [id, data.name, data.age ?? null, data.diagnosis ?? null, data.therapist ?? null, data.notes ?? null, ts, ts]);
            return id;
        }

        /** Datos de la ficha (alta y edición): las mismas reglas que PatientCreate en el servidor. */
        function validatePatient(body) {
            if (!isObj(body)) throw err422('cuerpo no válido');
            const name = str(body.name);
            if (typeof name !== 'string' || !name || name.length > 80) throw err422('name');
            let age = body.age;
            if (age === '' || age === undefined) age = null;
            if (age !== null) { age = Number(age); if (!Number.isInteger(age) || age < 0 || age > 130) throw err422('age'); }
            const opt = (v, max) => { const s = str(v); if (s === undefined || s === null || s === '') return null; if (typeof s !== 'string' || s.length > max) throw err422('campo'); return s; };
            return { name, age, diagnosis: opt(body.diagnosis, 120), notes: opt(body.notes, 1000) };
        }

        function updatePatient(patientId, data) {
            if (!one('SELECT id FROM patients WHERE id = ?', [patientId])) return false;
            run('UPDATE patients SET name = ?, age = ?, diagnosis = ?, notes = ?, updated_at = ? WHERE id = ?',
                [data.name, data.age ?? null, data.diagnosis ?? null, data.notes ?? null, stamp(), patientId]);
            return true;
        }

        /** Borra al paciente y todo lo suyo (intentos, puntos y logros). No se puede deshacer. */
        function deletePatient(patientId) {
            if (!one('SELECT id FROM patients WHERE id = ?', [patientId])) return false;
            run('BEGIN');
            try {
                for (const table of ['progress', 'achievements', 'points']) run(`DELETE FROM ${table} WHERE patient_id = ?`, [patientId]);
                run('DELETE FROM patients WHERE id = ?', [patientId]);
                if (getState('patient_id') === patientId) run('DELETE FROM app_state WHERE key = ?', ['patient_id']);
                run('COMMIT');
            } catch (e) {
                run('ROLLBACK');
                throw e;
            }
            return true;
        }

        const addPoints = (patientId, points, reason) =>
            run('INSERT INTO points (id, patient_id, points, reason, created_at) VALUES (?, ?, ?, ?, ?)',
                [shortUuid(), patientId, points, reason, stamp()]);

        function getTotalPoints(patientId) {
            const r = one('SELECT SUM(points) AS t FROM points WHERE patient_id = ?', [patientId]);
            return r && r.t ? Math.trunc(r.t) : 0;
        }

        function unlockAchievement(patientId, type, data) {
            if (one('SELECT id FROM achievements WHERE patient_id = ? AND achievement_type = ?', [patientId, type])) return false;
            run('INSERT INTO achievements (id, patient_id, achievement_type, achievement_data, unlocked_at) VALUES (?, ?, ?, ?, ?)',
                [shortUuid(), patientId, type, pyJsonDumps(data || {}), stamp()]);
            return true;
        }

        function getWordsForPractice(patientId, categoryId, level, count) {
            const words = level
                ? all('SELECT * FROM words WHERE category_id = ? AND level = ?', [categoryId, level])
                : all('SELECT * FROM words WHERE category_id = ?', [categoryId]);
            if (!words.length) return [];
            const stats = new Map(all(
                `SELECT word_id AS w, COUNT(id) AS n, AVG(score) AS a, MAX(created_at) AS last FROM progress
                 WHERE patient_id = ? AND word_id IN (${words.map(() => '?').join(', ')}) GROUP BY word_id`,
                [patientId, ...words.map((w) => w.id)]).map((r) => [r.w, r]));
            const nowMs = now().getTime();
            const items = words.map((w) => {
                const s = stats.get(w.id);
                return { word: toDict('words', w), attempts: s ? s.n || 0 : 0, avg: s ? Number(s.a || 0) : 0, last: s ? s.last : null };
            });
            const priority = (it) => {
                if (it.attempts === 0) return 100;
                const scoreFactor = 100 - it.avg;
                const timeFactor = it.last ? Math.min(Math.floor((nowMs - msFromDb(it.last)) / 86400000) * 5, 50) : 50;
                const repetition = Math.max(0, 30 - it.attempts * 3);
                return scoreFactor * 0.5 + timeFactor * 0.3 + repetition * 0.2;
            };
            const sorted = items.map((it) => ({ it, p: priority(it) })).sort((a, b) => b.p - a.p);
            return sorted.slice(0, count).map(({ it, p }) => ({
                ...it.word,
                practice_stats: { attempts: it.attempts, avg_score: pyRound(it.avg, 1), priority: pyRound(p, 1) },
            }));
        }

        function getDifficultWords(patientId, limit) {
            return all(`SELECT w.*, AVG(p.score) AS _avg, COUNT(p.id) AS _n FROM words w JOIN progress p ON p.word_id = w.id
                        WHERE p.patient_id = ? AND p.${NOT_GAME} GROUP BY w.id HAVING COUNT(p.id) >= 2
                        ORDER BY AVG(p.score) ASC LIMIT ?`, [patientId, limit])
                .map((r) => ({ ...toDict('words', r), difficulty_stats: { avg_score: pyRound(Number(r._avg), 1), attempts: r._n } }));
        }

        /** Palabras para repasar: pocos aciertos (< 60 %) o falladas la última vez. Ver database.py. */
        function getReviewWords(patientId, limit) {
            /** @type {Map<string, {n: number, ok: number, sum: number, lastOk: boolean}>} */
            const stats = new Map();
            for (const p of all(`SELECT word_id, score, auto_correct, therapist_correct FROM progress
                                 WHERE patient_id = ? AND ${NOT_GAME} ORDER BY created_at`, [patientId])) {
                const s = stats.get(p.word_id) || { n: 0, ok: 0, sum: 0, lastOk: false };
                const correct = isAttemptCorrect(p.score, p.auto_correct, p.therapist_correct);
                s.n += 1;
                s.ok += correct ? 1 : 0;
                s.sum += p.score || 0;
                s.lastOk = correct;
                stats.set(p.word_id, s);
            }
            const candidates = [];
            for (const [wordId, s] of stats) {
                const rate = s.ok / s.n;
                if (rate >= 0.6 && s.lastOk) continue;
                const word = one('SELECT * FROM words WHERE id = ?', [wordId]);
                if (word) candidates.push({ rate, avg: s.sum / s.n, word, n: s.n });
            }
            candidates.sort((a, b) => a.rate - b.rate || a.avg - b.avg || (a.word.word < b.word.word ? -1 : a.word.word > b.word.word ? 1 : 0));
            return candidates.slice(0, Math.max(0, limit)).map((c) => ({
                ...toDict('words', c.word),
                review_stats: { attempts: c.n, correct_rate: pyRound(c.rate * 100), avg_score: pyRound(c.avg, 1) },
            }));
        }

        // ---- comunicador a medida del paciente (pictogramas ocultos y frases propias)

        function loadAacProfile(raw) {
            let stored = {};
            if (raw) { try { stored = JSON.parse(raw); } catch (_) { stored = {}; } }
            if (!isObj(stored)) stored = {};
            const list = (v) => (Array.isArray(v) ? v.filter((x) => typeof x === 'string') : []);
            return { hidden: list(stored.hidden), phrases: list(stored.phrases) };
        }

        function getAacProfile(patientId) {
            const p = one('SELECT aac_profile FROM patients WHERE id = ?', [patientId]);
            return loadAacProfile(p ? p.aac_profile : null);
        }

        /** Las mismas reglas que AacProfile en rehab/schemas.py. */
        function validateAacProfile(body) {
            if (!isObj(body)) throw err422('cuerpo no válido');
            const clean = (value, maxItems, maxChars, key) => {
                if (value === undefined || value === null) return null;
                if (!Array.isArray(value)) throw err422(key);
                const out = [];
                for (const raw of value) {
                    if (typeof raw !== 'string') throw err422(key);
                    const item = raw.trim();
                    if (item.length > maxChars) throw err422(key);
                    if (item && !out.includes(item)) out.push(item);
                }
                if (out.length > maxItems) throw err422(key);
                return out;
            };
            return { hidden: clean(body.hidden, 400, 64, 'hidden'), phrases: clean(body.phrases, 40, 120, 'phrases') };
        }

        function setAacProfile(patientId, updates) {
            const p = one('SELECT aac_profile FROM patients WHERE id = ?', [patientId]);
            if (!p) return null;
            const current = loadAacProfile(p.aac_profile);
            for (const key of ['hidden', 'phrases']) if (updates[key] !== null && updates[key] !== undefined) current[key] = updates[key];
            run('UPDATE patients SET aac_profile = ?, updated_at = ? WHERE id = ?', [JSON.stringify(current), stamp(), patientId]);
            return current;
        }

        function getAacConfig() {
            return {
                categories: all('SELECT * FROM aac_categories ORDER BY order_num').map((r) => toDict('aac_categories', r)),
                items: all('SELECT * FROM aac_pictograms').map((r) => toDict('aac_pictograms', r)),
            };
        }

        // ---- game_engine.py

        function currentStreak(patientId) {
            const days = all(`SELECT DISTINCT date(created_at) AS day FROM progress WHERE patient_id = ?
                              ORDER BY date(created_at) DESC LIMIT 30`, [patientId]).map((r) => r.day);
            let streak = 0;
            const today = now();
            for (let i = 0; i < days.length; i++) {
                const expected = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
                if (days[i] === localDate(expected)) streak += 1;
                else break;
            }
            return streak;
        }

        function checkAchievements(patientId, rec) {
            const score = rec.score ?? 0;
            const isSpeech = !String(rec.word_id ?? '').startsWith(GAME_PREFIX);
            if (isSpeech && isAttemptCorrect(score, rec.is_correct)) unlockAchievement(patientId, 'first_word');
            const streak = currentStreak(patientId);
            if (streak >= 3) unlockAchievement(patientId, 'daily_streak_3');
            if (streak >= 7) unlockAchievement(patientId, 'daily_streak_7');
            if (streak >= 30) unlockAchievement(patientId, 'daily_streak_30');
            const hour = now().getHours();
            if (hour >= 22 || hour < 5) unlockAchievement(patientId, 'night_owl');
            if (hour >= 5 && hour < 7) unlockAchievement(patientId, 'early_bird');
            const q = one(`SELECT COUNT(id) AS total, SUM(CASE WHEN ${CORRECT_SQL} THEN 1 ELSE 0 END) AS correct
                           FROM progress WHERE patient_id = ? AND ${NOT_GAME}`, [patientId]);
            if ((q.correct || 0) >= 100) unlockAchievement(patientId, 'century');
            if ((q.total || 0) >= 1000) unlockAchievement(patientId, 'thousand');
        }

        function calculatePoints(rec) {
            const score = rec.score ?? 0;
            let points = 1;
            const reasons = ['intento'];
            if (score >= 90) { points += 10; reasons.push('puntuación perfecta'); }
            else if (score >= 70) { points += 5; reasons.push('buen intento'); }
            else if (score >= 50) { points += 2; reasons.push('progreso'); }
            const streak = currentStreak(rec.patient_id);
            if (streak > 0) { points += Math.min(streak * 2, 20); reasons.push(`racha de ${streak}`); }
            if (points > 0) addPoints(rec.patient_id, points, reasons.join(', '));
            checkAchievements(rec.patient_id, rec);
            return points;
        }

        function getDailyChallenge() {
            const today = localDate(now());
            const rnd = seededRandom(today);
            const pick = (arr) => arr[Math.floor(rnd() * arr.length)];
            /** @type {Record<string, any>} */
            const ch = { ...pick(DAILY_CHALLENGES) };
            const fmt = (s, vals) => s.replace(/\{(\w+)\}/g, (_, k) => String(vals[k]));
            if (ch.type === 'category_focus') {
                const cats = getCategories();
                if (cats.length) {
                    const cat = pick(cats);
                    ch.category = cat.id;
                    ch.category_name = cat.name;
                    ch.description = fmt(ch.description, { count: ch.count, category: cat.name });
                }
            } else if (ch.type === 'level_challenge') {
                ch.level = 1 + Math.floor(rnd() * 3);
                ch.description = fmt(ch.description, { count: ch.count, level: ch.level });
            } else {
                ch.description = fmt(ch.description, { count: ch.count });
            }
            ch.id = `daily_${today}`;
            ch.date = today;
            return ch;
        }

        function completeChallenge(patientId, challengeId) {
            const ch = getDailyChallenge();
            if (ch.id !== challengeId) return { success: false, message: 'Desafío no válido' };
            const points = ch.points ?? 10;
            addPoints(patientId, points, `Desafío diario: ${ch.title}`);
            return { success: true, points_earned: points, message: `¡Desafío completado! +${points} puntos` };
        }

        function getAchievements(patientId) {
            const unlocked = all('SELECT * FROM achievements WHERE patient_id = ?', [patientId]).map((r) => toDict('achievements', r));
            const result = { unlocked: [], locked: [], total_unlocked: unlocked.length, total_available: Object.keys(ACHIEVEMENTS).length };
            for (const [id, data] of Object.entries(ACHIEVEMENTS)) {
                /** @type {Record<string, any>} */
                const item = { id, ...data };
                const u = unlocked.find((a) => a.achievement_type === id);
                if (u) { item.unlocked_at = u.unlocked_at; result.unlocked.push(item); }
                else result.locked.push(item);
            }
            return result;
        }

        function getPlayerLevel(patientId) {
            const total = getTotalPoints(patientId);
            let current = LEVELS[0], next = LEVELS[1];
            LEVELS.forEach((lv, i) => { if (total >= lv[0]) { current = lv; next = LEVELS[i + 1] || null; } });
            let progress = 0;
            if (next) progress = Math.min(100, ((total - current[0]) / (next[0] - current[0])) * 100);
            return {
                level: current[1], icon: current[2], total_points: total,
                progress_to_next: pyRound(progress, 1),
                next_level: next ? next[1] : null,
                points_to_next: next ? next[0] - total : 0,
            };
        }

        // ---- voz

        async function analyzeVoice(form) {
            if (!deps.recognizer) throw new HttpError(503, 'Reconocimiento de voz no disponible');
            const audio = form.get('audio_file');
            if (!audio) throw err422('audio_file');
            const target = String(form.get('target_word') || '');
            let level = parseInt(String(form.get('level') || '1'), 10);
            if (!Number.isFinite(level)) throw err422('level');
            level = Math.max(1, Math.min(5, level));
            const patientId = currentPatient();
            const profile = getSpeechProfile(patientId);
            // Sin pista con la palabra objetivo (ver VoiceProcessor.analyze)
            const transcription = await deps.recognizer.transcribe(audio, { prompt: null, retry: true });
            return { ...RehabScoring.scoreTranscription(transcription, target, level, profile.tolerance), engine: 'local' };
        }

        async function transcribe(form) {
            if (!deps.recognizer) throw new HttpError(503, 'Reconocimiento de voz no disponible');
            const audio = form.get('audio_file');
            if (!audio) throw err422('audio_file');
            const prompt = form.get('initial_prompt');
            const text = await deps.recognizer.transcribe(audio, { prompt: prompt ? String(prompt) : null, retry: false });
            return { transcription: text, success: true };
        }

        // ---- rutas

        const intParam = (q, key, def) => {
            if (!q.has(key)) return def;
            const v = Number(q.get(key));
            if (!Number.isInteger(v)) throw err422(key);
            return v;
        };

        /** @type {[string, RegExp, (m: RegExpMatchArray, q: URLSearchParams, body: any) => any][]} */
        const routes = [
            ['GET', /^\/api\/categories$/, () => ({ categories: getCategories() })],
            ['GET', /^\/api\/words\/practice\/([^/]+)$/, (m, q) => {
                const patientId = currentPatient();
                const category = decodeURIComponent(m[1]);
                const level = q.has('level') && q.get('level') !== '' ? intParam(q, 'level', null) : null;
                const words = getWordsForPractice(patientId, category, level, intParam(q, 'count', 10));
                return { words, category, level, patient_id: patientId, method: 'spaced_repetition' };
            }],
            ['GET', /^\/api\/words\/difficult\/([^/]+)$/, (m, q) => {
                const patientId = currentPatient();
                const words = getDifficultWords(patientId, intParam(q, 'limit', 10));
                return { words, patient_id: patientId, count: words.length };
            }],
            ['GET', /^\/api\/words\/review\/([^/]+)$/, (m, q) => {
                const patientId = currentPatient();
                const words = getReviewWords(patientId, intParam(q, 'limit', 20));
                return { words, patient_id: patientId, count: words.length };
            }],
            ['GET', /^\/api\/words\/([^/]+)$/, (m, q) => {
                const category = decodeURIComponent(m[1]);
                const level = intParam(q, 'level', 1);
                return { words: getWords(category, level), category, level };
            }],
            ['POST', /^\/api\/words$/, (m, q, body) => {
                if (!isObj(body) || typeof str(body.word) !== 'string' || !str(body.word) || str(body.word).length > 100) throw err422('word');
                addWord({ ...body, word: str(body.word) });
                return { success: true, message: 'Palabra agregada' };
            }],
            ['GET', /^\/api\/aac\/config$/, () => getAacConfig()],
            ['GET', /^\/api\/aac\/profile$/, () => getAacProfile(currentPatient())],
            ['POST', /^\/api\/aac\/profile$/, (m, q, body) => {
                const patientId = currentPatient();
                const saved = setAacProfile(patientId, validateAacProfile(body));
                if (!saved) throw new HttpError(404, 'Paciente no encontrado');
                return saved;
            }],
            ['GET', /^\/api\/config$/, () => ({
                voices_available: [], languages: ['es-ES', 'es-MX', 'en-US'], difficulty_levels: [1, 2, 3, 4, 5],
                categories: getCategories(),
            })],
            ['GET', /^\/api\/progress\/([^/]+)$/, () => getProgress(currentPatient())],
            ['POST', /^\/api\/progress$/, (m, q, body) => {
                const rec = { ...validateProgress(body), patient_id: currentPatient() };
                const id = saveProgress(rec);
                const points = calculatePoints(rec);
                return { success: true, id, points_earned: points, total_points: getTotalPoints(rec.patient_id) };
            }],
            ['POST', /^\/api\/progress\/([^/]+)\/label$/, (m, q, body) => {
                if (!isObj(body)) throw err422('cuerpo no válido');
                const correct = body.correct === undefined ? null : body.correct;
                if (correct !== null && typeof correct !== 'boolean') throw err422('correct');
                const id = decodeURIComponent(m[1]);
                if (!setTherapistLabel(currentPatient(), id, correct)) throw new HttpError(404, 'Intento no encontrado');
                return { success: true, id, correct };
            }],
            ['GET', /^\/api\/stats\/([^/]+)$/, () => getDetailedStats(currentPatient())],
            ['GET', /^\/api\/games\/level\/([^/]+)$/, () => getPlayerLevel(currentPatient())],
            ['GET', /^\/api\/games\/daily-challenge$/, () => getDailyChallenge()],
            ['GET', /^\/api\/games\/achievements\/([^/]+)$/, () => getAchievements(currentPatient())],
            ['POST', /^\/api\/games\/complete-challenge$/, (m, q, body) => {
                if (!isObj(body) || typeof str(body.challenge_id) !== 'string' || !str(body.challenge_id)) throw err422('challenge_id');
                return completeChallenge(currentPatient(), str(body.challenge_id));
            }],
            ['GET', /^\/api\/speech-settings$/, () => speechSettings(currentPatient())],
            ['POST', /^\/api\/speech-settings$/, (m, q, body) => {
                const patientId = currentPatient();
                const s = validateSpeechSettings(body);
                // En la app no hay reconocimiento en la nube: el consentimiento no se registra
                const { cloud_speech: _ignored, ...profile } = s;
                if (Object.keys(profile).length) setSpeechProfile(patientId, profile);
                return speechSettings(patientId);
            }],
            ['POST', /^\/api\/analyze-voice$/, (m, q, body) => analyzeVoice(body)],
            ['POST', /^\/api\/transcribe$/, (m, q, body) => transcribe(body)],
            // ---- solo de la app: pacientes (en la web los dibuja el servidor en /patients)
            ['GET', /^\/api\/app\/patients$/, () => {
                const active = getState('patient_id');
                return { patients: listPatients(), active_patient_id: active };
            }],
            ['POST', /^\/api\/app\/patients$/, (m, q, body) => {
                const id = registerPatient(validatePatient(body));
                setState('patient_id', id);
                return { patient_id: id, success: true };
            }],
            ['POST', /^\/api\/app\/patients\/select$/, (m, q, body) => {
                const id = isObj(body) ? str(body.patient_id) : null;
                if (!id || !one('SELECT id FROM patients WHERE id = ?', [id])) throw new HttpError(404, 'Paciente no encontrado');
                setState('patient_id', id);
                return { success: true, patient_id: id };
            }],
            // Ficha del paciente: cambiar sus datos o borrarlo con todo lo suyo
            ['POST', /^\/api\/app\/patients\/([^/]+)$/, (m, q, body) => {
                const data = validatePatient(body);
                if (!updatePatient(decodeURIComponent(m[1]), data)) throw new HttpError(404, 'Paciente no encontrado');
                return { success: true };
            }],
            ['POST', /^\/api\/app\/patients\/([^/]+)\/delete$/, (m) => {
                if (!deletePatient(decodeURIComponent(m[1]))) throw new HttpError(404, 'Paciente no encontrado');
                return { success: true };
            }],
            ['GET', /^\/api\/app\/session$/, () => {
                const id = getState('patient_id');
                const p = id ? one('SELECT id, name FROM patients WHERE id = ?', [id]) : null;
                return { patient_id: p ? p.id : null, patient_name: p ? p.name : null };
            }],
        ];

        /**
         * @param {string} method @param {string} url ruta con query (p. ej. '/api/words/x?level=2')
         * @param {any} body objeto JSON ya parseado, FormData o null
         * @returns {Promise<{status: number, body: any}>}
         */
        async function handle(method, url, body) {
            const u = new URL(url, 'http://local');
            const m = method.toUpperCase();
            try {
                let pathMatched = false;
                for (const [rm, re, fn] of routes) {
                    const match = u.pathname.match(re);
                    if (!match) continue;
                    pathMatched = true;
                    if (rm !== m) continue;
                    return { status: 200, body: await fn(match, u.searchParams, body) };
                }
                if (pathMatched) return { status: 405, body: { detail: 'Method Not Allowed' } };
                return { status: 404, body: { detail: 'Not Found' } };
            } catch (e) {
                if (e instanceof HttpError) return { status: e.status, body: { detail: e.detail } };
                return { status: 500, body: { detail: String(e && e.message ? e.message : e) } };
            }
        }

        return { init, handle, currentStreak };
    }

    return { create, pyRound, pyJsonDumps };
})();
