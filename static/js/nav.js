// @ts-check
// Menú móvil de la cabecera, compartido por todas las páginas (cargado desde base.html).
// No crea variables globales, así que no choca con los scripts de cada página.
document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('mobile-menu-btn');
    const menu = document.getElementById('mobile-menu');
    const icon = document.getElementById('menu-icon');
    if (!button || !menu) return;

    /** @param {boolean} open */
    const setOpen = (open) => {
        menu.classList.toggle('active', open);
        button.setAttribute('aria-expanded', String(open));
        button.setAttribute('aria-label', open ? 'Cerrar menú de navegación' : 'Abrir menú de navegación');
        icon?.classList.toggle('fa-bars', !open);
        icon?.classList.toggle('fa-times', open);
    };

    button.addEventListener('click', () => setOpen(!menu.classList.contains('active')));
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && menu.classList.contains('active')) {
            setOpen(false);
            button.focus();
        }
    });
});
