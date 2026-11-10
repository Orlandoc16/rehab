// Juegos de la página /games (cargado desde templates/games.html).
//
// Principios:
// - Cada partida tiene varias rondas y se guarda UNA vez al terminar, con el identificador del
//   juego (game_match, game_sort...). Nunca con el de una palabra: un clic en «agua» no es una
//   pronunciación y falsearía el progreso y la repetición espaciada de la práctica.
// - Al cerrar el juego se cancela todo lo pendiente (temporizadores, audio, micrófono): nada
//   sigue sonando ni empieza una ronda nueva con la ventana cerrada.
// - Botones grandes, sin animaciones que distraigan, con pictograma cuando la palabra lo tiene.
// - La voz del laberinto se reconoce en NUESTRO servidor (como la práctica), no en Google.

/* global playVoice, anunciar */

const GAME_IDS = {
    word_match: 'game_match', category_sort: 'game_sort', complete_phrase: 'game_phrase',
    speed_round: 'game_speed', memory: 'game_memory', maze: 'game_maze',
};
// Grupos que no sirven para los juegos de palabras sueltas (frases largas, metajuegos) o que se
// solapan con otros al clasificar («agua» es necesidad básica y bebida a la vez).
const EXCLUDED_CATEGORIES = ['games_cat', 'phrases'];
const SORT_EXCLUDED = ['basic_needs', 'time'];

const pool = { words: [], categories: [], ready: null };
let session = 0;                       // cambia al abrir/cerrar: invalida lo que quedara pendiente
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

/** setTimeout que no se ejecuta si el juego se cerró o cambió entretanto */
function later(fn, ms) {
    const s = session;
    const id = setTimeout(() => { timers.delete(id); if (s === session) fn(); }, ms);
    timers.add(id);
}
const wait = (ms) => new Promise((resolve) => later(resolve, ms));

function playSound(text) {
    if (typeof playVoice === 'function') playVoice(gameAudio, `/api/speak/${encodeURIComponent(text)}`, text);
}
function stopSound() {
    gameAudio.pause();
    if ('speechSynthesis' in window) speechSynthesis.cancel();
}
function say(text) { if (typeof anunciar === 'function') anunciar(text); }

/** Palabras sueltas y fáciles (las de varias palabras se dejan para la práctica) */
function easyWords(maxLevel = 2) {
    return pool.words.filter((w) => !w.multi && w.level <= maxLevel);
}
/** Elige n palabras distintas (por texto), sin repetir las de `avoid` */
function pickWords(list, n, avoid = new Set()) {
    const out = [];
    const seen = new Set(avoid);
    for (const w of shuffle(list)) {
        if (seen.has(w.key)) continue;
        seen.add(w.key);
        out.push(w);
        if (out.length === n) break;
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

function picture(word, size = 'w-20 h-20') {
    return word.image_url
        ? `<img src="${esc(word.image_url)}" alt="" width="96" height="96" class="${size} object-contain mx-auto mb-2" loading="lazy" decoding="async">`
        : '';
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
    try {
        const res = await fetch('/api/progress', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                patient_id: 'default',          // el servidor usa siempre el paciente de la sesión
                word_id: GAME_IDS[gameType],
                score: Math.max(0, Math.min(100, Math.round(score))),
                attempt_number: 1,
                transcription: 'Juego: ' + gameType,
                feedback: details,
                duration_ms: details.duration_ms || null,
            }),
        });
        if (!res.ok) throw new Error(res.statusText);
        const data = await res.json();
        loadPlayerLevel();
        loadAchievements();
        return data.points_earned || 0;
    } catch (e) {
        console.warn('No se pudo guardar la partida:', e);
        return null;
    }
}

// ---------- ventana del juego ----------
const GAMES = {
    word_match: ['🎯 Emparejar Palabras', startWordMatch],
    category_sort: ['📦 Clasificar Palabras', startCategorySort],
    complete_phrase: ['💬 Completa la Frase', startCompletePhrase],
    speed_round: ['⚡ Ronda Rápida', startSpeedRound],
    memory: ['🧠 Memoria', startMemoryGame],
    maze: ['🗺️ Laberinto de Voz', startMazeGame],
};

