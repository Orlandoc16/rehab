// Juegos de la página /games (cargado desde templates/games.html).
//
// Principios:
// - Sin reloj y sin castigo: la prisa perjudica en afasia y apraxia, y son adultos. Un fallo se
//   señala con suavidad (nada de rojo ni de tachados) y siempre se puede seguir.
// - Cada partida tiene varias rondas y se guarda UNA vez al terminar, con el identificador del
//   juego (game_match, game_sort...). Nunca con el de una palabra: un clic en «agua» no es una
//   pronunciación y falsearía el progreso y la repetición espaciada de la práctica.
// - La dificultad (1-3) se ajusta sola: sube si la última partida salió muy bien y baja si costó.
//   El terapeuta puede cambiarla antes de empezar.
// - En los juegos de hablar, el micrófono es una ayuda, no un juez: siempre hay un botón para
//   que el paciente o quien le acompaña diga «la dije bien». Funcionan aunque no haya
//   reconocimiento de voz.
// - Las palabras que el paciente falla en la práctica salen más a menudo.
// - Al cerrar el juego se cancela todo lo pendiente (temporizadores, audio, micrófono).
// - La voz se reconoce en NUESTRO servidor (como la práctica), no en Google. «Voz larga» solo
//   mide el volumen en el propio navegador: no graba ni envía nada.

/* global playVoice, anunciar, RehabSyllables */

const GAME_IDS = {
    naming: 'game_naming', streak: 'game_streak', sustain: 'game_sustain', complete_phrase: 'game_phrase',
    word_match: 'game_match', min_pairs: 'game_minpairs', category_sort: 'game_sort',
    pairs: 'game_pairs', maze: 'game_maze',
};
const LEVELS = 3;
// Grupos que no sirven para los juegos de palabras sueltas (frases largas, metajuegos) o que se
// solapan con otros al clasificar («agua» es necesidad básica y bebida a la vez).
const EXCLUDED_CATEGORIES = ['games_cat', 'phrases'];
const SORT_EXCLUDED = ['basic_needs', 'time'];

const pool = { words: [], categories: [], review: new Set(), ready: null };
const stats = {};                      // por id de juego: { plays, last_score, last_level, best_score }
let session = 0;                       // cambia al abrir/cerrar: invalida lo que quedara pendiente
let current = null;                    // { type, level } de la partida en curso
const timers = new Set();
const gameAudio = new Audio();
let keyHandler = null;                 // teclas propias del juego activo (flechas del laberinto)
let lastFocus = null;

// ---------- utilidades ----------
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const norm = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-zñ0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
const shuffle = (list) => {
    const a = [...list];
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
};
const content = () => document.getElementById('game-content');
const seconds = (ms) => (ms / 1000).toFixed(1).replace('.', ',');

/** Distancia de edición entre dos textos */
function lev(a, b) {
    const row = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
        let prev = row[0]; row[0] = i;
        for (let j = 1; j <= b.length; j++) {
            const tmp = row[j];
            row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
            prev = tmp;
        }
    }
    return row[b.length];
}

/** ¿Se oyó la palabra (o frase) esperada? Tolerante: es un juego, no la práctica puntuada */
function heardWord(text, target) {
    const said = norm(text), t = norm(target);
    if (!said || !t) return false;
    if (` ${said} `.includes(` ${t} `)) return true;
    if (t.includes(' ')) return lev(said, t) <= Math.max(1, Math.floor(t.length / 5));
    const tolerance = t.length >= 7 ? 2 : t.length >= 4 ? 1 : 0;
    return said.split(' ').some((token) => lev(token, t) <= tolerance);
}

/** setTimeout que no se ejecuta si el juego se cerró o cambió entretanto */
function later(fn, ms) {
    const s = session;
    const id = setTimeout(() => { timers.delete(id); if (s === session) fn(); }, ms);
    timers.add(id);
}
const wait = (ms) => new Promise((resolve) => later(resolve, ms));

function playSound(text, onEnd) {
    if (typeof playVoice === 'function') playVoice(gameAudio, `/api/speak/${encodeURIComponent(text)}`, text, onEnd ? { onEnd } : {});
    else if (onEnd) onEnd();
}
/** Dice el texto y espera a que termine (o 4 s como mucho, por si la voz no avisa) */
function speakAndWait(text) {
    return new Promise((resolve) => {
        let done = false;
        const finish = () => { if (!done) { done = true; resolve(); } };
        playSound(text, finish);
        later(finish, 4000);
    });
}
function stopSound() {
    gameAudio.pause();
    if ('speechSynthesis' in window) speechSynthesis.cancel();
}
function say(text) { if (typeof anunciar === 'function') anunciar(text); }

/** Mensaje bajo el juego: verde si es un acierto, ámbar (nunca rojo) si hay que seguir probando */
function feedback(id, text, good = true) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.classList.remove('text-green-700', 'text-amber-700', 'text-gray-700');
    el.classList.add(good === null ? 'text-gray-700' : good ? 'text-green-700' : 'text-amber-700');
    if (text) say(text);
}
const FEEDBACK_BOX = 'min-h-[2rem] mt-4 text-lg font-bold text-center';

/** Palabras sueltas y fáciles (las de varias palabras se dejan para la práctica) */
function easyWords(maxLevel = 2) {
    return pool.words.filter((w) => !w.multi && w.level <= maxLevel);
}
const withPicture = (list) => list.filter((w) => w.image_url);
/** Elige n palabras distintas (por texto), sin repetir las de `avoid` */
function pickWords(list, n, avoid = new Set()) {
    const out = [];
    const seen = new Set(avoid);
    for (const w of shuffle(list)) {
        if (out.length >= n) break;
        if (seen.has(w.key)) continue;
        seen.add(w.key);
        out.push(w);
    }
    return out;
}

/** Una palabra que no se haya usado; si ya se usaron todas, se vuelve a empezar */
function pickFresh(list, used) {
    let [w] = pickWords(list, 1, used);
    if (!w) {
        used.clear();
        [w] = pickWords(list, 1, used);
    }
    return w;
}

/** n palabras para una partida: hasta la mitad, de las que el paciente falla en la práctica */
function buildQueue(list, n) {
    const review = pickWords(list.filter((w) => pool.review.has(w.id)), Math.ceil(n / 2));
    const rest = pickWords(list, n - review.length, new Set(review.map((w) => w.key)));
    return shuffle([...review, ...rest]);
}

function picture(word, size = 'w-20 h-20') {
    return word && word.image_url
        ? `<img src="${esc(word.image_url)}" alt="" width="96" height="96" class="${size} object-contain mx-auto mb-2" loading="lazy" decoding="async">`
        : '';
}
const wordByKey = (text) => pool.words.find((w) => w.key === norm(text));

function notEnough() {
    content().innerHTML = '<p class="text-gray-700 text-lg text-center">No hay suficientes palabras para este juego.</p>';
}

// ---------- datos ----------
async function loadPool() {
    const catRes = await fetch('/api/categories');
    if (!catRes.ok) throw new Error('categorías: ' + catRes.status);
    const categories = (await catRes.json()).categories.filter((c) => !EXCLUDED_CATEGORIES.includes(c.id));
    // level=0: todas las palabras del grupo (sin nivel, la API solo da el nivel 1)
    const lists = await Promise.all(categories.map((c) =>
        fetch(`/api/words/${encodeURIComponent(c.id)}?level=0`).then((r) => (r.ok ? r.json() : { words: [] }))));
    const words = [];
    lists.forEach((data, i) => {
        for (const w of data.words || []) {
            words.push({ id: w.id, word: w.word, level: w.level || 1, image_url: w.image_url,
                         category_id: categories[i].id, key: norm(w.word), multi: /\s/.test(w.word.trim()) });
        }
    });
    // Palabras que están en más de un grupo («café»: bebida y color) no sirven para clasificar
    const count = {};
    for (const w of words) count[w.key] = (count[w.key] || 0) + 1;
    for (const w of words) w.ambiguous = count[w.key] > 1;
    pool.words = words;
    pool.categories = categories;
}

function ensurePool() {
    if (!pool.ready) pool.ready = loadPool().catch((e) => { pool.ready = null; throw e; });
    return pool.ready;
}

/** Palabras que el paciente falla en la práctica (si no se pueden cargar, se juega sin ellas) */
async function loadReview() {
    try {
        const res = await fetch('/api/words/review/default?limit=20');
        if (!res.ok) return;
        pool.review = new Set(((await res.json()).words || []).map((w) => w.id));
    } catch (e) { /* sin repaso */ }
}

async function loadSummary() {
    try {
        const res = await fetch('/api/games/summary/default');
        if (res.ok) for (const g of (await res.json()).games || []) stats[g.game] = g;
    } catch (e) { /* las tarjetas salen sin la última nota */ }
    renderCards();
}

async function loadPlayerLevel() {
    try {
        const res = await fetch('/api/games/level/default');
        if (!res.ok) throw new Error(res.statusText);
        const d = await res.json();
        document.getElementById('player-level').textContent = d.level;
        document.getElementById('player-icon').textContent = d.icon;
        document.getElementById('player-points').textContent = d.total_points;
        document.getElementById('progress-bar').style.width = (d.next_level ? d.progress_to_next : 100) + '%';
        document.getElementById('progress-percent').textContent = d.next_level ? Math.round(d.progress_to_next) + '%' : '¡Máximo!';
        document.getElementById('points-to-next').textContent = d.next_level
            ? `${d.points_to_next} puntos para ${d.next_level}` : '¡Has alcanzado el nivel máximo!';
    } catch (e) {
        document.getElementById('player-level').textContent = '—';
        document.getElementById('points-to-next').textContent = 'No se pudo cargar el nivel';
    }
}

async function loadDailyChallenge() {
    try {
        const data = await (await fetch('/api/games/daily-challenge')).json();
        document.getElementById('challenge-title').textContent = data.title;
        document.getElementById('challenge-description').textContent = data.description;
        document.getElementById('challenge-points').textContent = data.points;
        const link = document.getElementById('challenge-link');
        if (link && data.type === 'review_words') link.setAttribute('href', '/practice?category=__repaso');
    } catch (e) {
        document.getElementById('challenge-title').textContent = 'No disponible';
    }
}

