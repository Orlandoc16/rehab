// Service worker de Rehab Voice: el COMUNICADOR funciona sin conexión.
//
// - Al instalarse guarda la página del comunicador, sus recursos (CSS, fuentes, iconos),
//   la configuración de pictogramas y todas sus imágenes.
// - Página, configuración y tablero a medida del paciente: primero la red (datos al día); sin red,
//   la copia guardada.
// - Estáticos con hash (?v=... o nombre.<hash>.ext): primero la caché (nunca cambian).
// - Otros estáticos (pictogramas): caché inmediata y actualización en segundo plano.
// - Voz (/api/speak): primero la red; cada frase dicha se guarda para poder repetirla sin red.
// El resto de peticiones (práctica, progreso...) no se tocan.
//
// Se sirve desde /sw.js (ver rehab/routers/pages.py) para que su alcance sea toda la app.
// Tipos comprobados con: npm run check:js

// @ts-check
/** En este archivo, `self` es el ámbito del service worker. */
const sw = /** @type {ServiceWorkerGlobalScope} */ (/** @type {unknown} */ (self));

// v4: pictogramas de licencia libre (la copia anterior, con los de ARASAAC, se descarta)
const CACHE = 'rehab-comunicador-v4';
const SHELL_PAGE = '/communicator';
const CONFIG_URL = '/api/aac/config';
// Tablero a medida del paciente activo (pictogramas ocultos y frases propias)
const PROFILE_URL = '/api/aac/profile';
const NETWORK_TIMEOUT_MS = 4000;
const SPEECH_TIMEOUT_MS = 12000;   // la primera síntesis de una frase puede tardar varios segundos
const SYNC_FETCH_TIMEOUT_MS = 20000; // cada descarga de la copia sin conexión

/**
 * fetch que se CANCELA si tarda demasiado: una descarga colgada no debe bloquear la copia
 * sin conexión para siempre (las sincronizaciones siguientes esperan a la que está en curso).
 * @param {string} url
 * @param {RequestInit} [init]
 * @returns {Promise<Response>}
 */
async function fetchWithTimeout(url, init = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), SYNC_FETCH_TIMEOUT_MS);
    try {
        return await fetch(url, { ...init, signal: controller.signal });
    } finally {
        clearTimeout(timer);
    }
}

// Solo se guardan respuestas completas (la Cache API no admite 206) y un fallo al guardar
// nunca debe impedir responder.
/**
 * @param {Cache} cache
 * @param {RequestInfo} key
 * @param {Response} response
 */
async function store(cache, key, response) {
    // Nunca guardar una redirección (p. ej. a /login si la sesión caducó) en lugar de la página
    if (response.status !== 200 || response.redirected) return;
    try {
        await cache.put(key, response);
    } catch (err) {
        console.warn('[sw] no se pudo guardar', key, err);
    }
}

// La instalación no descarga nada: la primera página suele ser el login (sin sesión) y el
// comunicador aún no se puede guardar. Cada página con sesión pide después que se complete
// la copia sin conexión (mensaje 'sync-offline'), y solo se descarga lo que falte.
sw.addEventListener('install', () => {
    sw.skipWaiting();
});

sw.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const names = await caches.keys();
        await Promise.all(names.filter((n) => n.startsWith('rehab-') && n !== CACHE).map((n) => caches.delete(n)));
        await sw.clients.claim();
    })());
});

sw.addEventListener('message', (event) => {
    if (event.data === 'sync-offline') event.waitUntil(syncOffline());
});

/** @type {Promise<void> | null} */
let syncing = null;

/** Evita dos sincronizaciones a la vez (varias pestañas o páginas seguidas). */
function syncOffline() {
    if (!syncing) syncing = syncOfflineNow().catch((err) => console.warn('[sw] copia sin conexión:', err)).finally(() => { syncing = null; });
    return syncing;
}

async function syncOfflineNow() {
    const cache = await caches.open(CACHE);
    const page = await fetchWithTimeout(SHELL_PAGE, { cache: 'no-store' });
    // Sin sesión se recibe la página de login: no se guarda nada (se reintentará tras iniciar sesión)
    if (!page.ok || page.redirected) return;
    const html = await page.clone().text();
    await store(cache, SHELL_PAGE, page);

    /** @type {Set<string>} */
    const urls = new Set();
    for (const m of html.matchAll(/(?:href|src)="(\/static\/[^"]+)"/g)) urls.add(m[1]);

    const config = await fetchWithTimeout(CONFIG_URL, { cache: 'no-store' });
    if (config.ok && !config.redirected) {
        const data = await config.clone().json();
        await store(cache, CONFIG_URL, config);
        for (const item of /** @type {{icon_src?: string}[]} */ (data.items || [])) {
            if (item.icon_src && item.icon_src.startsWith('/static/')) urls.add(item.icon_src);
        }
    }

    const profile = await fetchWithTimeout(PROFILE_URL, { cache: 'no-store' });
    if (profile.ok && !profile.redirected) await store(cache, PROFILE_URL, profile);

    // La fuente de iconos se referencia desde su CSS (solo existe la versión woff2)
    for (const url of [...urls]) {
        if (url.includes('fontawesome.subset.css')) {
            const css = await (await fetchWithTimeout(url)).text();
            for (const m of css.matchAll(/url\(\.\.\/webfonts\/([^)]+\.woff2)\)/g)) urls.add('/static/vendor/fontawesome/webfonts/' + m[1]);
        }
    }

    // Quitar de la copia los estáticos que ya no usa el comunicador (versiones antiguas)
    for (const request of await cache.keys()) {
        const path = new URL(request.url).pathname + new URL(request.url).search;
        if (path.startsWith('/static/') && !urls.has(path)) await cache.delete(request);
    }

    // Descargar solo lo que falte, de 6 en 6 (todo a la vez hacía fallar descargas) y con reintento
    /** @type {string[]} */
    let pending = [];
    for (const url of urls) {
        if (!(await cache.match(url))) pending.push(url);
    }
    for (let attempt = 1; attempt <= 2 && pending.length; attempt++) {
        pending = await downloadAll(cache, pending, 6);
    }
    if (pending.length) console.warn(`[sw] ${pending.length} recursos no se pudieron guardar`, pending);
}

