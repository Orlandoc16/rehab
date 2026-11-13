// @ts-check
/**
 * Puente de la app Android sin servidor (solo se carga en app_mode, ver templates/base.html).
 *
 * - Las peticiones fetch('/api/...') las responde RehabLocalApi (static/js/app/local-api.js) en
 *   vez de un servidor. /api/speak/... no pasa por aquí: lo sirve Android (voz Piper) para que
 *   <audio src="/api/speak/..."> siga funcionando igual.
 * - La base de datos es SQLite de Android, a través de la interfaz nativa `RehabNative`.
 * - El reconocimiento de voz (Whisper) también es nativo: aquí se decodifica la grabación a
 *   PCM 16 kHz mono y se envía.
 * - Sin paciente elegido, cualquier página lleva a /patients (como hace el servidor).
 */
(function () {
    'use strict';

    /**
     * @typedef {{ sqlAll(sql: string, params: string): string, sqlRun(sql: string, params: string): string,
     *   transcribe(id: string, pcm16Base64: string, prompt: string, retry: boolean): void,
     *   exportBackup(): string, importBackup(): void }} NativeApi
     */
    /** @type {NativeApi | undefined} */
    const native = /** @type {any} */ (window).RehabNative;
    if (!native) {
        console.error('RehabNative no disponible: esta página solo funciona dentro de la app.');
        return;
    }

    const parse = (/** @type {string} */ json) => {
        const r = JSON.parse(json);
        if (r && r.error) throw new Error(r.error);
        return r;
    };
    const db = {
        all: (/** @type {string} */ sql, params = []) => parse(native.sqlAll(sql, JSON.stringify(params))).rows,
        run: (/** @type {string} */ sql, params = []) => parse(native.sqlRun(sql, JSON.stringify(params))),
    };

    // ---- reconocimiento de voz (nativo, asíncrono)

    /** @type {Map<string, {resolve: (t: string) => void, reject: (e: Error) => void}>} */
    const pending = new Map();
    let nextId = 1;

    /** Grabación (WebM/Opus del MediaRecorder) -> PCM 16 kHz mono en Int16, codificado en base64. */
    async function toPcm16kBase64(/** @type {Blob} */ blob) {
        const AC = window.AudioContext || /** @type {any} */ (window).webkitAudioContext;
        const ctx = new AC();
        let decoded;
        try {
            decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
        } finally {
            ctx.close();
        }
        const frames = Math.max(1, Math.ceil(decoded.duration * 16000));
        const offline = new OfflineAudioContext(1, frames, 16000);
        const src = offline.createBufferSource();
        src.buffer = decoded;
        src.connect(offline.destination);
        src.start();
        const pcm = (await offline.startRendering()).getChannelData(0);
        const bytes = new Uint8Array(pcm.length * 2);
        const view = new DataView(bytes.buffer);
        for (let i = 0; i < pcm.length; i++) {
            const s = Math.max(-1, Math.min(1, pcm[i]));
            view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        }
        let bin = '';
        for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + 0x8000)));
        return btoa(bin);
    }

    const recognizer = {
        async transcribe(/** @type {Blob} */ audio, /** @type {{prompt?: string|null, retry?: boolean}} */ opts) {
            const pcm = await toPcm16kBase64(audio);
            const id = String(nextId++);
            return new Promise((resolve, reject) => {
                pending.set(id, { resolve, reject });
                native.transcribe(id, pcm, opts.prompt || '', Boolean(opts.retry));
            });
        },
    };

    // ---- servidor local

    const api = RehabLocalApi.create({ db, recognizer });
    const realFetch = window.fetch.bind(window);
    const ready = realFetch('/static/app/content.json')
        .then((r) => r.json())
        .then((content) => api.init(content));

    /** @param {RequestInfo | URL} input @param {RequestInit} [init] */
    async function localFetch(input, init) {
        const req = input instanceof Request ? input : null;
        const url = new URL(req ? req.url : String(input), location.href);
        if (url.origin !== location.origin || !url.pathname.startsWith('/api/') || url.pathname.startsWith('/api/speak/')) {
            return realFetch(input, init);
        }
        await ready;
        const method = (init && init.method) || (req && req.method) || 'GET';
        let body = (init && init.body) ?? null;
        if (req && body === null && method !== 'GET') body = await req.clone().text();
        if (typeof body === 'string') {
            try { body = JSON.parse(body); } catch (_) { /* se queda como texto */ }
        }
        const r = await api.handle(method, url.pathname + url.search, body);
        return new Response(JSON.stringify(r.body), { status: r.status, headers: { 'Content-Type': 'application/json' } });
    }
    window.fetch = localFetch;

    // ---- interfaz para el código nativo y las páginas

    /** @type {any} */ (window).RehabBridge = {
        /** Android llama aquí al terminar una transcripción. */
        _transcribed(/** @type {string} */ id, /** @type {boolean} */ ok, /** @type {string} */ text) {
            const p = pending.get(id);
            if (!p) return;
            pending.delete(id);
            if (ok) p.resolve(text);
            else p.reject(new Error(text || 'Error de reconocimiento'));
        },
        /** Guarda una copia de la base de datos (el sistema pregunta dónde). */
        exportBackup: () => native.exportBackup(),
        /** Sustituye la base de datos por una copia (el sistema pide el archivo; luego se recarga). */
        importBackup: () => native.importBackup(),
        ready,
    };

    // ---- paciente activo: cabecera y redirección a /patients si no hay

    ready.then(async () => {
        const s = (await api.handle('GET', '/api/app/session', null)).body;
        const fill = () => document.querySelectorAll('[data-app-patient-name]').forEach((el) => { el.textContent = s.patient_name || ''; });
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fill); else fill();
        if (!s.patient_id && location.pathname !== '/patients') location.replace('/patients');
    }).catch((e) => console.error('No se pudo iniciar la app', e));
})();