async function loadAchievements() {
    const grid = document.getElementById('achievements-grid');
    try {
        const data = await (await fetch('/api/games/achievements/default')).json();
        const unlocked = (data.unlocked || []).map((a) => `
            <div class="bg-gradient-to-br from-yellow-400 to-orange-500 rounded-xl p-4 text-center shadow-lg">
                <div class="text-3xl mb-2">${esc(a.icon)}</div>
                <h5 class="font-semibold text-white text-sm">${esc(a.name)}</h5>
            </div>`);
        const locked = (data.locked || []).map((a) => `
            <div class="bg-gray-100 rounded-xl p-4 text-center" title="${esc(a.description || '')}">
                <div class="text-3xl mb-2 opacity-50">🔒</div>
                <h5 class="font-semibold text-gray-600 text-sm">${esc(a.name)}</h5>
            </div>`);
        grid.innerHTML = [...unlocked, ...locked].join('');
    } catch (e) {
        grid.innerHTML = '<p class="col-span-full text-gray-600">No se pudieron cargar los logros.</p>';
    }
}

/** Guarda la partida terminada (score 0-100) y devuelve los puntos ganados */
async function saveGame(gameType, score, details = {}) {
    const rounded = Math.max(0, Math.min(100, Math.round(score)));
    try {
        const res = await fetch('/api/progress', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_id: 'default',          // el servidor usa siempre el paciente de la sesión
                word_id: GAME_IDS[gameType],
                score: rounded,
                attempt_number: 1,
                transcription: 'Juego: ' + gameType,
                feedback: details,
                duration_ms: details.duration_ms || null,
            }),
        });
        if (!res.ok) throw new Error(res.statusText);
        const data = await res.json();
        const id = GAME_IDS[gameType];
        const old = stats[id] || { plays: 0, best_score: 0 };
        stats[id] = { ...old, game: id, plays: old.plays + 1, last_score: rounded,
                      last_level: details.level || null, best_score: Math.max(old.best_score, rounded) };
        renderCards();
        loadPlayerLevel();
        loadAchievements();
        return data.points_earned || 0;
    } catch (e) {
        console.warn('No se pudo guardar la partida:', e);
        return null;
    }
}

// ---------- los juegos ----------
// levels: qué cambia en cada dificultad (null = el juego no tiene niveles)
const GAMES = {
    naming: {
        title: '¿Qué es?', emoji: '🖼️', group: 'speak', trains: 'encontrar la palabra',
        about: 'Mira el dibujo y di qué es. Si no sale, pide una pista.',
        levels: ['Palabras muy comunes', 'Más palabras', 'Palabras menos frecuentes'],
        start: startNaming, tile: 'bg-indigo-100', btn: 'bg-indigo-700 hover:bg-indigo-800',
    },
    streak: {
        title: 'Palabras seguidas', emoji: '🔥', group: 'speak', trains: 'decir palabras con claridad',
        about: 'Di cada palabra en voz alta, a tu ritmo. Sin reloj.',
        levels: ['Palabras cortas y comunes', 'Más palabras', 'Palabras largas y expresiones'],
        start: startStreak, tile: 'bg-amber-100', btn: 'bg-amber-700 hover:bg-amber-800',
    },
    sustain: {
        title: 'Voz larga', emoji: '⛵', group: 'speak', trains: 'el aire y la fuerza de la voz',
        about: 'Di «aaaa» sin parar para llevar el barco hasta la meta.',
        levels: ['Meta: 3 segundos', 'Meta: 5 segundos', 'Meta: 8 segundos'],
        start: startSustain, tile: 'bg-sky-100', btn: 'bg-sky-700 hover:bg-sky-800',
    },
    complete_phrase: {
        title: 'Completa la frase', emoji: '💬', group: 'speak', trains: 'construir frases',
        about: 'Elige la palabra que falta y luego di la frase entera.',
        levels: ['Dos opciones', 'Tres opciones', 'Cuatro opciones'],
        start: startCompletePhrase, tile: 'bg-pink-100', btn: 'bg-pink-700 hover:bg-pink-800',
    },
    word_match: {
        title: 'Escucha y elige', emoji: '🎯', group: 'listen', trains: 'entender lo que se oye',
        about: 'Escucha la palabra y toca el dibujo que le corresponde.',
        levels: ['Tres opciones muy distintas', 'Cuatro opciones', 'Cuatro opciones que se parecen'],
        start: startWordMatch, tile: 'bg-blue-100', btn: 'bg-blue-700 hover:bg-blue-800',
    },
    min_pairs: {
        title: 'Palabras parecidas', emoji: '👂', group: 'listen', trains: 'distinguir sonidos',
        about: 'Dos palabras que suenan casi igual: «pato» y «gato». ¿Cuál has oído?',
        levels: ['Cambia una vocal', 'Cambia una consonante', '¿Son iguales o distintas?'],
        start: startMinPairs, tile: 'bg-violet-100', btn: 'bg-violet-700 hover:bg-violet-800',
    },
    category_sort: {
        title: 'Clasificar palabras', emoji: '📦', group: 'listen', trains: 'el significado de las palabras',
        about: 'Elige a qué grupo pertenece cada palabra.',
        levels: ['Dos grupos', 'Tres grupos', 'Tres grupos y «¿cuál no pertenece?»'],
        start: startCategorySort, tile: 'bg-green-100', btn: 'bg-green-700 hover:bg-green-800',
    },
    pairs: {
        title: 'Parejas', emoji: '🃏', group: 'fun', trains: 'la memoria, nombrando cada dibujo',
        about: 'Levanta dos cartas y encuentra las parejas. Di la palabra al encontrarla.',
        levels: ['3 parejas', '4 parejas', '6 parejas'],
        start: startPairs, tile: 'bg-purple-100', btn: 'bg-purple-700 hover:bg-purple-800',
    },
    maze: {
        title: 'Laberinto de voz', emoji: '🗺️', group: 'fun', trains: 'pasar un buen rato',
        about: 'Guía al mono con tu voz: «Arriba», «Abajo»… (o con las flechas).',
        levels: null,
        start: startMazeGame, tile: 'bg-teal-100', btn: 'bg-teal-700 hover:bg-teal-800',
    },
};
const GROUPS = [['speak', 'Hablar'], ['listen', 'Escuchar y entender'], ['fun', 'Para pasar un buen rato']];

/** Dificultad para la próxima partida: sube si la última salió muy bien, baja si costó */
function suggestedLevel(type) {
    const s = stats[GAME_IDS[type]];
    if (!GAMES[type].levels || !s || !s.last_level) return 1;
    const step = s.last_score >= 85 ? 1 : s.last_score < 50 ? -1 : 0;
    return Math.max(1, Math.min(LEVELS, s.last_level + step));
}

function renderCards() {
    const list = document.getElementById('games-list');
    if (!list) return;
    const card = ([type, g]) => {
        const s = stats[GAME_IDS[type]];
        const last = s ? `Última vez: ${s.last_score}%${s.last_level ? ` · nivel ${s.last_level}` : ''}` : 'Sin jugar todavía';
        return `
            <div class="bg-white rounded-2xl shadow-lg p-6 flex flex-col">
                <div class="w-14 h-14 ${g.tile} rounded-xl flex items-center justify-center mb-4"><span class="text-3xl">${g.emoji}</span></div>
                <h4 class="text-lg font-bold text-gray-800 mb-1">${esc(g.title)}</h4>
                <p class="text-gray-600 text-sm mb-4">${esc(g.about)}</p>
                <div class="mt-auto flex items-center justify-between gap-3">
                    <span class="text-sm text-gray-600">${last}</span>
                    <button data-play="${type}" aria-label="Jugar a ${esc(g.title)}"
                        class="${g.btn} text-white px-5 py-2 min-h-[48px] rounded-lg font-semibold transition">Jugar</button>
                </div>
            </div>`;
    };
    const practice = `
        <div class="bg-white rounded-2xl shadow-lg p-6 flex flex-col">
            <div class="w-14 h-14 bg-gray-100 rounded-xl flex items-center justify-center mb-4"><span class="text-3xl">🎤</span></div>
            <h4 class="text-lg font-bold text-gray-800 mb-1">Práctica</h4>
            <p class="text-gray-600 text-sm mb-4">Practica las palabras que quieras, con nota y valoración del terapeuta.</p>
            <div class="mt-auto flex items-center justify-end">
                <a href="/practice" class="bg-gray-700 hover:bg-gray-800 text-white px-5 py-2 min-h-[48px] rounded-lg font-semibold transition inline-flex items-center">Ir</a>
            </div>
        </div>`;
    list.innerHTML = GROUPS.map(([id, name]) => `
        <h3 class="text-2xl font-bold text-gray-800 mb-4">${name}</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
            ${Object.entries(GAMES).filter(([, g]) => g.group === id).map(card).join('')}${id === 'speak' ? practice : ''}
        </div>`).join('');
}

// ---------- ventana del juego ----------
/** Abre la ventana con la presentación del juego (qué se hace y con qué dificultad) */
async function startGame(type) {
    const game = GAMES[type];
    if (!game) return;
    resetSession();
    const modal = document.getElementById('game-modal');
    if (modal.classList.contains('hidden')) {
        lastFocus = document.activeElement;
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        document.getElementById('game-close-btn').focus();
    }
    document.getElementById('game-modal-title').textContent = `${game.emoji} ${game.title}`;
    const s = session;
    content().innerHTML = '<p class="text-gray-600 text-lg"><i class="fas fa-spinner fa-spin mr-2"></i>Preparando el juego…</p>';
    try {
        await ensurePool();
    } catch (e) {
        if (s === session) content().innerHTML = '<p class="text-gray-800 text-lg text-center">No se pudieron cargar las palabras. Comprueba la conexión y vuelve a intentarlo.</p>';
        return;
    }
    if (s !== session) return;
    showIntro(type);
}

