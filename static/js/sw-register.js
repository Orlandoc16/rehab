// @ts-check
// Registra el service worker (comunicador sin conexión). Los navegadores solo lo permiten
// con HTTPS o en localhost, igual que el micrófono.
if ('serviceWorker' in navigator) {
    window.addEventListener('load', async () => {
        try {
            await navigator.serviceWorker.register('/sw.js');
            // En cada página con sesión se pide completar la copia sin conexión del comunicador.
            // Solo se descarga lo que falte, así que si una descarga se corta, la siguiente página
            // la termina. En el login no hay sesión todavía: no tiene sentido pedirla.
            if (location.pathname === '/login') return;
            const registration = await navigator.serviceWorker.ready;
            registration.active?.postMessage('sync-offline');
        } catch (err) {
            console.warn('No se pudo activar el modo sin conexión:', err);
        }
    });
}
