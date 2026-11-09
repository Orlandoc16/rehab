// @ts-check
// Página /samples: el terapeuta graba al paciente diciendo una palabra y la etiqueta
// (correcta / incorrecta). Ver rehab/routers/samples.py.

/** @typedef {{id: string, name: string}} Category */
/** @typedef {{word: string, level: number, image_url?: string | null}} Word */

/**
 * @template {HTMLElement} T
 * @param {string} id
 * @returns {T}
 */
function el(id) {
    const node = document.getElementById(id);
    if (!node) throw new Error(`Falta #${id}`);
    return /** @type {T} */ (node);
}

const ui = {
    consent: /** @type {HTMLInputElement} */ (el('consent')),
    category: /** @type {HTMLSelectElement} */ (el('category')),
    level: /** @type {HTMLSelectElement} */ (el('level')),
    word: /** @type {HTMLSelectElement} */ (el('word')),
    image: /** @type {HTMLImageElement} */ (el('word-image')),
    target: el('target'),
    record: /** @type {HTMLButtonElement} */ (el('record')),
    recordIcon: el('record-icon'),
    status: el('status'),
    review: el('review'),
    playback: /** @type {HTMLAudioElement} */ (el('playback')),
    spokenWrap: el('spoken-wrap'),
    spoken: /** @type {HTMLInputElement} */ (el('spoken')),
    summary: el('summary'),
};

const MAX_SECONDS = 10;
/** @type {Word[]} */
let words = [];
/** @type {MediaRecorder | null} */
let recorder = null;
/** @type {Blob | null} */
let lastAudio = null;
/** @type {number | undefined} */
let stopTimer;

/** @param {string} text */
function setStatus(text) {
    ui.status.textContent = text;
}

/** @param {{total: number, correct: number, incorrect: number}} c */
function showSummary(c) {
    ui.summary.textContent = `Muestras guardadas: ${c.total} (${c.correct} correctas, ${c.incorrect} incorrectas)`;
}

function currentWord() {
    return words[Number(ui.word.value)] || null;
}

function refreshWord() {
    const w = currentWord();
    ui.target.textContent = w ? w.word : '—';
    if (w && w.image_url) {
        ui.image.src = w.image_url;
        ui.image.classList.remove('hidden');
    } else {
        ui.image.removeAttribute('src');
        ui.image.classList.add('hidden');
    }
    ui.record.disabled = !(w && ui.consent.checked);
    resetReview();
}

function resetReview() {
    lastAudio = null;
    ui.review.classList.add('hidden');
    ui.spokenWrap.classList.add('hidden');
    ui.spokenWrap.classList.remove('flex');
    ui.spoken.value = '';
}

async function loadWords() {
    const r = await fetch(`/api/words/${encodeURIComponent(ui.category.value)}?level=${ui.level.value}`);
    words = r.ok ? (await r.json()).words : [];
    ui.word.innerHTML = words.length
        ? words.map((w, i) => `<option value="${i}">${w.word.replace(/</g, '&lt;')}</option>`).join('')
        : '<option value="">(sin palabras en este nivel)</option>';
    refreshWord();
}

async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    /** @type {Blob[]} */
    const chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        clearTimeout(stopTimer);
        recorder = null;
        ui.recordIcon.className = 'fas fa-microphone';
        lastAudio = new Blob(chunks, { type: 'audio/webm' });
        ui.playback.src = URL.createObjectURL(lastAudio);
        ui.review.classList.remove('hidden');
        setStatus('Escucha la grabación y márcala.');
    };
    recorder.start();
    ui.recordIcon.className = 'fas fa-stop';
    setStatus(`Grabando... pulsa otra vez para terminar (máximo ${MAX_SECONDS} s).`);
    stopTimer = window.setTimeout(() => recorder && recorder.stop(), MAX_SECONDS * 1000);
}

/** @param {'correct' | 'incorrect'} label */
async function save(label) {
    const w = currentWord();
    if (!w || !lastAudio) return;
    const form = new FormData();
    form.append('audio_file', lastAudio, 'muestra.webm');
    form.append('target', w.word);
    form.append('label', label);
    form.append('spoken', label === 'incorrect' ? ui.spoken.value : '');
    form.append('level', String(w.level || ui.level.value));
    form.append('consent', ui.consent.checked ? '1' : '');
    setStatus('Guardando...');
    try {
        const r = await fetch('/api/samples', { method: 'POST', body: form });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        showSummary(data);
        resetReview();
        setStatus(`Guardada como ${label === 'correct' ? 'correcta' : 'incorrecta'}. Puedes grabar otra.`);
    } catch (err) {
        setStatus(`No se pudo guardar: ${err instanceof Error ? err.message : err}`);
    }
}

ui.consent.addEventListener('change', () => {
    refreshWord();
    setStatus(ui.consent.checked ? 'Elige una palabra y pulsa el micrófono.' : 'Marca el consentimiento para empezar.');
});
ui.category.addEventListener('change', loadWords);
ui.level.addEventListener('change', loadWords);
ui.word.addEventListener('change', refreshWord);
ui.record.addEventListener('click', () => {
    if (recorder) {
        recorder.stop();
        return;
    }
    resetReview();
    startRecording().catch((err) => setStatus(`No se pudo usar el micrófono: ${err instanceof Error ? err.message : err}`));
});
el('mark-correct').addEventListener('click', () => save('correct'));
el('mark-incorrect').addEventListener('click', () => {
    ui.spokenWrap.classList.remove('hidden');
    ui.spokenWrap.classList.add('flex');
    ui.spoken.focus();
});
el('save-incorrect').addEventListener('click', () => save('incorrect'));
el('discard').addEventListener('click', () => { resetReview(); setStatus('Descartada. Puedes grabar otra.'); });

(async () => {
    const cats = await (await fetch('/api/categories')).json();
    ui.category.innerHTML = /** @type {Category[]} */ (cats.categories)
        .map((c) => `<option value="${c.id}">${c.name.replace(/</g, '&lt;')}</option>`).join('');
    await loadWords();
    const summary = await fetch('/api/samples/summary');
    if (summary.ok) showSummary(await summary.json());
})();