function showIntro(type) {
    const game = GAMES[type];
    const level = suggestedLevel(type);
    const chips = game.levels ? `
        <p class="text-gray-700 font-semibold mb-2" id="level-label">Dificultad</p>
        <div class="flex justify-center gap-3 mb-2" role="group" aria-labelledby="level-label">
            ${game.levels.map((_, i) => `
                <button data-action="level" data-level="${i + 1}" aria-pressed="${i + 1 === level}"
                    class="level-chip w-14 h-14 rounded-xl border-2 text-xl font-bold transition ${i + 1 === level ? 'bg-primary border-primary text-white' : 'bg-white border-gray-300 text-gray-800'}">${i + 1}</button>`).join('')}
        </div>
        <p id="level-desc" class="text-gray-600 mb-6 min-h-[1.5rem]">${esc(game.levels[level - 1])}</p>` : '';
    content().innerHTML = `
        <div class="text-center w-full max-w-xl">
            <div class="text-6xl mb-3" aria-hidden="true">${game.emoji}</div>
            <p class="text-xl text-gray-800 mb-2">${esc(game.about)}</p>
            <p class="text-gray-600 mb-6">Sirve para trabajar ${esc(game.trains)}.</p>
            ${chips}
            <button data-action="begin" data-game="${type}" data-level="${level}" id="begin-btn"
                class="${game.btn} text-white px-10 py-5 rounded-2xl text-2xl font-bold transition">
                <i class="fas fa-play mr-2"></i>Empezar
            </button>
        </div>`;
}

function runGame(type, level) {
    resetSession();
    current = { type, level };
    loadReview();                         // para la próxima partida; esta usa lo ya cargado
    GAMES[type].start(level);
}

/** Cancela todo lo de la partida anterior */
function resetSession() {
    session++;
    for (const id of timers) clearTimeout(id);
    timers.clear();
    keyHandler = null;
    sayCtx = null;
    stopSound();
    stopListening(true);
    stopSustain();
}

function closeGame() {
    resetSession();
    current = null;
    document.getElementById('game-modal').classList.add('hidden');
    document.body.style.overflow = '';
    content().innerHTML = '';
    if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
}

document.addEventListener('keydown', (e) => {
    if (document.getElementById('game-modal').classList.contains('hidden')) return;
    if (e.key === 'Escape') { e.preventDefault(); closeGame(); return; }
    if (keyHandler) keyHandler(e);
});

// Delegación de clics: los botones llevan data-action (sin texto de palabras dentro de onclick)
document.addEventListener('click', (e) => {
    const el = e.target instanceof Element ? e.target : null;
    if (!el) return;
    const play = el.closest('[data-play]');
    if (play) { startGame(play.getAttribute('data-play')); return; }
    const btn = el.closest('[data-action]');
    if (!btn || btn.disabled || !content().contains(btn)) return;
    const handler = ACTIONS[btn.dataset.action];
    if (handler) handler(btn);
});
const ACTIONS = {};

ACTIONS.level = (btn) => {
    const level = Number(btn.dataset.level);
    const begin = document.getElementById('begin-btn');
    begin.dataset.level = String(level);
    content().querySelectorAll('.level-chip').forEach((chip) => {
        const on = chip === btn;
        chip.setAttribute('aria-pressed', String(on));
        chip.classList.toggle('bg-primary', on); chip.classList.toggle('border-primary', on); chip.classList.toggle('text-white', on);
        chip.classList.toggle('bg-white', !on); chip.classList.toggle('border-gray-300', !on); chip.classList.toggle('text-gray-800', !on);
    });
    document.getElementById('level-desc').textContent = GAMES[begin.dataset.game].levels[level - 1];
};
ACTIONS.begin = (btn) => runGame(btn.dataset.game, Number(btn.dataset.level) || 1);
ACTIONS.restart = (btn) => runGame(btn.dataset.game, Number(btn.dataset.level) || 1);
ACTIONS.close = () => closeGame();
ACTIONS.speak = (btn) => playSound(btn.dataset.text);

/** Pantalla final común a todos los juegos */
async function showEnd(type, { emoji, title, lines, score, details }) {
    const s = session;
    const level = current ? current.level : 1;
    const hasLevels = !!GAMES[type].levels;
    const saved = hasLevels ? { level, ...details } : details;
    content().innerHTML = `
        <div class="text-center">
            <div class="text-6xl mb-4" aria-hidden="true">${emoji}</div>
            <h2 class="text-3xl font-bold text-gray-800 mb-3">${esc(title)}</h2>
            ${lines.map((l) => `<p class="text-xl text-gray-700 mb-2">${l}</p>`).join('')}
            <p id="end-next" class="text-lg text-gray-700 mb-2"></p>
            <p id="end-points" class="text-lg text-gray-600 mb-6">Guardando…</p>
            <div class="flex flex-wrap justify-center gap-3">
                <button data-action="restart" data-game="${type}" data-level="${level}" class="bg-primary text-white px-8 py-4 rounded-xl text-lg font-semibold hover:bg-secondary transition">Jugar otra vez</button>
                <button data-action="close" class="bg-gray-200 text-gray-800 px-8 py-4 rounded-xl text-lg font-semibold hover:bg-gray-300 transition">Salir</button>
            </div>
        </div>`;
    say(`${title}. ${lines.map((l) => l.replace(/<[^>]+>/g, '')).join(' ')}`);
    const points = await saveGame(type, score, saved);
    if (s !== session) return;
    const el = document.getElementById('end-points');
    if (el) el.textContent = points === null ? 'No se pudo guardar la partida.' : `+${points} puntos`;
    if (!hasLevels || points === null) return;
    const next = suggestedLevel(type);
    const again = content().querySelector('[data-action="restart"]');
    if (again) again.dataset.level = String(next);
    const note = document.getElementById('end-next');
    if (note && next !== level) note.textContent = next > level ? 'Te ha salido muy bien: la próxima será un poco más difícil.' : 'La próxima será un poco más fácil.';
}

function roundHeader(round, total, extra = '') {
    return `<div class="flex justify-between items-center w-full mb-4 text-gray-600">
        <span class="font-medium">Ronda ${round} de ${total}</span>${extra}</div>`;
}

/** Marca una respuesta: verde y bloquea todo si es correcta; si no, se apaga sin dramatismo */
function markAnswer(btn, ok, group) {
    if (ok) {
        btn.classList.add('!bg-green-100', '!border-green-600', 'text-green-800');
        group.querySelectorAll('button').forEach((b) => { b.disabled = true; });
    } else {
        btn.classList.add('opacity-40', '!border-dashed');
        btn.disabled = true;
    }
}

// ---------- micrófono: escuchar una palabra ----------
const MIC_ERRORS = {
    https: 'El micrófono no está disponible en este navegador.',
    denied: 'Necesito permiso para usar el micrófono.',
    mic: 'No se pudo usar el micrófono.',
    silence: 'No te oí. Acércate y habla un poco más fuerte.',
    server: 'No se pudo reconocer la voz.',
};
const VOICE_ON = 0.012, VOICE_KEEP = 0.006;    // volumen (RMS) para empezar a contar voz y para seguir
let rec = null;                // grabación en curso
let micStarting = false;       // evita abrir dos micrófonos con dos pulsaciones seguidas
let audioCtx = null;

async function openMic() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return { error: 'https' };
    try {
        return { stream: await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: true } }) };
    } catch (e) {
        return { error: e && e.name === 'NotAllowedError' ? 'denied' : 'mic' };
    }
}

/** Medidor de volumen del micrófono; null si el navegador no tiene Web Audio */
function volumeMeter(stream) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return null;
    audioCtx = audioCtx || new AudioCtx();
    if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    const source = audioCtx.createMediaStreamSource(stream);
    source.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    return {
        rms() {
            analyser.getFloatTimeDomainData(buf);
            let sum = 0; for (const v of buf) sum += v * v;
            return Math.sqrt(sum / buf.length);
        },
        close() { try { source.disconnect(); } catch (e) { /* ya cerrado */ } },
    };
}

/**
 * Graba hasta que la persona calla (o maxMs) y devuelve lo transcrito.
 * @returns {Promise<{text: string} | {error: string} | null>} null si se canceló o ya había otra
 */
async function listen({ prompt = '', maxMs = 5000, onState = () => {} } = {}) {
    if (rec || micStarting) return null;
    if (typeof MediaRecorder === 'undefined') return { error: 'https' };
    const s = session;
    micStarting = true;
    const mic = await openMic();
    micStarting = false;
    if (mic.error) return s === session ? { error: mic.error } : null;
    const stream = mic.stream;
    if (s !== session) { stream.getTracks().forEach((t) => t.stop()); return null; }
    stopSound();
    const recorder = new MediaRecorder(stream);
    const chunks = [];
    const r = { recorder, stream, heard: false, cancelled: false, timer: null, meter: null };
    rec = r;
    const stopped = new Promise((resolve) => { recorder.onstop = resolve; });
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.start();
    onState('listening');

    // Para sola al callar (como en la práctica) o al llegar a maxMs
    const started = Date.now();
    r.meter = volumeMeter(stream);
    if (!r.meter) { r.heard = true; later(() => { if (rec === r) stopListening(false); }, 3000); }
    else {
        let lastVoice = 0, voiceMs = 0;
        r.timer = setInterval(() => {
            const now = Date.now();
            if (r.meter.rms() > (r.heard ? VOICE_KEEP : VOICE_ON)) { voiceMs += 50; lastVoice = now; if (voiceMs >= 150) r.heard = true; }
            if ((r.heard && now - lastVoice > 900) || now - started > maxMs) { if (rec === r) stopListening(false); }
        }, 50);
    }

    await stopped;
    stream.getTracks().forEach((t) => t.stop());
    clearInterval(r.timer);
    if (r.meter) r.meter.close();
    if (rec === r) rec = null;
    if (r.cancelled || s !== session) return null;
    if (!r.heard) return { error: 'silence' };
    onState('thinking');
    const form = new FormData();
    form.append('audio_file', new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }), 'voz.webm');
    if (prompt) form.append('initial_prompt', prompt);
    try {
        const res = await fetch('/api/transcribe', { method: 'POST', body: form });
        if (!res.ok) throw new Error(res.statusText);
        const data = await res.json();
        return s === session ? { text: data.transcription || '' } : null;
    } catch (e) {
        return s === session ? { error: 'server' } : null;
    }
}

/** cancel: descartar lo grabado; byUser: se pulsó para terminar (se envía aunque fuera bajito) */
function stopListening(cancel, byUser = false) {
    const r = rec;
    if (!r) return;
    r.cancelled = cancel;
    if (byUser) r.heard = true;
    clearInterval(r.timer);
    rec = null;
    if (r.recorder.state !== 'inactive') r.recorder.stop();
    else r.stream.getTracks().forEach((t) => t.stop());
}

// ---------- «dila en voz alta»: micrófono + botón de quien acompaña ----------
let sayCtx = null;             // { accepts(text), onResult(ok, how), done }