/**
 * Descarga y guarda las URLs con un máximo de descargas simultáneas.
 * @param {Cache} cache
 * @param {string[]} urls
 * @param {number} concurrency
 * @returns {Promise<string[]>} las URLs que fallaron
 */
async function downloadAll(cache, urls, concurrency) {
    /** @type {string[]} */
    const failed = [];
    const queue = [...urls];
    const worker = async () => {
        for (let url = queue.shift(); url !== undefined; url = queue.shift()) {
            try {
                const response = await fetchWithTimeout(url);
                if (response.status !== 200) throw new Error(`HTTP ${response.status}`);
                await store(cache, url, response);
            } catch (err) {
                failed.push(url);
            }
        }
    };
    await Promise.all(Array.from({ length: concurrency }, worker));
    return failed;
}

sw.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') return;
    const url = new URL(request.url);
    if (url.origin !== sw.location.origin) return;

    if (url.pathname === SHELL_PAGE || url.pathname === CONFIG_URL || url.pathname === PROFILE_URL) {
        event.respondWith(networkFirst(request, url.pathname));
    } else if (url.pathname.startsWith('/api/speak/')) {
        event.respondWith(speech(event, url));
    } else if (url.pathname.startsWith('/static/')) {
        const hashed = url.searchParams.has('v') || /\.[0-9a-f]{10}\.[a-z0-9]+$/.test(url.pathname);
        event.respondWith(hashed ? cacheFirst(request) : staleWhileRevalidate(event, request));
    }
});

/**
 * @template T
 * @param {Promise<T>} promise
 * @param {number} ms
 * @returns {Promise<T>}
 */
function withTimeout(promise, ms) {
    return Promise.race([promise, new Promise((_, reject) => { setTimeout(() => reject(new Error('timeout')), ms); })]);
}

/**
 * @param {Request} request
 * @param {string} key
 * @returns {Promise<Response>}
 */
async function networkFirst(request, key) {
    const cache = await caches.open(CACHE);
    try {
        const response = await withTimeout(fetch(request), NETWORK_TIMEOUT_MS);
        await store(cache, key, response.clone());
        return response;
    } catch (err) {
        const cached = await cache.match(key);
        if (cached) return cached;
        throw err;
    }
}

/**
 * @param {Request} request
 * @returns {Promise<Response>}
 */
async function cacheFirst(request) {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(request);
    if (cached) return cached;
    const response = await fetch(request);
    await store(cache, request, response.clone());
    return response;
}

/**
 * @param {FetchEvent} event
 * @param {Request} request
 * @returns {Promise<Response>}
 */
async function staleWhileRevalidate(event, request) {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(request);
    const refresh = fetch(request).then(async (response) => {
        await store(cache, request, response.clone());
        return response;
    });
    if (cached) {
        event.waitUntil(refresh.catch(() => {}));
        return cached;
    }
    return refresh;
}

// La voz se guarda por texto + velocidad (se ignora cualquier parámetro anti-caché).
// El reproductor pide el audio por rangos (206): se descarga completo (200) para poder guardarlo.
// Si el servidor tarda más que el límite, la página usa la voz del dispositivo, pero la respuesta
// se guarda igualmente cuando llega: la próxima vez esa frase ya funciona sin conexión.
/**
 * @param {FetchEvent} event
 * @param {URL} url
 * @returns {Promise<Response>}
 */
async function speech(event, url) {
    const key = new URL(url.pathname, sw.location.origin);
    const speed = url.searchParams.get('speed');
    if (speed) key.searchParams.set('speed', speed);
    const cache = await caches.open(CACHE);
    const network = fetch(key.href).then(async (response) => {
        await store(cache, key.href, response.clone());
        return response;
    });
    event.waitUntil(network.catch(() => {}));
    try {
        return await withTimeout(network, SPEECH_TIMEOUT_MS);
    } catch (err) {
        const cached = await cache.match(key.href);
        if (cached) return cached;
        throw err;
    }
}