async function startGame(type, ...args) {
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
    document.getElementById('game-modal-title').textContent = game[0];
    const s = session;
    content().innerHTML = '<p class="text-gray-600 text-lg"><i class="fas fa-spinner fa-spin mr-2"></i>Preparando el juego…</p>';
    try {
        await ensurePool();
    } catch (e) {
        if (s === session) content().innerHTML = '<p class="text-red-600 text-lg text-center">No se pudieron cargar las palabras. Comprueba la conexión y vuelve a intentarlo.</p>';
        return;
    }
    if (s !== session) return;
    game[1](content(), ...args);
}

/** Cancela todo lo de la partida anterior */
function resetSession() {
    session++;
    for (const id of timers) clearTimeout(id);
    timers.clear();
    clearInterval(speedTimer);
    keyHandler = null;
    stopSound();
    stopMazeRecording(true);
}

function closeGame() {
    resetSession();
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
    const btn = e.target instanceof Element ? e.target.closest('[data-action]') : null;
    if (!btn || btn.disabled || !content().contains(btn)) return;
    const handler = ACTIONS[btn.dataset.action];
    if (handler) handler(btn);
});
const ACTIONS = {};

/** Pantalla final común a todos los juegos */
async function showEnd(type, { emoji, title, lines, score, details }) {
    const s = session;
    content().innerHTML = `
        <div class="text-center">
            <div class="text-6xl mb-4">${emoji}</div>
            <h2 class="text-3xl font-bold text-gray-800 mb-3">${esc(title)}</h2>
            ${lines.map((l) => `<p class="text-xl text-gray-700 mb-2">${l}</p>`).join('')}
            <p id="end-points" class="text-lg text-gray-500 mb-6">Guardando…</p>
            <div class="flex flex-wrap justify-center gap-3">
                <button data-action="restart" data-game="${type}" class="bg-primary text-white px-8 py-4 rounded-xl text-lg font-semibold hover:bg-secondary transition">Jugar otra vez</button>
                <button data-action="close" class="bg-gray-200 text-gray-800 px-8 py-4 rounded-xl text-lg font-semibold hover:bg-gray-300 transition">Salir</button>
            </div>
        </div>`;
    say(`${title}. ${lines.map((l) => l.replace(/<[^>]+>/g, '')).join(' ')}`);
    const points = await saveGame(type, score, details);
    if (s !== session) return;
    const el = document.getElementById('end-points');
    if (el) el.textContent = points === null ? 'No se pudo guardar la partida.' : `+${points} puntos`;
}
ACTIONS.restart = (btn) => startGame(btn.dataset.game);
ACTIONS.close = () => closeGame();
ACTIONS.speak = (btn) => playSound(btn.dataset.text);

function roundHeader(round, total, extra = '') {
    return `<div class="flex justify-between items-center w-full mb-4 text-gray-600">
        <span class="font-medium">Ronda ${round} de ${total}</span>${extra}</div>`;
}

/** Marca una respuesta: verde y bloquea todo si es correcta; roja y desactivada si no */
function markAnswer(btn, ok, group) {
    if (ok) {
        btn.classList.add('!bg-green-100', '!border-green-500', 'text-green-800');
        group.querySelectorAll('button').forEach((b) => { b.disabled = true; });
    } else {
        btn.classList.add('!bg-red-50', '!border-red-400', 'text-red-700', 'line-through');
        btn.disabled = true;
    }
}

// =============== 1. Emparejar: escucha y elige la palabra ===============
const MATCH_ROUNDS = 8;
let match = null;

function startWordMatch() {
    const words = easyWords();
    if (words.length < 4) { content().innerHTML = '<p>No hay suficientes palabras.</p>'; return; }
    match = { round: 0, firstTry: 0, used: new Set(), started: Date.now() };
    nextMatchRound();
}