function sayPanel({ okLabel = 'La dije bien', skipLabel = 'Pasar' } = {}) {
    return `
        <div class="flex flex-wrap items-center justify-center gap-4 mt-2">
            <button id="say-mic" data-action="say-mic" aria-label="Decirla al micrófono"
                class="bg-teal-700 text-white w-20 h-20 rounded-full text-3xl shadow-lg hover:opacity-90 transition flex items-center justify-center">
                <i class="fas fa-microphone"></i>
            </button>
            <button data-action="say-ok" class="say-btn bg-green-700 text-white px-6 py-4 rounded-2xl text-lg font-bold hover:bg-green-800 transition"><i class="fas fa-check mr-2"></i>${okLabel}</button>
            <button data-action="say-skip" class="say-btn bg-gray-200 text-gray-800 px-6 py-4 rounded-2xl text-lg font-bold hover:bg-gray-300 transition">${skipLabel}</button>
        </div>
        <div id="say-feedback" class="${FEEDBACK_BOX}" aria-live="polite"></div>`;
}

/** Espera a que digan `target` (o lo que acepte `accepts`); onResult(ok, 'voice'|'manual'|'skip') */
function expectSpeech(target, onResult) {
    sayCtx = { accepts: (text) => heardWord(text, target), onResult, done: false };
}

function setMicButton(state) {
    const btn = document.getElementById('say-mic');
    if (!btn) return;
    btn.classList.toggle('bg-red-700', state === 'listening');
    btn.classList.toggle('bg-teal-700', state !== 'listening');
    btn.setAttribute('aria-label', state === 'listening' ? 'Terminar de hablar' : 'Decirla al micrófono');
    btn.innerHTML = `<i class="fas ${state === 'listening' ? 'fa-stop' : state === 'thinking' ? 'fa-spinner fa-spin' : 'fa-microphone'}"></i>`;
}

function finishSay(ok, how) {
    const ctx = sayCtx;
    if (!ctx || ctx.done) return;
    ctx.done = true;
    stopListening(true);
    content().querySelectorAll('#say-mic, .say-btn').forEach((b) => { b.disabled = true; });
    ctx.onResult(ok, how);
}

ACTIONS['say-mic'] = async () => {
    const ctx = sayCtx;
    if (!ctx || ctx.done) return;
    if (rec) { stopListening(false, true); return; }
    const res = await listen({
        onState: (state) => {
            setMicButton(state);
            feedback('say-feedback', state === 'listening' ? 'Te escucho…' : 'Un momento…', null);
        },
    });
    if (ctx !== sayCtx || ctx.done) return;
    setMicButton('idle');
    if (!res) return;
    if (res.error) { feedback('say-feedback', `${MIC_ERRORS[res.error]} Si la dijiste, pulsa el botón verde.`, false); return; }
    if (ctx.accepts(res.text)) finishSay(true, 'voice');
    else feedback('say-feedback', res.text ? `Oí «${res.text}». Prueba otra vez, o pulsa el botón verde si la dijiste bien.` : 'No te entendí. Prueba otra vez.', false);
};
ACTIONS['say-ok'] = () => finishSay(true, 'manual');
ACTIONS['say-skip'] = () => finishSay(false, 'skip');

// =============== 1. ¿Qué es?: decir el nombre del dibujo, con pistas graduadas ===============
// Sin pista vale 1; con la primera sílaba, 0,6; si hizo falta oír la palabra entera (repetir), 0,3.
const NAMING_ROUNDS = 8;
const NAMING_VALUE = [1, 0.6, 0.3];
let naming = null;

function startNaming(level) {
    let words = withPicture(easyWords(level));
    if (words.length < NAMING_ROUNDS) words = withPicture(easyWords(3));
    const queue = buildQueue(words, NAMING_ROUNDS);
    if (queue.length < 4) { notEnough(); return; }
    naming = { queue, round: 0, counts: [0, 0, 0], skipped: 0, started: Date.now() };
    nextNamingRound();
}

function nextNamingRound() {
    const word = naming.queue[naming.round];
    naming.round++;
    naming.word = word;
    naming.cue = 0;
    content().innerHTML = `
        <div class="text-center w-full max-w-xl">
            ${roundHeader(naming.round, naming.queue.length)}
            <p class="text-gray-700 text-lg mb-3">¿Qué es? Dilo en voz alta.</p>
            <div class="bg-indigo-50 rounded-2xl p-4 mb-3 inline-block">${picture(word, 'w-40 h-40')}</div>
            <div id="naming-cue" class="min-h-[2.5rem] text-2xl font-bold text-indigo-800 mb-2" aria-live="polite"></div>
            <button data-action="naming-cue" id="naming-cue-btn" class="bg-white border-2 border-indigo-300 text-indigo-800 px-6 py-3 rounded-2xl text-lg font-semibold hover:bg-indigo-50 transition mb-4">💡 Dame una pista</button>
            ${sayPanel()}
        </div>`;
    expectSpeech(word.word, (ok) => {
        const text = word.word;
        if (ok) naming.counts[naming.cue]++; else naming.skipped++;
        const cue = document.getElementById('naming-cue');
        if (cue) cue.textContent = `«${text}»`;
        document.getElementById('naming-cue-btn').disabled = true;
        feedback('say-feedback', ok ? '¡Eso es!' : `Es «${text}». Vamos con otra.`, ok ? true : null);
        playSound(text);
        later(() => (naming.round >= naming.queue.length ? endNaming() : nextNamingRound()), 1900);
    });
}

function firstSyllable(word) {
    const parts = typeof RehabSyllables !== 'undefined' ? RehabSyllables.splitWord(word) : [];
    return parts.length > 1 ? parts[0] : word.slice(0, Math.min(2, Math.max(1, word.length - 1)));
}

ACTIONS['naming-cue'] = (btn) => {
    if (!sayCtx || sayCtx.done) return;
    const text = naming.word.word;
    const cue = document.getElementById('naming-cue');
    naming.cue++;
    if (naming.cue === 1) {
        const start = firstSyllable(text);
        cue.textContent = `Empieza por «${start}…»`;
        say(`Empieza por ${start}`);
        playSound(start);
        btn.textContent = '💡 Otra pista';
    } else {
        naming.cue = 2;
        cue.textContent = `Es «${text}». Repítela.`;
        say(`Es ${text}. Repítela.`);
        playSound(text);
        btn.disabled = true;
    }
};

function endNaming() {
    const n = naming.queue.length;
    const [clean, cued, repeated] = naming.counts;
    const score = naming.counts.reduce((sum, c, i) => sum + c * NAMING_VALUE[i], 0) / n * 100;
    const lines = [`Dijiste <strong>${clean} de ${n}</strong> sin ayuda.`];
    if (cued + repeated) lines.push(`Con pista: <strong>${cued + repeated}</strong>.`);
    showEnd('naming', {
        emoji: clean >= n * 0.75 ? '🏆' : '👏', title: '¡Partida terminada!', lines, score,
        details: { rounds: n, no_cue: clean, with_cue: cued, repeated, skipped: naming.skipped, duration_ms: Date.now() - naming.started },
    });
}

// =============== 2. Palabras seguidas: decirlas a tu ritmo (sin reloj) ===============
const STREAK_ROUNDS = 10;
let streak = null;

function startStreak(level) {
    let words = level >= 3 ? pool.words.filter((w) => w.level <= 3) : easyWords(level);
    if (words.length < STREAK_ROUNDS) words = easyWords(3);
    const queue = buildQueue(words, STREAK_ROUNDS);
    if (queue.length < 4) { notEnough(); return; }
    streak = { queue, round: 0, good: 0, run: 0, best: 0, started: Date.now() };
    nextStreakWord();
}

function nextStreakWord() {
    const word = streak.queue[streak.round];
    streak.round++;
    const fire = streak.run >= 2 ? `<span class="font-bold text-amber-700">${streak.run} seguidas 🔥</span>` : '';
    content().innerHTML = `
        <div class="text-center w-full max-w-xl">
            ${roundHeader(streak.round, streak.queue.length, fire)}
            <p class="text-gray-700 text-lg mb-3">Di esta palabra en voz alta:</p>
            <div class="bg-gray-50 rounded-2xl p-6 mb-4 border-2 border-gray-100">
                ${picture(word, 'w-24 h-24')}
                <p class="text-4xl md:text-5xl font-bold text-gray-800 capitalize">${esc(word.word)}</p>
                <button data-action="speak" data-text="${esc(word.word)}" class="mt-3 text-blue-700 font-medium hover:underline px-4 py-2"><i class="fas fa-volume-high mr-1"></i>Escuchar</button>
            </div>
            ${sayPanel()}
        </div>`;
    expectSpeech(word.word, (ok) => {
        if (ok) { streak.good++; streak.run++; streak.best = Math.max(streak.best, streak.run); }
        else streak.run = 0;
        feedback('say-feedback', ok ? (streak.run >= 3 ? `¡Bien! Llevas ${streak.run} seguidas.` : '¡Bien!') : 'Vamos con otra.', ok ? true : null);
        later(() => (streak.round >= streak.queue.length ? endStreak() : nextStreakWord()), 1100);
    });
}

function endStreak() {
    const n = streak.queue.length;
    const lines = [`Dijiste bien <strong>${streak.good} de ${n}</strong> palabras.`];
    if (streak.best >= 2) lines.push(`Tu mejor racha: <strong>${streak.best} seguidas</strong>.`);
    showEnd('streak', {
        emoji: streak.good >= n * 0.8 ? '🏆' : '👏', title: '¡Partida terminada!', lines, score: (streak.good / n) * 100,
        details: { rounds: n, words_ok: streak.good, best_streak: streak.best, duration_ms: Date.now() - streak.started },
    });
}

// =============== 3. Voz larga: sostener una vocal ===============
// Solo mide el volumen del micrófono en el navegador: no graba ni envía audio.
const SUSTAIN_TARGETS = [3, 5, 8];     // segundos por nivel
const SUSTAIN_ROUNDS = 5;
let sustain = null;

function startSustain(level) {
    sustain = { target: SUSTAIN_TARGETS[level - 1] * 1000, round: 0, held: [], mic: null, running: false, started: Date.now() };
    nextSustainRound();
}

