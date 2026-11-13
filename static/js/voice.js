// @ts-check
// Voz de la app: primero la del servidor (Piper, local y de buena calidad); si no está disponible
// (sin conexión, servidor caído o sin motor de voz), la del propio dispositivo.
// La usan el comunicador, la práctica y los juegos.

/** Variantes de español por orden de preferencia (la voz del servidor es mexicana) */
const VOICE_PREFERRED = ['es-mx', 'es-us', 'es-419', 'es-es'];

/**
 * Voces en español del dispositivo, de mejor a peor (misma regla que la app móvil): primero las
 * instaladas en el aparato y, a igualdad, la variante de español preferida. Sin conexión se
 * descartan las voces en línea, que no suenan.
 * @param {{ lang: string, localService: boolean, name?: string }[]} voices
 * @param {boolean} online
 */
function rankDeviceVoices(voices, online) {
    const norm = (/** @type {string} */ lang) => (lang || '').toLowerCase().replace('_', '-');
    let spanish = voices.filter((v) => norm(v.lang).startsWith('es'));
    const local = spanish.filter((v) => v.localService);
    if (!online && local.length) spanish = local;
    const score = (/** @type {{ lang: string, localService: boolean }} */ v) => {
        const rank = VOICE_PREFERRED.indexOf(norm(v.lang));
        return (v.localService ? 10 : 0) + (rank < 0 ? 0 : (VOICE_PREFERRED.length - rank) * 2);
    };
    return spanish
        .map((v, i) => ({ v, i, s: score(v) }))
        .sort((a, b) => b.s - a.s || a.i - b.i)
        .map(({ v }) => v);
}

// Algunos navegadores cargan la lista de voces más tarde: se pide ya para tenerla en el primer uso
if ('speechSynthesis' in window) {
    try { speechSynthesis.getVoices(); } catch (e) { /* sin voces */ }
}

/**
 * Dice el texto con la voz del dispositivo (funciona sin conexión si el sistema tiene una voz
 * en español).
 * @param {string} text
 * @param {{ rate?: number, onEnd?: () => void }} [opts] rate: velocidad (1 = normal)
 * @returns {boolean} false si el navegador no tiene síntesis de voz
 */
function speakWithDevice(text, opts = {}) {
    if (!('speechSynthesis' in window)) return false;
    const utterance = new SpeechSynthesisUtterance(text);
    const [voice] = /** @type {SpeechSynthesisVoice[]} */ (rankDeviceVoices(speechSynthesis.getVoices(), navigator.onLine));
    utterance.lang = voice ? voice.lang : 'es-ES';
    if (voice) utterance.voice = voice;
    utterance.rate = opts.rate ?? 0.9;
    if (opts.onEnd) {
        utterance.onend = opts.onEnd;
        utterance.onerror = opts.onEnd;
    }
    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
    return true;
}

/** Aviso de fin de la voz que suena en cada reproductor @type {WeakMap<HTMLAudioElement, () => void>} */
const pendingVoiceEnd = new WeakMap();

/**
 * Reproduce la voz del servidor y, si falla, la del dispositivo.
 * @param {HTMLAudioElement} audio reproductor a usar
 * @param {string} url ruta de /api/speak/...
 * @param {string} text el mismo texto, para la voz del dispositivo
 * @param {{ rate?: number, onEnd?: () => void }} [opts] rate: velocidad de la voz del dispositivo;
 *   onEnd: se llama una vez cuando la voz termina (o no llega a sonar)
 * @returns {Promise<'server' | 'device' | 'none'>} qué voz sonó
 */
async function playVoice(audio, url, text, opts = {}) {
    // Una frase nueva corta la anterior: se avisa antes a quien esperaba su final
    const previous = pendingVoiceEnd.get(audio);
    if (previous) previous();
    let ended = false;
    const end = () => {
        if (ended) return;
        ended = true;
        audio.removeEventListener('ended', end);
        audio.removeEventListener('pause', end);
        if (pendingVoiceEnd.get(audio) === end) pendingVoiceEnd.delete(audio);
        if (opts.onEnd) opts.onEnd();
    };
    pendingVoiceEnd.set(audio, end);
    try {
        if ('speechSynthesis' in window) speechSynthesis.cancel();
        audio.src = url;
        await audio.play();
        audio.addEventListener('ended', end);
        audio.addEventListener('pause', end);
        return 'server';
    } catch (err) {
        // Se pulsó otra vez antes de empezar: la nueva reproducción ya está en marcha
        if (err instanceof DOMException && err.name === 'AbortError') { end(); return 'server'; }
        console.warn('Voz del servidor no disponible; se usa la del dispositivo', err);
        if (speakWithDevice(text, { rate: opts.rate, onEnd: end })) return 'device';
        end();
        return 'none';
    }
}

/** Calla la voz (la del servidor y la del dispositivo): p. ej. al empezar a grabar.
 * @param {HTMLAudioElement | null} [audio] */
function stopVoice(audio) {
    if (audio && !audio.paused) audio.pause();
    if ('speechSynthesis' in window) speechSynthesis.cancel();
}

/**
 * Texto para leer por sílabas: «caminar» → «ca, mi, nar» (las comas hacen la pausa). Necesita
 * static/js/syllables.js; sin él devuelve el texto tal cual.
 * @param {string} text
 */
function syllableCue(text) {
    /** @type {{ splitWord: (w: string) => string[] } | undefined} */
    const syl = /** @type {any} */ (window).RehabSyllables;
    if (!syl) return text;
    return text.split(/\s+/)
        .map((w) => syl.splitWord(w.replace(/[¿?¡!.,;:]/g, '')).join(', '))
        .filter(Boolean)
        .join('. ');
}

/** ¿Hay alguna voz en español en el dispositivo? null si el navegador aún no ha dado la lista. */
function deviceHasSpanishVoice() {
    if (!('speechSynthesis' in window)) return false;
    const voices = speechSynthesis.getVoices();
    if (!voices.length) return null;
    return rankDeviceVoices(voices, true).length > 0;
}