function nextMatchRound() {
    match.round++;
    // Preferir palabras con pictograma: ayudan a quien tiene dificultades para leer
    const candidates = easyWords().filter((w) => w.image_url);
    const target = pickFresh(candidates.length >= MATCH_ROUNDS ? candidates : easyWords(), match.used);
    match.used.add(target.key);
    match.target = target;
    match.missed = false;
    const options = shuffle([target, ...pickWords(easyWords(), 3, new Set([target.key]))]);
    content().innerHTML = `
        <div class="text-center w-full max-w-2xl">
            ${roundHeader(match.round, MATCH_ROUNDS)}
            <p class="text-gray-700 text-lg mb-4">Escucha la palabra y elige la correcta:</p>
            <button data-action="speak" data-text="${esc(target.word)}" class="bg-blue-700 text-white px-6 py-4 rounded-2xl text-xl font-semibold shadow-lg hover:bg-blue-800 transition mb-6">
                <i class="fas fa-volume-high mr-2"></i>Escuchar otra vez
            </button>
            <div id="match-options" class="grid grid-cols-2 gap-4 mb-4">
                ${options.map((o) => `
                    <button data-action="match" data-key="${esc(o.key)}"
                        class="bg-gray-50 border-2 border-gray-200 hover:border-primary p-4 rounded-2xl transition text-xl font-semibold capitalize">
                        ${picture(o)}${esc(o.word)}
                    </button>`).join('')}
            </div>
            <div id="match-feedback" class="h-8 text-lg font-bold" aria-live="polite"></div>
        </div>`;
    later(() => playSound(target.word), 400);
}