function nextSustainRound() {
    sustain.round++;
    content().innerHTML = `
        <div class="text-center w-full max-w-xl">
            ${roundHeader(sustain.round, SUSTAIN_ROUNDS, `<span>Meta: <strong>${sustain.target / 1000} segundos</strong></span>`)}
            <p class="text-gray-700 text-lg mb-4">Toma aire y di <strong>«aaaa»</strong> sin parar, hasta la meta.</p>
            <div class="relative w-full h-20 bg-sky-100 rounded-2xl mb-3 overflow-hidden" aria-hidden="true">
                <div class="absolute right-3 top-1/2 -translate-y-1/2 text-4xl">🏁</div>
                <div id="sus-boat" class="absolute top-1/2 -translate-y-1/2 text-5xl" style="left: 2%">⛵</div>
            </div>
            <p class="text-5xl font-bold text-sky-800 mb-1"><span id="sus-time">0,0</span> <span class="text-2xl">s</span></p>
            <div class="w-full h-3 bg-gray-200 rounded-full mb-5" aria-hidden="true"><div id="sus-vol" class="h-3 bg-teal-500 rounded-full" style="width: 0%"></div></div>
            <button data-action="sus-go" id="sus-go" class="bg-sky-700 text-white px-10 py-5 rounded-2xl text-2xl font-bold hover:bg-sky-800 transition">
                <i class="fas fa-microphone mr-2"></i>Empezar
            </button>
            <div id="sus-feedback" class="${FEEDBACK_BOX}" aria-live="polite"></div>
        </div>`;
}

ACTIONS['sus-go'] = async (btn) => {
    if (sustain.running) return;
    if (btn.dataset.next) { if (sustain.round >= SUSTAIN_ROUNDS) endSustain(); else nextSustainRound(); return; }
    sustain.running = true;
    btn.disabled = true;
    const s = session;
    if (!sustain.mic) {
        const mic = await openMic();
        if (s !== session) { if (mic.stream) mic.stream.getTracks().forEach((t) => t.stop()); return; }
        const meter = mic.stream ? volumeMeter(mic.stream) : null;
        if (!meter) {
            if (mic.stream) mic.stream.getTracks().forEach((t) => t.stop());
            sustain.running = false;
            btn.disabled = false;
            feedback('sus-feedback', mic.error ? MIC_ERRORS[mic.error] : 'Este juego necesita el micrófono.', false);
            return;
        }
        sustain.mic = { stream: mic.stream, meter, timer: null };
    }
    stopSound();
    feedback('sus-feedback', 'Te escucho… di «aaaa».', null);
    const mic = sustain.mic;
    const boat = document.getElementById('sus-boat'), time = document.getElementById('sus-time'), vol = document.getElementById('sus-vol');
    const limit = Math.max(sustain.target * 2, sustain.target + 5000);
    const began = Date.now();
    let held = 0, voiced = 0, lastVoice = 0, speaking = false, last = began;
    mic.timer = setInterval(() => {
        const now = Date.now(), dt = now - last;
        last = now;
        const rms = mic.meter.rms();
        vol.style.width = Math.min(100, Math.round(rms * 700)) + '%';
        if (rms > (speaking ? VOICE_KEEP : VOICE_ON)) {
            lastVoice = now;
            if (speaking) held += dt;
            else { voiced += dt; if (voiced >= 150) { speaking = true; held = voiced; } }
        } else if (!speaking) voiced = 0;
        if (speaking) {
            time.textContent = seconds(held);
            boat.style.left = (2 + Math.min(1, held / sustain.target) * 78) + '%';
        }
        const silent = speaking && now - lastVoice > 400;
        if (silent || held >= limit || (!speaking && now - began > 10000)) finishSustainRound(speaking ? held : 0);
    }, 50);
};

function finishSustainRound(held) {
    clearInterval(sustain.mic.timer);
    sustain.running = false;
    const vol = document.getElementById('sus-vol');
    if (vol) vol.style.width = '0%';
    const btn = document.getElementById('sus-go');
    if (!held) {                           // no se oyó nada: la ronda no cuenta, se repite
        feedback('sus-feedback', 'No te oí. Acércate al micrófono y prueba otra vez.', false);
        btn.disabled = false;
        return;
    }
    sustain.held.push(held);
    feedback('sus-feedback', held >= sustain.target ? `¡Llegaste a la meta! Aguantaste ${seconds(held)} segundos.`
        : `Aguantaste ${seconds(held)} segundos. ¡Cada vez un poco más!`, true);
    btn.dataset.next = '1';
    btn.disabled = false;
    btn.textContent = sustain.round >= SUSTAIN_ROUNDS ? 'Terminar' : 'Siguiente';
    btn.focus();
}

function stopSustain() {
    if (!sustain || !sustain.mic) return;
    clearInterval(sustain.mic.timer);
    sustain.mic.meter.close();
    sustain.mic.stream.getTracks().forEach((t) => t.stop());
    sustain.mic = null;
    sustain.running = false;
}

function endSustain() {
    const { held, target } = sustain;
    const started = sustain.started;
    stopSustain();
    const best = Math.max(...held);
    const reached = held.filter((h) => h >= target).length;
    const score = held.reduce((sum, h) => sum + Math.min(1, h / target), 0) / held.length * 100;
    showEnd('sustain', {
        emoji: reached >= 3 ? '🏆' : '⛵', title: '¡Buen trabajo!',
        lines: [`Tu voz más larga: <strong>${seconds(best)} segundos</strong>.`,
                `Llegaste a la meta <strong>${reached} de ${held.length}</strong> veces.`],
        score, details: { target_s: target / 1000, best_s: Math.round(best / 100) / 10, reached, rounds: held.length, duration_ms: Date.now() - started },
    });
}

// =============== 4. Completa la frase (y dila entera) ===============
// Las opciones incorrectas no encajan con la frase (ni por sentido ni por gramática).
const PHRASES = [
    { text: 'Tengo sed, quiero un vaso de ___', correct: 'agua', wrongs: ['zapato', 'lunes'] },
    { text: 'Me duele la ___', correct: 'cabeza', wrongs: ['feliz', 'verde'] },
    { text: 'Necesito ir al ___', correct: 'baño', wrongs: ['azul', 'comer'] },
    { text: 'Hoy estoy muy ___', correct: 'feliz', wrongs: ['zapato', 'mesa'] },
    { text: 'Buenas ___', correct: 'noches', wrongs: ['comer', 'azul'] },
    { text: 'Para dormir me acuesto en la ___', correct: 'cama', wrongs: ['sopa', 'nube'] },
    { text: 'Me lavo las manos con agua y ___', correct: 'jabón', wrongs: ['pelota', 'lunes'] },
    { text: 'El cielo es de color ___', correct: 'azul', wrongs: ['silla', 'pan'] },
    { text: 'Por la mañana tomo café con ___', correct: 'leche', wrongs: ['zapato', 'llave'] },
    { text: 'Me pongo los zapatos en los ___', correct: 'pies', wrongs: ['ojos', 'platos'] },
    { text: 'Para ver bien me pongo los ___', correct: 'lentes', wrongs: ['zapatos', 'platos'] },
    { text: 'Abro la puerta con la ___', correct: 'llave', wrongs: ['sopa', 'nube'] },
    { text: 'El perro hace ___', correct: 'guau', wrongs: ['miau', 'pan'] },
    { text: 'El gato hace ___', correct: 'miau', wrongs: ['guau', 'mesa'] },
    { text: 'Uno, dos, ___', correct: 'tres', wrongs: ['rojo', 'casa'] },
    { text: 'Muchas ___', correct: 'gracias', wrongs: ['silla', 'perro'] },
    { text: 'Tengo hambre, quiero ___', correct: 'comer', wrongs: ['zapato', 'azul'] },
    { text: 'Hablo con mi hija por ___', correct: 'teléfono', wrongs: ['cuchara', 'nube'] },
    { text: 'Después del lunes viene el ___', correct: 'martes', wrongs: ['verde', 'pan'] },
    { text: 'Tengo frío, me pongo el ___', correct: 'abrigo', wrongs: ['plato', 'gato'] },
    { text: 'Para comer sopa uso la ___', correct: 'cuchara', wrongs: ['almohada', 'llave'] },
    { text: 'En invierno hace ___', correct: 'frío', wrongs: ['mesa', 'leche'] },
    { text: 'Me seco con la ___', correct: 'toalla', wrongs: ['ventana', 'sopa'] },
    { text: 'Me siento en la ___', correct: 'silla', wrongs: ['leche', 'nube'] },
    { text: 'Bebo el café en una ___', correct: 'taza', wrongs: ['cama', 'llave'] },
    { text: 'Por la noche sale la ___', correct: 'luna', wrongs: ['mesa', 'sopa'] },
    { text: 'Me lavo los dientes con el ___', correct: 'cepillo', wrongs: ['zapato', 'plato'] },
    { text: 'Para saber la hora miro el ___', correct: 'reloj', wrongs: ['pan', 'gato'] },
];
const PHRASE_ROUNDS = 6;
let phrase = null;

function startCompletePhrase(level) {
    phrase = { level, round: 0, firstTry: 0, spoken: 0, queue: shuffle(PHRASES).slice(0, PHRASE_ROUNDS), started: Date.now() };
    nextPhraseRound();
}

function nextPhraseRound() {
    phrase.current = phrase.queue[phrase.round];
    phrase.round++;
    phrase.missed = false;
    const p = phrase.current;
    const [before, after] = p.text.split('___');
    const wrongs = [...p.wrongs];
    if (phrase.level === 1) wrongs.length = 1;
    if (phrase.level >= 3) {
        const [extra] = pickWords(easyWords(), 1, new Set([p.correct, ...p.wrongs].map(norm)));
        if (extra) wrongs.push(extra.word);
    }
    const options = shuffle([p.correct, ...wrongs]);
    content().innerHTML = `
        <div class="text-center w-full max-w-2xl">
            ${roundHeader(phrase.round, PHRASE_ROUNDS)}
            <p id="phrase-task" class="text-gray-700 text-lg mb-4">Elige la palabra que falta:</p>
            <div class="bg-orange-50 rounded-2xl p-6 mb-6 shadow-sm">
                <span class="text-2xl md:text-3xl font-medium text-gray-800">${esc(before)}<span id="phrase-gap" class="border-b-4 border-orange-400 px-3 text-orange-700 font-bold">?</span>${esc(after || '')}</span>
            </div>
            <div id="phrase-options" class="grid grid-cols-1 ${options.length === 2 ? 'md:grid-cols-2' : options.length === 3 ? 'md:grid-cols-3' : 'md:grid-cols-4'} gap-4">
                ${options.map((o) => `
                    <button data-action="phrase" data-word="${esc(o)}"
                        class="bg-white border-2 border-gray-200 hover:border-orange-400 shadow-sm p-5 rounded-2xl transition text-xl font-bold">
                        ${esc(o)}
                    </button>`).join('')}
            </div>
            <div id="phrase-feedback" class="${FEEDBACK_BOX}" aria-live="polite"></div>
            <div id="phrase-say"></div>
        </div>`;
}

