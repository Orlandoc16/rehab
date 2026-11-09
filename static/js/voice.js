// @ts-check
// Voz de la app: primero la del servidor (Piper, local y de buena calidad); si no está disponible
// (sin conexión, servidor caído o sin motor de voz), la del propio dispositivo.
// La usan el comunicador, la práctica y los juegos.

/**
 * Dice el texto con la voz del dispositivo (funciona sin conexión si el sistema tiene una voz
 * en español).
 * @param {string} text
 * @returns {boolean} false si el navegador no tiene síntesis de voz
 */
function speakWithDevice(text) {
    if (!('speechSynthesis' in window)) return false;
    const utterance = new SpeechSynthesisUtterance(text);
    const spanish = speechSynthesis.getVoices().filter((v) => (v.lang || '').toLowerCase().startsWith('es'));
    const voice = spanish.find((v) => v.localService) || spanish[0];
    utterance.lang = voice ? voice.lang : 'es-ES';
    if (voice) utterance.voice = voice;
    utterance.rate = 0.9;
    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
    return true;
}

/**
 * Reproduce la voz del servidor y, si falla, la del dispositivo.
 * @param {HTMLAudioElement} audio reproductor a usar
 * @param {string} url ruta de /api/speak/...
 * @param {string} text el mismo texto, para la voz del dispositivo
 * @returns {Promise<'server' | 'device' | 'none'>} qué voz sonó
 */
async function playVoice(audio, url, text) {
    try {
        audio.src = url;
        await audio.play();
        return 'server';
    } catch (err) {
        // Se pulsó otra vez antes de empezar: la nueva reproducción ya está en marcha
        if (err instanceof DOMException && err.name === 'AbortError') return 'server';
        console.warn('Voz del servidor no disponible; se usa la del dispositivo', err);
        return speakWithDevice(text) ? 'device' : 'none';
    }
}