ACTIONS.match = (btn) => {
    const ok = btn.dataset.key === match.target.key;
    const fb = document.getElementById('match-feedback');
    markAnswer(btn, ok, document.getElementById('match-options'));
    if (ok) {
        if (!match.missed) match.firstTry++;
        fb.textContent = '¡Correcto! 🎉'; fb.className = 'h-8 text-lg font-bold text-green-600';
        say('¡Correcto!');
        later(() => (match.round >= MATCH_ROUNDS ? endWordMatch() : nextMatchRound()), 1400);
    } else {
        match.missed = true;
        fb.textContent = 'Esa no es. Escucha otra vez.'; fb.className = 'h-8 text-lg font-bold text-red-600';
        say('Esa no es. Escucha otra vez.');
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

// =============== 2. Clasificar: ¿a qué grupo pertenece? ===============
const SORT_ROUNDS = 8;
let sort = null;

function sortableCategories() {
    return pool.categories.filter((c) => !SORT_EXCLUDED.includes(c.id)
        && pool.words.filter((w) => w.category_id === c.id && !w.multi && !w.ambiguous).length >= 3);
}

function startCategorySort() {
    if (sortableCategories().length < 3) { content().innerHTML = '<p>No hay suficientes grupos de palabras.</p>'; return; }
    sort = { round: 0, firstTry: 0, used: new Set(), started: Date.now() };
    nextSortRound();
}

function nextSortRound() {
    sort.round++;
    const cats = sortableCategories();
    const catIds = new Set(cats.map((c) => c.id));
    const words = pool.words.filter((w) => catIds.has(w.category_id) && !w.multi && !w.ambiguous && w.level <= 3);
    const item = pickFresh(words, sort.used);
    sort.used.add(item.key);
    sort.item = item;
    sort.missed = false;
    const correct = cats.find((c) => c.id === item.category_id);
    const options = shuffle([correct, ...shuffle(cats.filter((c) => c.id !== item.category_id)).slice(0, 2)]);
    content().innerHTML = `
        <div class="text-center w-full max-w-2xl">
            ${roundHeader(sort.round, SORT_ROUNDS)}
            <p class="text-gray-700 text-lg mb-4">¿A qué grupo pertenece esta palabra?</p>
            <button data-action="speak" data-text="${esc(item.word)}" class="bg-blue-50 rounded-2xl px-10 py-6 mb-6 inline-block shadow-sm hover:bg-blue-100 transition" aria-label="Escuchar ${esc(item.word)}">
                ${picture(item, 'w-24 h-24')}
                <span class="text-4xl font-bold text-gray-800 capitalize">${esc(item.word)}</span>
                <span class="block text-sm text-blue-700 mt-2"><i class="fas fa-volume-high mr-1"></i>Escuchar</span>
            </button>
            <div id="sort-options" class="grid grid-cols-1 md:grid-cols-3 gap-4">
                ${options.map((c) => `
                    <button data-action="sort" data-cat="${esc(c.id)}"
                        class="bg-gray-50 border-2 border-gray-200 hover:border-indigo-400 p-5 rounded-2xl transition text-xl font-semibold">
                        <span class="text-3xl block mb-1">${esc(c.icon)}</span>${esc(c.name)}
                    </button>`).join('')}
            </div>
            <div id="sort-feedback" class="mt-5 h-8 text-lg font-bold" aria-live="polite"></div>
        </div>`;
}

ACTIONS.sort = (btn) => {
    const ok = btn.dataset.cat === sort.item.category_id;
    const fb = document.getElementById('sort-feedback');
    markAnswer(btn, ok, document.getElementById('sort-options'));
    if (ok) {
        if (!sort.missed) sort.firstTry++;
        fb.textContent = '¡Correcto! 🎉'; fb.className = 'mt-5 h-8 text-lg font-bold text-green-600';
        say('¡Correcto!');
        later(() => (sort.round >= SORT_ROUNDS ? endCategorySort() : nextSortRound()), 1400);
    } else {
        sort.missed = true;
        fb.textContent = 'Ese no es. Prueba con otro.'; fb.className = 'mt-5 h-8 text-lg font-bold text-red-600';
        say('Ese no es. Prueba con otro.');
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

// =============== 3. Completa la frase ===============
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
];
const PHRASE_ROUNDS = 8;
let phrase = null;

function startCompletePhrase() {
    phrase = { round: 0, firstTry: 0, queue: shuffle(PHRASES).slice(0, PHRASE_ROUNDS), started: Date.now() };
    nextPhraseRound();
}

function nextPhraseRound() {
    phrase.current = phrase.queue[phrase.round];
    phrase.round++;
    phrase.missed = false;
    const p = phrase.current;
    const [before, after] = p.text.split('___');
    content().innerHTML = `
        <div class="text-center w-full max-w-2xl">
            ${roundHeader(phrase.round, PHRASE_ROUNDS)}
            <p class="text-gray-700 text-lg mb-4">Elige la palabra que falta:</p>
            <div class="bg-orange-50 rounded-2xl p-6 mb-6 shadow-sm">
                <span class="text-2xl md:text-3xl font-medium text-gray-800">${esc(before)}<span id="phrase-gap" class="border-b-4 border-orange-400 px-3 text-orange-600 font-bold">?</span>${esc(after || '')}</span>
            </div>
            <div id="phrase-options" class="grid grid-cols-1 md:grid-cols-3 gap-4">
                ${shuffle([p.correct, ...p.wrongs]).map((o) => `
                    <button data-action="phrase" data-word="${esc(o)}"
                        class="bg-white border-2 border-gray-200 hover:border-orange-400 shadow-sm p-5 rounded-2xl transition text-xl font-bold">
                        ${esc(o)}
                    </button>`).join('')}
            </div>
            <div id="phrase-feedback" class="mt-5 h-8 text-lg font-bold" aria-live="polite"></div>
        </div>`;
}

ACTIONS.phrase = (btn) => {
    const p = phrase.current;
    const ok = btn.dataset.word === p.correct;
    const fb = document.getElementById('phrase-feedback');
    markAnswer(btn, ok, document.getElementById('phrase-options'));
    if (ok) {
        if (!phrase.missed) phrase.firstTry++;
        document.getElementById('phrase-gap').textContent = p.correct;
        fb.textContent = '¡Excelente! 🌟'; fb.className = 'mt-5 h-8 text-lg font-bold text-green-600';
        const full = p.text.replace('___', p.correct);
        say(full);
        playSound(full);                     // se oye la frase completa: refuerza lo aprendido
        later(() => (phrase.round >= PHRASE_ROUNDS ? endCompletePhrase() : nextPhraseRound()), 2600);
    } else {
        phrase.missed = true;
        fb.textContent = 'Casi… prueba otra vez'; fb.className = 'mt-5 h-8 text-lg font-bold text-red-600';
        say('Casi, prueba otra vez');
    }
};

function endCompletePhrase() {
    const pct = (phrase.firstTry / PHRASE_ROUNDS) * 100;
    showEnd('complete_phrase', {
        emoji: pct >= 75 ? '🏆' : '👏', title: '¡Partida terminada!',
        lines: [`Completaste <strong>${phrase.firstTry} de ${PHRASE_ROUNDS}</strong> frases a la primera.`],
        score: pct, details: { first_try: phrase.firstTry, rounds: PHRASE_ROUNDS, duration_ms: Date.now() - phrase.started },
    });
}

// =============== 4. Ronda rápida: leer en voz alta ===============
// Quien acompaña al paciente (o él mismo) marca si la dijo bien. 90 s: a los mayores 60 s se
// les quedaban cortos.
const SPEED_SECONDS = 90;
let speedTimer = null;
let speed = null;

function startSpeedRound(container) {
    speed = { good: 0, skipped: 0, used: new Set(), left: SPEED_SECONDS };
    container.innerHTML = `
        <div class="text-center w-full max-w-xl">
            <p class="text-gray-700 text-lg mb-6">Lee cada palabra en voz alta. Pulsa <strong>«La dije bien»</strong> o <strong>«Pasar»</strong>.</p>
            <button data-action="speed-go" class="bg-amber-700 text-white px-10 py-5 rounded-2xl text-2xl font-bold hover:bg-amber-800 transition">
                <i class="fas fa-play mr-2"></i>Empezar
            </button>
        </div>`;
}

ACTIONS['speed-go'] = () => {
    content().innerHTML = `
        <div class="text-center w-full max-w-xl">
            <div id="speed-timer" class="text-5xl font-bold text-primary" aria-live="off">${SPEED_SECONDS}</div>
            <p class="text-gray-600 mb-4">segundos</p>
            <div class="bg-gray-50 rounded-2xl p-6 mb-6 border-2 border-gray-100">
                <div id="speed-picture"></div>
                <p id="speed-word" class="text-5xl font-bold text-gray-800 capitalize"></p>
                <button data-action="speed-listen" class="mt-3 text-blue-700 font-medium hover:underline"><i class="fas fa-volume-high mr-1"></i>Escuchar</button>
            </div>
            <div class="grid grid-cols-2 gap-4 mb-4">
                <button data-action="speed-next" data-good="1" class="bg-green-600 text-white py-5 rounded-2xl text-xl font-bold hover:bg-green-700 transition"><i class="fas fa-check mr-2"></i>La dije bien</button>
                <button data-action="speed-next" data-good="0" class="bg-gray-200 text-gray-800 py-5 rounded-2xl text-xl font-bold hover:bg-gray-300 transition">Pasar ›</button>
            </div>
            <p class="text-gray-700 text-lg">Bien dichas: <span id="speed-score" class="font-bold text-2xl text-primary">0</span></p>
        </div>`;
    nextSpeedWord();
    clearInterval(speedTimer);
    const s = session;
    speedTimer = setInterval(() => {
        if (s !== session) { clearInterval(speedTimer); return; }
        speed.left--;
        document.getElementById('speed-timer').textContent = speed.left;
        if (speed.left === 10) say('Quedan 10 segundos');
        if (speed.left <= 0) { clearInterval(speedTimer); endSpeedRound(); }
    }, 1000);
};

function nextSpeedWord() {
    let words = easyWords(3);
    if (speed.used.size >= words.length) speed.used.clear();
    const [w] = pickWords(words, 1, speed.used);
    speed.used.add(w.key);
    speed.word = w;
    document.getElementById('speed-word').textContent = w.word;
    document.getElementById('speed-picture').innerHTML = picture(w, 'w-24 h-24');
    say(w.word);
}

ACTIONS['speed-listen'] = () => playSound(speed.word.word);
ACTIONS['speed-next'] = (btn) => {
    if (btn.dataset.good === '1') speed.good++; else speed.skipped++;
    document.getElementById('speed-score').textContent = speed.good;
    nextSpeedWord();
};

function endSpeedRound() {
    const shown = speed.good + speed.skipped;
    showEnd('speed_round', {
        emoji: '🏁', title: '¡Tiempo terminado!',
        lines: [`Dijiste bien <strong>${speed.good}</strong> ${speed.good === 1 ? 'palabra' : 'palabras'}.`],
        score: shown ? (speed.good / shown) * 100 : 0,
        details: { words_ok: speed.good, skipped: speed.skipped, duration_ms: SPEED_SECONDS * 1000 },
    });
}

// =============== 5. Memoria: repetir la secuencia en orden ===============
const MEMORY_MAX = 6;          // palabras de la secuencia más larga
let memory = null;

function startMemoryGame() {
    memory = { length: 2, best: 0, started: Date.now() };
    nextMemoryRound();
}

function nextMemoryRound() {
    memory.sequence = pickWords(easyWords().filter((w) => w.image_url).length >= 8 ? easyWords().filter((w) => w.image_url) : easyWords(), memory.length);
    memory.input = [];
    memory.locked = true;
    content().innerHTML = `
        <div class="text-center w-full max-w-2xl">
            <h3 class="text-2xl font-bold mb-2">Secuencia de ${memory.length} palabras</h3>
            <p id="mem-status" class="text-gray-700 text-lg mb-6" aria-live="polite">Mira y escucha las palabras. Luego tócalas en el mismo orden.</p>
            <div id="memory-board" class="flex justify-center mb-6 min-h-[11rem] items-center"></div>
            <div id="memory-answer" class="flex flex-wrap justify-center gap-2 mb-4 min-h-[2.5rem]"></div>
            <div id="memory-options" class="hidden grid grid-cols-2 md:grid-cols-3 gap-3"></div>
            <button data-action="mem-play" class="bg-purple-600 text-white px-10 py-4 rounded-2xl text-xl font-bold hover:bg-purple-700 transition">Comenzar</button>
        </div>`;
}

ACTIONS['mem-play'] = async (btn) => {
    btn.remove();
    const board = document.getElementById('memory-board');
    const status = document.getElementById('mem-status');
    status.textContent = 'Observa…';
    for (const w of memory.sequence) {
        board.innerHTML = `
            <div class="w-44 bg-white border-4 border-purple-500 rounded-2xl p-4 shadow-lg">
                ${picture(w, 'w-24 h-24')}<span class="text-2xl font-bold capitalize">${esc(w.word)}</span>
            </div>`;
        playSound(w.word);
        await wait(1800);                    // tiempo para ver, oír y retener cada palabra
        board.innerHTML = '<div class="w-44 h-44 bg-gray-100 rounded-2xl"></div>';
        await wait(600);
    }
    board.innerHTML = '';
    status.textContent = '¡Tu turno! Toca las palabras en el mismo orden.';
    say(status.textContent);
    // Opciones: las de la secuencia y, desde 3 palabras, una que no salió
    const extra = memory.length >= 3 ? pickWords(easyWords(), 1, new Set(memory.sequence.map((w) => w.key))) : [];
    const options = document.getElementById('memory-options');
    options.innerHTML = shuffle([...memory.sequence, ...extra]).map((w) => `
        <button data-action="mem-pick" data-key="${esc(w.key)}"
            class="bg-white border-2 border-purple-200 hover:border-purple-500 shadow-sm p-3 rounded-2xl text-lg font-semibold capitalize">
            ${picture(w, 'w-16 h-16')}${esc(w.word)}
        </button>`).join('');
    options.classList.remove('hidden');
    memory.locked = false;
};

ACTIONS['mem-pick'] = (btn) => {
    if (memory.locked) return;
    const expected = memory.sequence[memory.input.length];
    const status = document.getElementById('mem-status');
    if (btn.dataset.key === expected.key) {
        memory.input.push(expected);
        btn.disabled = true;
        btn.classList.add('opacity-40');
        document.getElementById('memory-answer').insertAdjacentHTML('beforeend',
            `<span class="bg-purple-100 text-purple-800 px-3 py-1 rounded-full font-semibold capitalize">${memory.input.length}. ${esc(expected.word)}</span>`);
        playSound(expected.word);
        if (memory.input.length === memory.sequence.length) {
            memory.locked = true;
            memory.best = memory.length;
            if (memory.length >= MEMORY_MAX) { endMemory(true); return; }
            status.textContent = '¡Muy bien! La siguiente tendrá una palabra más.';
            say(status.textContent);
            later(() => { memory.length++; nextMemoryRound(); }, 1800);
        }
    } else {
        memory.locked = true;
        btn.classList.add('!border-red-400', '!bg-red-50');
        const order = memory.sequence.map((w, i) => `${i + 1}. ${esc(w.word)}`).join(' · ');
        status.innerHTML = `No pasa nada. El orden era: <strong class="capitalize">${order}</strong>`;
        say('No pasa nada. El orden era: ' + memory.sequence.map((w) => w.word).join(', '));
        document.getElementById('memory-options').insertAdjacentHTML('afterend', `
            <div class="flex flex-wrap justify-center gap-3 mt-6">
                <button data-action="mem-retry" class="bg-purple-600 text-white px-6 py-4 rounded-2xl text-lg font-bold hover:bg-purple-700">Repetir con ${memory.length} palabras</button>
                <button data-action="mem-finish" class="bg-gray-200 text-gray-800 px-6 py-4 rounded-2xl text-lg font-bold hover:bg-gray-300">Terminar</button>
            </div>`);
    }
};
ACTIONS['mem-retry'] = () => nextMemoryRound();
ACTIONS['mem-finish'] = () => endMemory(false);

function endMemory(won) {
    showEnd('memory', {
        emoji: won ? '🏆' : '🧠', title: won ? '¡Lo lograste todo!' : '¡Buen trabajo!',
        lines: [memory.best ? `Recordaste una secuencia de <strong>${memory.best} palabras</strong>.` : 'Sigue practicando: cada vez será más fácil.'],
        score: (memory.best / MEMORY_MAX) * 100,
        details: { best_length: memory.best, duration_ms: Date.now() - memory.started },
    });
}

// =============== 6. Laberinto de voz ===============
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
let mazeRec = null;            // grabación en curso del laberinto

function startMazeGame(container, level = 0) {
    maze = { level, grid: MAZES[level % MAZES.length], x: 0, y: 0, moves: 0, started: Date.now() };
    keyHandler = (e) => {
        const map = { ArrowUp: 'arriba', ArrowDown: 'abajo', ArrowLeft: 'izquierda', ArrowRight: 'derecha' };
        if (map[e.key]) { e.preventDefault(); moveMaze(map[e.key]); }
    };
    renderMaze('Di una dirección o usa las flechas.');
}

function renderMaze(feedback) {
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
    const recording = !!mazeRec;
    const arrow = (d) => `<button data-action="maze-move" data-dir="${d}" aria-label="${DIRECTIONS[d].label}"
        class="w-16 h-16 rounded-2xl bg-white border-2 border-teal-200 text-teal-700 hover:bg-teal-50 flex items-center justify-center">${ARROW_SVG(DIRECTIONS[d].rotate)}</button>`;
    content().innerHTML = `
        <div class="flex flex-col items-center">
            <p class="text-gray-700 text-lg mb-1">Ayuda al mono a llegar a la banana. <span class="text-gray-500">Laberinto ${maze.level % MAZES.length + 1} de ${MAZES.length}</span></p>
            <p class="text-gray-600 mb-3">Movimientos: <strong>${maze.moves}</strong></p>
            <div class="grid grid-cols-5 gap-2 mb-4 p-3 bg-white rounded-xl shadow-inner border border-gray-100">${cells}</div>
            <div id="maze-feedback" class="min-h-[2rem] font-bold text-lg text-teal-700 text-center mb-3" aria-live="polite">${esc(feedback)}</div>
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
    const next = maze.level + 1;
    showEnd('maze', {
        emoji: '🏆', title: '¡Laberinto completado!',
        lines: [`Lo hiciste en <strong>${maze.moves}</strong> movimientos.`],
        score: 100, details: { maze: maze.level % MAZES.length + 1, moves: maze.moves, duration_ms: Date.now() - maze.started },
    }).then(() => {
        const again = content().querySelector('[data-action="restart"]');
        if (again && next < MAZES.length) {
            again.textContent = 'Siguiente laberinto';
            again.dataset.action = 'maze-next';
            again.dataset.level = String(next);
        }
    });
}
ACTIONS['maze-next'] = (btn) => startGame('maze', Number(btn.dataset.level));

/** Interpreta lo transcrito: admite variantes y pequeños errores («isquierda», «derecho») */
function parseDirection(text) {
    const lev = (a, b) => {
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
    };
    for (const token of norm(text).split(' ')) {
        for (const [dir, d] of Object.entries(DIRECTIONS)) {
            if (d.words.includes(token)) return dir;
        }
    }
    for (const token of norm(text).split(' ')) {
        if (token.length < 4) continue;
        for (const [dir] of Object.entries(DIRECTIONS)) {
            if (lev(token, dir) <= (dir.length >= 7 ? 2 : 1)) return dir;
        }
    }
    return null;
}

ACTIONS['maze-mic'] = () => {
    if (mazeRec) { stopMazeRecording(false, true); return; }
    if (!mazeStarting) startMazeRecording();
};

let mazeAudioCtx = null;
let mazeStarting = false;      // evita abrir dos micrófonos con dos pulsaciones seguidas
async function startMazeRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        renderMaze('El micrófono necesita HTTPS. Usa las flechas.'); return;
    }
    const s = session;
    let stream;
    mazeStarting = true;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: true } });
    } catch (e) {
        renderMaze(e.name === 'NotAllowedError' ? 'Necesito permiso para usar el micrófono.' : 'No se pudo usar el micrófono.'); return;
    } finally {
        mazeStarting = false;
    }
    if (s !== session) { stream.getTracks().forEach((t) => t.stop()); return; }
    const recorder = new MediaRecorder(stream);
    const chunks = [];
    const rec = { recorder, stream, heard: false, cancelled: false, timer: null };
    mazeRec = rec;
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        clearInterval(rec.timer);
        if (mazeRec === rec) mazeRec = null;
        if (rec.cancelled || s !== session) return;
        if (!rec.heard) { renderMaze('No te oí. Pulsa el micrófono y habla un poco más fuerte.'); return; }
        sendMazeCommand(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }), s);
    };
    recorder.start();
    renderMaze('Te escucho…');

    // Para sola al callar (como en la práctica) o a los 4 s
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const started = Date.now();
    if (!AudioCtx) { rec.heard = true; later(() => stopMazeRecording(false, false), 3000); return; }
    mazeAudioCtx = mazeAudioCtx || new AudioCtx();
    if (mazeAudioCtx.state === 'suspended') mazeAudioCtx.resume().catch(() => {});
    const analyser = mazeAudioCtx.createAnalyser();
    analyser.fftSize = 2048;
    const source = mazeAudioCtx.createMediaStreamSource(stream);
    source.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    let lastVoice = 0, voiceMs = 0;
    rec.timer = setInterval(() => {
        analyser.getFloatTimeDomainData(buf);
        let sum = 0; for (const v of buf) sum += v * v;
        const rms = Math.sqrt(sum / buf.length);
        const now = Date.now();
        if (rms > (rec.heard ? 0.006 : 0.012)) { voiceMs += 50; lastVoice = now; if (voiceMs >= 150) rec.heard = true; }
        if ((rec.heard && now - lastVoice > 900) || now - started > 4000) {
            source.disconnect();
            stopMazeRecording(false, false);
        }
    }, 50);
}

/** cancel: descartar lo grabado; byUser: se pulsó para terminar (se envía aunque fuera bajito) */
function stopMazeRecording(cancel, byUser = false) {
    const rec = mazeRec;
    if (!rec) return;
    rec.cancelled = cancel;
    if (byUser) rec.heard = true;
    clearInterval(rec.timer);
    if (rec.recorder.state !== 'inactive') rec.recorder.stop();
    else rec.stream.getTracks().forEach((t) => t.stop());
    mazeRec = null;
}

async function sendMazeCommand(blob, s) {
    renderMaze('Entendiendo…');
    const form = new FormData();
    form.append('audio_file', blob, 'comando.webm');
    form.append('initial_prompt', 'Arriba. Abajo. Izquierda. Derecha.');
    try {
        const res = await fetch('/api/transcribe', { method: 'POST', body: form });
        if (!res.ok) throw new Error(res.statusText);
        const data = await res.json();
        if (s !== session) return;
        const dir = parseDirection(data.transcription || '');
        if (dir) moveMaze(dir);
        else renderMaze(data.transcription ? `Oí «${data.transcription}». Di: Arriba, Abajo, Izquierda o Derecha.` : 'No te entendí. Inténtalo otra vez.');
    } catch (e) {
        if (s === session) renderMaze('No se pudo procesar la voz. Usa las flechas.');
    }
}

// ---------- inicio ----------
document.addEventListener('DOMContentLoaded', () => {
    loadPlayerLevel();
    loadDailyChallenge();
    loadAchievements();
    ensurePool().catch((e) => console.warn('No se pudieron cargar las palabras de los juegos:', e));
});