ACTIONS.phrase = (btn) => {
    const p = phrase.current;
    const ok = btn.dataset.word === p.correct;
    markAnswer(btn, ok, document.getElementById('phrase-options'));
    if (!ok) {
        phrase.missed = true;
        feedback('phrase-feedback', 'Casi… prueba con otra.', false);
        return;
    }
    if (!phrase.missed) phrase.firstTry++;
    document.getElementById('phrase-gap').textContent = p.correct;
    const full = p.text.replace('___', p.correct);
    say(full);
    playSound(full);                         // se oye la frase completa: refuerza lo aprendido
    // Ahora, a decirla: es lo que convierte el acierto en habla
    document.getElementById('phrase-options').classList.add('hidden');
    document.getElementById('phrase-feedback').textContent = '';
    document.getElementById('phrase-task').textContent = '¡Eso es! Ahora di tú la frase entera:';
    document.getElementById('phrase-say').innerHTML = sayPanel({ okLabel: 'La dije', skipLabel: 'Seguir' });
    expectSpeech(p.correct, (said) => {
        if (said) phrase.spoken++;
        feedback('say-feedback', said ? '¡Muy bien dicha!' : '', true);
        later(() => (phrase.round >= PHRASE_ROUNDS ? endCompletePhrase() : nextPhraseRound()), said ? 1200 : 300);
    });
};

function endCompletePhrase() {
    const pct = (phrase.firstTry / PHRASE_ROUNDS) * 100;
    showEnd('complete_phrase', {
        emoji: pct >= 75 ? '🏆' : '👏', title: '¡Partida terminada!',
        lines: [`Completaste <strong>${phrase.firstTry} de ${PHRASE_ROUNDS}</strong> frases a la primera.`,
                `Dijiste en voz alta <strong>${phrase.spoken}</strong>.`],
        score: pct, details: { first_try: phrase.firstTry, spoken: phrase.spoken, rounds: PHRASE_ROUNDS, duration_ms: Date.now() - phrase.started },
    });
}

// =============== 5. Escucha y elige ===============
const MATCH_ROUNDS = 8;
let match = null;

function startWordMatch(level) {
    if (easyWords().length < 4) { notEnough(); return; }
    match = { level, round: 0, firstTry: 0, used: new Set(), started: Date.now() };
    nextMatchRound();
}

/** Opciones incorrectas. Nivel 3: del mismo grupo o que suenan parecido (cuesta más distinguirlas) */
function matchDistractors(target, level) {
    const others = easyWords().filter((w) => w.key !== target.key);
    const avoid = new Set([target.key]);
    if (level === 1) return pickWords(others.filter((w) => w.category_id !== target.category_id), 2, avoid);
    if (level === 2) return pickWords(others, 3, avoid);
    const sameGroup = pickWords(others.filter((w) => w.category_id === target.category_id), 2, avoid);
    sameGroup.forEach((w) => avoid.add(w.key));
    const alike = pickWords(others.filter((w) => w.key[0] === target.key[0] || lev(w.key, target.key) <= 2), 1, avoid);
    alike.forEach((w) => avoid.add(w.key));
    const chosen = [...sameGroup, ...alike];
    return [...chosen, ...pickWords(others, 3 - chosen.length, avoid)];
}

function nextMatchRound() {
    match.round++;
    // Preferir palabras con pictograma: ayudan a quien tiene dificultades para leer
    const candidates = withPicture(easyWords());
    const target = pickFresh(candidates.length >= MATCH_ROUNDS ? candidates : easyWords(), match.used);
    match.used.add(target.key);
    match.target = target;
    match.missed = false;
    const options = shuffle([target, ...matchDistractors(target, match.level)]);
    content().innerHTML = `
        <div class="text-center w-full max-w-2xl">
            ${roundHeader(match.round, MATCH_ROUNDS)}
            <p class="text-gray-700 text-lg mb-4">Escucha la palabra y elige la correcta:</p>
            <button data-action="speak" data-text="${esc(target.word)}" class="bg-blue-700 text-white px-6 py-4 rounded-2xl text-xl font-semibold shadow-lg hover:bg-blue-800 transition mb-6">
                <i class="fas fa-volume-high mr-2"></i>Escuchar otra vez
            </button>
            <div id="match-options" class="grid ${options.length === 3 ? 'grid-cols-3' : 'grid-cols-2'} gap-4">
                ${options.map((o) => `
                    <button data-action="match" data-key="${esc(o.key)}"
                        class="bg-gray-50 border-2 border-gray-200 hover:border-primary p-4 rounded-2xl transition text-xl font-semibold capitalize">
                        ${picture(o)}${esc(o.word)}
                    </button>`).join('')}
            </div>
            <div id="match-feedback" class="${FEEDBACK_BOX}" aria-live="polite"></div>
        </div>`;
    later(() => playSound(target.word), 400);
}

ACTIONS.match = (btn) => {
    const ok = btn.dataset.key === match.target.key;
    markAnswer(btn, ok, document.getElementById('match-options'));
    if (ok) {
        if (!match.missed) match.firstTry++;
        feedback('match-feedback', '¡Correcto!', true);
        later(() => (match.round >= MATCH_ROUNDS ? endWordMatch() : nextMatchRound()), 1400);
    } else {
        match.missed = true;
        feedback('match-feedback', 'Escucha otra vez y prueba con otra.', false);
        playSound(match.target.word);
    }
};

function endWordMatch() {
    const pct = (match.firstTry / MATCH_ROUNDS) * 100;
    showEnd('word_match', {
        emoji: pct >= 75 ? '🏆' : '👏', title: '¡Partida terminada!',
        lines: [`Acertaste <strong>${match.firstTry} de ${MATCH_ROUNDS}</strong> a la primera.`],
        score: pct, details: { first_try: match.firstTry, rounds: MATCH_ROUNDS, duration_ms: Date.now() - match.started },
    });
}

// =============== 6. Palabras parecidas (pares mínimos) ===============
// Pares que se distinguen igual en España y en América (nada de «casa/caza»).
const MIN_PAIRS = {
    vowel: [['mesa', 'misa'], ['peso', 'piso'], ['mano', 'mono'], ['dedo', 'dado'], ['pelo', 'palo'], ['casa', 'cosa'],
            ['luna', 'lana'], ['sol', 'sal'], ['toro', 'tiro'], ['paso', 'peso'], ['pesa', 'pisa'], ['nido', 'nudo']],
    consonant: [['pato', 'gato'], ['pala', 'bala'], ['peso', 'beso'], ['boca', 'foca'], ['tía', 'día'], ['rana', 'lana'],
                ['sopa', 'ropa'], ['toro', 'coro'], ['cama', 'cana'], ['pera', 'perra'], ['caro', 'carro'], ['gol', 'col'],
                ['bota', 'gota'], ['foca', 'roca'], ['cuna', 'luna'], ['mesa', 'pesa']],
};
const PAIR_ROUNDS = 8;
let minPairs = null;

function startMinPairs(level) {
    const source = level === 1 ? MIN_PAIRS.vowel : level === 2 ? MIN_PAIRS.consonant : [...MIN_PAIRS.vowel, ...MIN_PAIRS.consonant];
    minPairs = { level, round: 0, good: 0, queue: shuffle(source).slice(0, PAIR_ROUNDS), started: Date.now() };
    nextMinPairRound();
}

function pairCard(text, action) {
    return `<button data-action="${action}" data-text="${esc(text)}"
        class="bg-gray-50 border-2 border-gray-200 hover:border-violet-500 p-5 rounded-2xl transition text-2xl font-bold capitalize">
        ${picture(wordByKey(text))}${esc(text)}</button>`;
}

function nextMinPairRound() {
    const pair = shuffle(minPairs.queue[minPairs.round]);
    minPairs.round++;
    minPairs.pair = pair;
    minPairs.answered = false;
    const sameDifferent = minPairs.level === 3;
    if (sameDifferent) minPairs.spoken = Math.random() < 0.5 ? [pair[0], pair[0]] : [pair[0], pair[1]];
    else minPairs.spoken = [pair[Math.floor(Math.random() * 2)]];
    content().innerHTML = `
        <div class="text-center w-full max-w-2xl">
            ${roundHeader(minPairs.round, PAIR_ROUNDS)}
            <p class="text-gray-700 text-lg mb-4">${sameDifferent ? 'Vas a oír dos palabras. ¿Son iguales o distintas?' : 'Escucha con atención. ¿Qué palabra has oído?'}</p>
            <button data-action="pair-listen" class="bg-violet-700 text-white px-6 py-4 rounded-2xl text-xl font-semibold shadow-lg hover:bg-violet-800 transition mb-6">
                <i class="fas fa-volume-high mr-2"></i>Escuchar otra vez
            </button>
            <div id="pair-options" class="grid grid-cols-2 gap-4">
                ${sameDifferent
                    ? `<button data-action="pair-same" data-same="1" class="bg-gray-50 border-2 border-gray-200 hover:border-violet-500 p-6 rounded-2xl transition text-2xl font-bold">Iguales</button>
                       <button data-action="pair-same" data-same="0" class="bg-gray-50 border-2 border-gray-200 hover:border-violet-500 p-6 rounded-2xl transition text-2xl font-bold">Distintas</button>`
                    : pair.map((w) => pairCard(w, 'pair-pick')).join('')}
            </div>
            <div id="pair-feedback" class="${FEEDBACK_BOX}" aria-live="polite"></div>
            <div id="pair-after"></div>
        </div>`;
    later(playMinPair, 500);
}

async function playMinPair() {
    const s = session;
    const [first, second] = minPairs.spoken;
    await speakAndWait(first);
    if (!second || s !== session) return;
    await wait(500);
    playSound(second);
}
ACTIONS['pair-listen'] = () => { playMinPair(); };

