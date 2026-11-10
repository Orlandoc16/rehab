// @ts-check
// Lupa de lectura para personas con baja visión (cargada desde base.html en todas las páginas).
//
// Un botón flotante (abajo a la izquierda) la activa. Con la lupa activa, el texto del botón,
// enlace o frase que hay bajo el ratón se muestra en letra MUY grande y con alto contraste junto
// al puntero. También funciona con el teclado: al moverse con Tab se amplía el elemento enfocado.
//
// - Alt+L activa/desactiva la lupa; Esc la oculta hasta que se mueva el ratón.
// - El tamaño de letra se ajusta con los botones A− / A+ y se recuerda (localStorage) junto con
//   si estaba activa, para no tener que activarla en cada página.
// - Solo aparece en equipos con ratón o lápiz: en pantallas táctiles no hay "pasar por encima".
// No crea variables globales.
(() => {
    const STORAGE_KEY = 'rehab-lupa';
    const SIZES = [32, 40, 52, 64, 80];   // tamaño de letra de la lupa, en px
    const DEFAULT_SIZE = 2;               // índice en SIZES
    const MAX_CHARS = 220;                // las frases muy largas se recortan
    const OFFSET = 28;                    // separación entre el puntero y la lupa

    // Elementos cuyo texto completo tiene sentido leer de una vez
    const READABLE = [
        '[data-zoom-text]', 'button', 'a', 'label', 'summary', '[role="button"]', '[role="tab"]',
        'li', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'td', 'th', 'dt', 'dd', 'figcaption',
        'legend', 'option', 'blockquote',
    ].join(',');

    if (!window.matchMedia('(any-pointer: fine)').matches) return;

    /** @type {{on: boolean, size: number}} */
    const state = { on: false, size: DEFAULT_SIZE };
    try {
        const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        state.on = saved.on === true;
        if (Number.isInteger(saved.size) && saved.size >= 0 && saved.size < SIZES.length) state.size = saved.size;
    } catch { /* sin almacenamiento: valores por defecto */ }

    const save = () => {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* ignorar */ }
    };

    const css = `
#rv-lupa-bar{position:fixed;left:16px;bottom:16px;z-index:2147483000;display:flex;gap:8px;align-items:center;font-family:Poppins,system-ui,sans-serif}
#rv-lupa-bar button{min-width:56px;height:56px;border-radius:16px;border:2px solid #1f2937;background:#fff;color:#111827;font:600 20px/1 Poppins,system-ui,sans-serif;display:flex;align-items:center;justify-content:center;gap:8px;padding:0 14px;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.18)}
#rv-lupa-bar button:hover{background:#eef2ff}
#rv-lupa-bar button[aria-pressed="true"]{background:#111827;color:#fff;border-color:#111827}
#rv-lupa-bar .rv-lupa-size{display:none}
#rv-lupa-bar.rv-on .rv-lupa-size{display:flex}
#rv-lupa-bar button:disabled{opacity:.4;cursor:default}
#rv-lupa-bar svg{width:26px;height:26px;flex:none}
#rv-lupa-lens{position:fixed;left:0;top:0;z-index:2147483001;pointer-events:none;display:none;max-width:min(90vw,1100px);padding:.35em .6em;border:4px solid #111827;border-radius:18px;background:#fffbea;color:#000;font-family:Poppins,system-ui,sans-serif;font-weight:600;line-height:1.25;overflow-wrap:anywhere;white-space:pre-line;box-shadow:0 12px 40px rgba(0,0,0,.35)}
@media (max-width:640px){#rv-lupa-bar .rv-lupa-label{display:none}}
/* espacio al final de la página para que la barra no tape lo último (p. ej. el estado de la grabación) */
body.rv-lupa-space{padding-bottom:88px}
@media print{#rv-lupa-bar,#rv-lupa-lens{display:none!important}}`;

    const ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/><path d="M8 10.5h5M10.5 8v5"/></svg>';

    /**
     * @param {string} html
     * @param {string} label
     * @param {string} [cls]
     */
    const makeButton = (html, label, cls = '') => {
        const b = document.createElement('button');
        b.type = 'button';
        b.innerHTML = html;
        b.setAttribute('aria-label', label);
        b.title = label;
        if (cls) b.className = cls;
        return b;
    };

    function init() {
        const style = document.createElement('style');
        style.textContent = css;
        document.head.appendChild(style);

        const bar = document.createElement('div');
        bar.id = 'rv-lupa-bar';
        bar.setAttribute('role', 'group');
        bar.setAttribute('aria-label', 'Lupa de lectura');
        const toggle = makeButton(`${ICON}<span class="rv-lupa-label">Lupa</span>`, 'Lupa de lectura (Alt+L)');
        const smaller = makeButton('A−', 'Letra de la lupa más pequeña', 'rv-lupa-size');
        const bigger = makeButton('A+', 'Letra de la lupa más grande', 'rv-lupa-size');
        bar.append(toggle, smaller, bigger);

        const lens = document.createElement('div');
        lens.id = 'rv-lupa-lens';
        lens.setAttribute('aria-hidden', 'true'); // solo visual: los lectores de pantalla ya leen el original

        document.body.append(bar, lens);
        document.body.classList.add('rv-lupa-space');

        /** Último punto conocido del ratón, para recolocar la lupa al hacer scroll o cambiar el tamaño */
        let last = { x: 0, y: 0, hasPointer: false };
        let frame = 0;
        /** @type {Element | null} */
        let shownFor = null;

        const hide = () => {
            lens.style.display = 'none';
            shownFor = null;
        };

        const render = () => {
            toggle.setAttribute('aria-pressed', String(state.on));
            bar.classList.toggle('rv-on', state.on);
            smaller.disabled = state.size === 0;
            bigger.disabled = state.size === SIZES.length - 1;
            lens.style.fontSize = `${SIZES[state.size]}px`;
            if (!state.on) hide();
        };

        /**
         * Texto legible de un elemento (o '' si no hay nada que ampliar).
         * @param {Element} el
         */
        const textOf = (el) => {
            const custom = el.getAttribute('data-zoom-text');
            if (custom) return custom;
            if (el instanceof HTMLImageElement) return el.alt;
            if (el instanceof HTMLInputElement) {
                if (el.type === 'password' || el.type === 'hidden') return '';
                if (['button', 'submit', 'reset'].includes(el.type)) return el.value;
                return el.value || el.placeholder || (el.labels?.[0]?.innerText ?? '');
            }
            if (el instanceof HTMLTextAreaElement) return el.value || el.placeholder;
            if (el instanceof HTMLSelectElement) return el.selectedOptions[0]?.text ?? '';
            const text = el instanceof HTMLElement ? el.innerText : (el.textContent || '');
            return text || el.getAttribute('aria-label') || el.getAttribute('title') || '';
        };

        /**
         * Elemento cuyo texto se amplía para lo que hay bajo el puntero.
         * @param {Element | null} target
         * @returns {Element | null}
         */
        const readableFrom = (target) => {
            if (!target || bar.contains(target)) return null;
            if (target instanceof HTMLImageElement || target instanceof HTMLInputElement
                || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) {
                // Una imagen dentro de un botón: mejor el texto del botón (incluye la palabra)
                const control = target.closest('button, a, [role="button"]');
                return control && textOf(control).trim() ? control : target;
            }
            let ownText = false;
            for (const node of target.childNodes) {
                if (node.nodeType === Node.TEXT_NODE && node.textContent && node.textContent.trim()) { ownText = true; break; }
            }
            const block = target.closest(READABLE);
            // En una tarjeta-enlace con mucho texto, mejor solo el trozo que se señala
            if (block && ownText && block !== target && textOf(block).length > 80) return target;
            // Si no, el bloque completo; o el texto suelto (span, div...) si no hay bloque
            return block || (ownText ? target : null);
        };

        /**
         * @param {Element} el
         * @param {number} x
         * @param {number} y
         */
        const show = (el, x, y) => {
            let text = textOf(el).replace(/[ \t]+/g, ' ').replace(/\s*\n\s*/g, '\n').trim();
            if (!text) { hide(); return; }
            if (text.length > MAX_CHARS) text = `${text.slice(0, MAX_CHARS).trimEnd()}…`;
            if (shownFor !== el || lens.textContent !== text) lens.textContent = text;
            shownFor = el;
            lens.style.display = 'block';

            // Debajo y a la derecha del puntero; si no cabe, encima / a la izquierda
            const w = lens.offsetWidth;
            const h = lens.offsetHeight;
            const vw = document.documentElement.clientWidth;
            const vh = document.documentElement.clientHeight;
            let left = x - w / 2;
            left = Math.max(8, Math.min(left, vw - w - 8));
            let top = y + OFFSET;
            if (top + h > vh - 8) top = y - OFFSET - h;
            if (top < 8) top = Math.max(8, vh - h - 8);
            lens.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
        };

        const update = () => {
            frame = 0;
            if (!state.on || !last.hasPointer) return;
            const el = readableFrom(document.elementFromPoint(last.x, last.y));
            if (el) show(el, last.x, last.y); else hide();
        };

        const schedule = () => {
            if (!frame) frame = requestAnimationFrame(update);
        };

        document.addEventListener('pointermove', (event) => {
            if (event.pointerType === 'touch') return;
            last = { x: event.clientX, y: event.clientY, hasPointer: true };
            schedule();
        }, { passive: true });

        document.documentElement.addEventListener('pointerleave', () => {
            last.hasPointer = false;
            hide();
        });

        // Al hacer scroll el contenido bajo el puntero cambia
        window.addEventListener('scroll', schedule, { passive: true, capture: true });
        // Tras pulsar, el texto puede cambiar (p. ej. una frase nueva en el comunicador)
        document.addEventListener('click', () => setTimeout(schedule, 50), true);

        // Teclado: ampliar el elemento enfocado, junto a él
        document.addEventListener('focusin', (event) => {
            if (!state.on || !(event.target instanceof Element)) return;
            if (!event.target.matches(':focus-visible')) return; // foco por clic: ya lo sigue el ratón
            const el = readableFrom(event.target);
            if (!el) return;
            const r = event.target.getBoundingClientRect();
            last.hasPointer = false;
            show(el, r.left + r.width / 2, r.bottom - OFFSET / 2);
        });

        document.addEventListener('keydown', (event) => {
            if (event.altKey && !event.ctrlKey && !event.metaKey && event.code === 'KeyL') {
                event.preventDefault();
                setOn(!state.on);
            } else if (event.key === 'Escape' && lens.style.display !== 'none') {
                hide();
            }
        });

        /** @param {boolean} on */
        const setOn = (on) => {
            state.on = on;
            save();
            render();
            if (on) schedule();
        };

        toggle.addEventListener('click', () => setOn(!state.on));
        /** @param {number} delta */
        const resize = (delta) => {
            state.size = Math.max(0, Math.min(SIZES.length - 1, state.size + delta));
            save();
            render();
        };
        smaller.addEventListener('click', () => resize(-1));
        bigger.addEventListener('click', () => resize(1));

        render();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