function answerMinPair(ok, btn, right) {
    if (minPairs.answered) return;
    minPairs.answered = true;
    if (ok) minPairs.good++;
    const group = document.getElementById('pair-options');
    group.querySelectorAll('button').forEach((b) => { b.disabled = true; });
    if (right) right.classList.add('!bg-green-100', '!border-green-600', 'text-green-800');
    if (!ok && btn) btn.classList.add('opacity-40', '!border-dashed');
    const [a, b] = minPairs.pair;
    const heard = minPairs.spoken.length === 2
        ? (minPairs.spoken[0] === minPairs.spoken[1] ? `Eran iguales: «${a}» y «${a}».` : `Eran distintas: «${a}» y «${b}».`)
        : `Era «${minPairs.spoken[0]}».`;
    feedback('pair-feedback', ok ? `¡Correcto! ${heard}` : heard, ok ? true : null);
    // Sin prisa: se pueden oír las dos y decirlas antes de seguir
    document.getElementById('pair-after').innerHTML = `
        <p class="text-gray-700 text-lg mt-4 mb-3">Escúchalas y dilas tú:</p>
        <div class="flex flex-wrap justify-center gap-3 mb-5">
            ${[a, b].map((w) => `<button data-action="speak" data-text="${esc(w)}" class="bg-white border-2 border-violet-300 text-violet-800 px-5 py-3 rounded-2xl text-xl font-bold hover:bg-violet-50 transition capitalize"><i class="fas fa-volume-high mr-2"></i>${esc(w)}</button>`).join('')}
        </div>
        <button data-action="pair-next" id="pair-next" class="bg-primary text-white px-8 py-4 rounded-xl text-lg font-semibold hover:bg-secondary transition">${minPairs.round >= PAIR_ROUNDS ? 'Terminar' : 'Siguiente'}</button>`;
    document.getElementById('pair-next').focus();
}

ACTIONS['pair-pick'] = (btn) => {
    const target = minPairs.spoken[0];
    const right = [...document.querySelectorAll('#pair-options button')].find((b) => b.dataset.text === target);
    answerMinPair(btn.dataset.text === target, btn, right);
};
ACTIONS['pair-same'] = (btn) => {
    const same = minPairs.spoken[0] === minPairs.spoken[1];
    const right = [...document.querySelectorAll('#pair-options button')].find((b) => (b.dataset.same === '1') === same);
    answerMinPair((btn.dataset.same === '1') === same, btn, right);
};
ACTIONS['pair-next'] = () => (minPairs.round >= PAIR_ROUNDS ? endMinPairs() : nextMinPairRound());

function endMinPairs() {
    const pct = (minPairs.good / PAIR_ROUNDS) * 100;
    showEnd('min_pairs', {
        emoji: pct >= 75 ? '🏆' : '👂', title: '¡Partida terminada!',
        lines: [`Distinguiste <strong>${minPairs.good} de ${PAIR_ROUNDS}</strong>.`],
        score: pct, details: { correct: minPairs.good, rounds: PAIR_ROUNDS, duration_ms: Date.now() - minPairs.started },
    });
}

// =============== 7. Clasificar: ¿a qué grupo pertenece? / ¿cuál no pertenece? ===============
const SORT_ROUNDS = 8;
let sort = null;

const sortable = (w) => !w.multi && !w.ambiguous && w.level <= 3;
function sortableCategories() {
    return pool.categories.filter((c) => !SORT_EXCLUDED.includes(c.id)
        && pool.words.filter((w) => w.category_id === c.id && sortable(w)).length >= 3);
}

function startCategorySort(level) {
    if (sortableCategories().length < 3) { notEnough(); return; }
    sort = { level, round: 0, firstTry: 0, used: new Set(), started: Date.now() };
    nextSortRound();
}

function nextSortRound() {
    sort.round++;
    sort.missed = false;
    if (sort.level === 3 && sort.round % 2 === 0) { oddOneOutRound(); return; }
    const cats = sortableCategories();
    const catIds = new Set(cats.map((c) => c.id));
    const item = pickFresh(pool.words.filter((w) => catIds.has(w.category_id) && sortable(w)), sort.used);
    sort.used.add(item.key);
    sort.answer = item.category_id;
    const correct = cats.find((c) => c.id === item.category_id);
    const options = shuffle([correct, ...shuffle(cats.filter((c) => c.id !== item.category_id)).slice(0, sort.level === 1 ? 1 : 2)]);
    content().innerHTML = `
        <div class="text-center w-full max-w-2xl">
            ${roundHeader(sort.round, SORT_ROUNDS)}
            <p class="text-gray-700 text-lg mb-4">¿A qué grupo pertenece esta palabra?</p>
            <button data-action="speak" data-text="${esc(item.word)}" class="bg-blue-50 rounded-2xl px-10 py-6 mb-6 inline-block shadow-sm hover:bg-blue-100 transition" aria-label="Escuchar ${esc(item.word)}">
                ${picture(item, 'w-24 h-24')}
                <span class="block text-4xl font-bold text-gray-800 capitalize">${esc(item.word)}</span>
                <span class="block text-sm text-blue-700 mt-2"><i class="fas fa-volume-high mr-1"></i>Escuchar</span>
            </button>
            <div id="sort-options" class="grid grid-cols-1 ${options.length === 2 ? 'md:grid-cols-2' : 'md:grid-cols-3'} gap-4">
                ${options.map((c) => `
                    <button data-action="sort" data-answer="${esc(c.id)}"
                        class="bg-gray-50 border-2 border-gray-200 hover:border-green-600 p-5 rounded-2xl transition text-xl font-semibold">
                        <span class="text-3xl block mb-1">${esc(c.icon)}</span>${esc(c.name)}
                    </button>`).join('')}
            </div>
            <div id="sort-feedback" class="${FEEDBACK_BOX}" aria-live="polite"></div>
        </div>`;
}

/** Tres palabras de un grupo y una de otro: tocar la que sobra */
function oddOneOutRound() {
    const cats = shuffle(sortableCategories());
    const [group, other] = cats;
    const members = pickWords(pool.words.filter((w) => w.category_id === group.id && sortable(w)), 3);
    const [intruder] = pickWords(pool.words.filter((w) => w.category_id === other.id && sortable(w)), 1);
    sort.answer = intruder.key;
    sort.oddNote = `«${intruder.word}» no es de ${group.name}.`;
    content().innerHTML = `
        <div class="text-center w-full max-w-2xl">
            ${roundHeader(sort.round, SORT_ROUNDS)}
            <p class="text-gray-700 text-lg mb-4">Tres van juntas. ¿Cuál <strong>no pertenece</strong> al grupo?</p>
            <div id="sort-options" class="grid grid-cols-2 gap-4">
                ${shuffle([...members, intruder]).map((w) => `
                    <button data-action="sort" data-answer="${esc(w.key)}"
                        class="bg-gray-50 border-2 border-gray-200 hover:border-green-600 p-4 rounded-2xl transition text-xl font-semibold capitalize">
                        ${picture(w)}${esc(w.word)}
                    </button>`).join('')}
            </div>
            <div id="sort-feedback" class="${FEEDBACK_BOX}" aria-live="polite"></div>
        </div>`;
}

ACTIONS.sort = (btn) => {
    const ok = btn.dataset.answer === sort.answer;
    const odd = sort.level === 3 && sort.round % 2 === 0;
    markAnswer(btn, ok, document.getElementById('sort-options'));
    if (ok) {
        if (!sort.missed) sort.firstTry++;
        feedback('sort-feedback', odd ? `¡Correcto! ${sort.oddNote}` : '¡Correcto!', true);
        later(() => (sort.round >= SORT_ROUNDS ? endCategorySort() : nextSortRound()), odd ? 2200 : 1400);
    } else {
        sort.missed = true;
        feedback('sort-feedback', odd ? 'Esa va con las demás. Prueba con otra.' : 'Prueba con otro grupo.', false);
    }
};

function endCategorySort() {
    const pct = (sort.firstTry / SORT_ROUNDS) * 100;
    showEnd('category_sort', {
        emoji: pct >= 75 ? '🏆' : '👏', title: '¡Partida terminada!',
        lines: [`Acertaste <strong>${sort.firstTry} de ${SORT_ROUNDS}</strong> a la primera.`],
        score: pct, details: { first_try: sort.firstTry, rounds: SORT_ROUNDS, duration_ms: Date.now() - sort.started },
    });
}

// =============== 8. Parejas de pictogramas ===============
const PAIR_COUNTS = [3, 4, 6];         // parejas por nivel
let pairs = null;

function startPairs(level) {
    const words = pickWords(withPicture(easyWords()), PAIR_COUNTS[level - 1]);
    if (words.length < PAIR_COUNTS[level - 1]) { notEnough(); return; }
    pairs = { cards: shuffle([...words, ...words]).map((word) => ({ word, open: false, found: false })),
              total: words.length, found: 0, turns: 0, open: [], locked: false, started: Date.now() };
    content().innerHTML = `
        <div class="text-center w-full max-w-2xl">
            <p class="text-gray-700 text-lg mb-4">Levanta dos cartas. Si son iguales, di la palabra en voz alta.</p>
            <div id="pairs-grid" class="grid ${pairs.cards.length === 6 ? 'grid-cols-3' : 'grid-cols-4'} gap-3">
                ${pairs.cards.map((_, i) => `<button data-action="pair-flip" data-i="${i}" class="h-28 md:h-32 rounded-2xl border-2 transition flex flex-col items-center justify-center font-semibold"></button>`).join('')}
            </div>
            <div id="pairs-feedback" class="${FEEDBACK_BOX}" aria-live="polite"></div>
        </div>`;
    pairs.cards.forEach((_, i) => paintCard(i));
}

function paintCard(i) {
    const card = pairs.cards[i];
    const btn = content().querySelector(`[data-i="${i}"]`);
    if (!btn) return;
    const shown = card.open || card.found;
    btn.className = 'h-28 md:h-32 rounded-2xl border-2 transition flex flex-col items-center justify-center font-semibold '
        + (card.found ? 'bg-green-100 border-green-600 text-green-800' : shown ? 'bg-white border-purple-500 text-gray-800' : 'bg-purple-700 border-purple-700 text-white hover:bg-purple-800');
    btn.innerHTML = shown
        ? `${picture(card.word, 'w-14 h-14 md:w-16 md:h-16')}<span class="text-sm md:text-base capitalize">${esc(card.word.word)}</span>`
        : '<span class="text-4xl" aria-hidden="true">?</span>';
    btn.setAttribute('aria-label', shown ? card.word.word + (card.found ? ', pareja encontrada' : '') : `Carta ${i + 1}, boca abajo`);
    btn.disabled = card.found;
}

ACTIONS['pair-flip'] = (btn) => {
    const i = Number(btn.dataset.i);
    const card = pairs.cards[i];
    if (pairs.locked || card.open || card.found) return;
    card.open = true;
    paintCard(i);
    playSound(card.word.word);
    pairs.open.push(i);
    if (pairs.open.length < 2) { say(card.word.word); return; }
    pairs.turns++;
    const [a, b] = pairs.open;
    pairs.open = [];
    if (pairs.cards[a].word.key === pairs.cards[b].word.key) {
        for (const k of [a, b]) { pairs.cards[k].found = true; pairs.cards[k].open = false; paintCard(k); }
        pairs.found++;
        feedback('pairs-feedback', `¡Pareja! Di en voz alta: «${card.word.word}».`, true);
        if (pairs.found === pairs.total) later(endPairs, 2200);
    } else {
        pairs.locked = true;
        feedback('pairs-feedback', `«${pairs.cards[a].word.word}» y «${pairs.cards[b].word.word}»: son distintas. Sigue buscando.`, null);
        later(() => {
            for (const k of [a, b]) { pairs.cards[k].open = false; paintCard(k); }
            pairs.locked = false;
        }, 2000);
    }
};

function endPairs() {
    // Sin fallar ninguna harían falta tantos turnos como parejas; hasta el doble es una partida redonda
    const score = Math.min(100, (2 * pairs.total / pairs.turns) * 100);
    showEnd('pairs', {
        emoji: '🏆', title: '¡Todas las parejas!',
        lines: [`Encontraste <strong>${pairs.total} parejas</strong> en ${pairs.turns} turnos.`],
        score, details: { pairs: pairs.total, turns: pairs.turns, duration_ms: Date.now() - pairs.started },
    });
}

// =============== 9. Laberinto de voz ===============
// 0 = camino, 1 = árbol. El mono sale de arriba a la izquierda y la banana está abajo a la derecha.
const MAZES = [
    [[0, 0, 1, 0, 0],
     [0, 1, 1, 0, 0],
     [0, 0, 0, 1, 0],
     [1, 1, 0, 0, 0],
     [0, 0, 0, 1, 0]],
    [[0, 0, 0, 0, 1],
     [1, 1, 1, 0, 1],
     [0, 0, 0, 0, 0],
     [0, 1, 1, 1, 0],
     [0, 0, 0, 1, 0]],
    [[0, 1, 0, 0, 0],
     [0, 1, 0, 1, 0],
     [0, 0, 0, 1, 0],
     [1, 1, 1, 1, 0],
     [0, 0, 0, 0, 0]],
];
const DIRECTIONS = {
    arriba: { dx: 0, dy: -1, label: 'Arriba', rotate: -90, words: ['arriba', 'riba', 'sube', 'subir', 'arriva'] },
    abajo: { dx: 0, dy: 1, label: 'Abajo', rotate: 90, words: ['abajo', 'bajo', 'baja', 'bajar', 'abaja'] },
    izquierda: { dx: -1, dy: 0, label: 'Izquierda', rotate: 180, words: ['izquierda', 'izquierdo', 'isquierda'] },
    derecha: { dx: 1, dy: 0, label: 'Derecha', rotate: 0, words: ['derecha', 'derecho', 'drecha'] },
};
// Flecha dibujada (el subconjunto de iconos solo trae la flecha a la derecha)
const ARROW_SVG = (deg) => `<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="transform: rotate(${deg}deg)"><path d="M4 12h15M13 6l6 6-6 6"/></svg>`;
let maze = null;

/** which: qué laberinto (este juego no tiene niveles de dificultad) */
function startMazeGame(which = 1) {
    const index = (which - 1) % MAZES.length;
    maze = { index, grid: MAZES[index], x: 0, y: 0, moves: 0, started: Date.now() };
    keyHandler = (e) => {
        const map = { ArrowUp: 'arriba', ArrowDown: 'abajo', ArrowLeft: 'izquierda', ArrowRight: 'derecha' };
        if (map[e.key]) { e.preventDefault(); moveMaze(map[e.key]); }
    };
    renderMaze('Di una dirección o usa las flechas.');
}

function renderMaze(message) {
    const size = maze.grid.length;
    let cells = '';
    for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
            let cls = 'bg-gray-100', inner = '';
            if (x === maze.x && y === maze.y) { cls = 'bg-blue-100 border-2 border-blue-500'; inner = '🐵'; }
            else if (x === size - 1 && y === size - 1) { cls = 'bg-yellow-100 border-2 border-yellow-400'; inner = '🍌'; }
            else if (maze.grid[y][x] === 1) { cls = 'bg-green-800'; inner = '🌴'; }
            cells += `<div class="w-12 h-12 md:w-16 md:h-16 rounded-lg ${cls} flex items-center justify-center text-2xl select-none" aria-hidden="true">${inner}</div>`;
        }
    }
    const recording = !!rec;
    const arrow = (d) => `<button data-action="maze-move" data-dir="${d}" aria-label="${DIRECTIONS[d].label}"
        class="w-16 h-16 rounded-2xl bg-white border-2 border-teal-200 text-teal-700 hover:bg-teal-50 flex items-center justify-center">${ARROW_SVG(DIRECTIONS[d].rotate)}</button>`;
    content().innerHTML = `
        <div class="flex flex-col items-center">
            <p class="text-gray-700 text-lg mb-1">Ayuda al mono a llegar a la banana. <span class="text-gray-600">Laberinto ${maze.index + 1} de ${MAZES.length}</span></p>
            <p class="text-gray-600 mb-3">Movimientos: <strong>${maze.moves}</strong></p>
            <div class="grid grid-cols-5 gap-2 mb-4 p-3 bg-white rounded-xl shadow-inner border border-gray-100">${cells}</div>
            <div id="maze-feedback" class="min-h-[2rem] font-bold text-lg text-teal-700 text-center mb-3" aria-live="polite">${esc(message)}</div>
            <div class="flex flex-wrap items-center justify-center gap-6">
                <button data-action="maze-mic" aria-label="${recording ? 'Detener' : 'Decir una dirección'}"
                    class="${recording ? 'bg-red-700' : 'bg-teal-700'} text-white w-24 h-24 rounded-full text-4xl shadow-lg hover:opacity-90 transition flex items-center justify-center">
                    <i class="fas ${recording ? 'fa-stop' : 'fa-microphone'}"></i>
                </button>
                <div class="grid grid-cols-3 gap-2" role="group" aria-label="Flechas">
                    <span></span>${arrow('arriba')}<span></span>
                    ${arrow('izquierda')}${arrow('abajo')}${arrow('derecha')}
                </div>
            </div>
            <p class="text-sm text-gray-600 mt-3">Pulsa el micrófono y di: Arriba, Abajo, Izquierda o Derecha.</p>
        </div>`;
}

ACTIONS['maze-move'] = (btn) => moveMaze(btn.dataset.dir);

function moveMaze(dir) {
    const d = DIRECTIONS[dir];
    if (!d || !maze || maze.done) return;
    const size = maze.grid.length;
    const nx = maze.x + d.dx, ny = maze.y + d.dy;
    if (nx < 0 || ny < 0 || nx >= size || ny >= size) { renderMaze(`Por ahí no se puede salir (${d.label}) 🧱`); return; }
    if (maze.grid[ny][nx] === 1) { renderMaze(`Hay un árbol hacia ${d.label.toLowerCase()} 🌴`); return; }
    maze.x = nx; maze.y = ny; maze.moves++;
    if (nx === size - 1 && ny === size - 1) {
        maze.done = true;
        keyHandler = null;
        renderMaze('¡Llegaste a la banana! 🎉');
        say('¡Llegaste a la banana!');
        later(() => endMaze(), 1200);
    } else {
        renderMaze(`${d.label} ✅`);
    }
}

function endMaze() {
    const next = maze.index + 2;           // número (desde 1) del laberinto siguiente
    showEnd('maze', {
        emoji: '🏆', title: '¡Laberinto completado!',
        lines: [`Lo hiciste en <strong>${maze.moves}</strong> movimientos.`],
        score: 100, details: { maze: maze.index + 1, moves: maze.moves, duration_ms: Date.now() - maze.started },
    }).then(() => {
        const again = content().querySelector('[data-action="restart"]');
        if (!again) return;
        if (next <= MAZES.length) { again.textContent = 'Siguiente laberinto'; again.dataset.level = String(next); }
        else again.dataset.level = '1';
    });
}

/** Interpreta lo transcrito: admite variantes y pequeños errores («isquierda», «derecho») */
function parseDirection(text) {
    const tokens = norm(text).split(' ');
    for (const token of tokens) {
        for (const [dir, d] of Object.entries(DIRECTIONS)) {
            if (d.words.includes(token)) return dir;
        }
    }
    for (const token of tokens) {
        if (token.length < 4) continue;
        for (const dir of Object.keys(DIRECTIONS)) {
            if (lev(token, dir) <= (dir.length >= 7 ? 2 : 1)) return dir;
        }
    }
    return null;
}

ACTIONS['maze-mic'] = async () => {
    if (rec) { stopListening(false, true); return; }
    const playing = maze;
    const res = await listen({
        prompt: 'Arriba. Abajo. Izquierda. Derecha.', maxMs: 4000,
        onState: (state) => renderMaze(state === 'listening' ? 'Te escucho…' : 'Entendiendo…'),
    });
    if (!res || maze !== playing || maze.done) return;
    if (res.error) { renderMaze(`${MIC_ERRORS[res.error]} Puedes usar las flechas.`); return; }
    const dir = parseDirection(res.text);
    if (dir) moveMaze(dir);
    else renderMaze(res.text ? `Oí «${res.text}». Di: Arriba, Abajo, Izquierda o Derecha.` : 'No te entendí. Inténtalo otra vez.');
};

// ---------- inicio ----------
document.addEventListener('DOMContentLoaded', () => {
    renderCards();
    loadSummary();
    loadPlayerLevel();
    loadDailyChallenge();
    loadAchievements();
    loadReview();
    ensurePool().catch((e) => console.warn('No se pudieron cargar las palabras de los juegos:', e));
});
