// @ts-check
// Construye UNA frase con sentido a partir de los pictogramas que se pulsan en el comunicador.
//
// Cada pictograma tiene un papel (acción, persona, objeto, lugar, comida, sentimiento,
// respuesta...) y la frase se arma relacionándolos, sin importar el orden en que se pulsen:
//
//   Caminar + Hijo              → «Quiero caminar con mi hijo»
//   Llamar + Hija               → «Quiero llamar a mi hija»
//   Baño + Enfermera            → «Necesito que la enfermera me ayude a ir al baño»
//   Compañía + Esposa           → «Quiero que mi esposa me acompañe»
//   Medicina + Hijo             → «Hijo, necesito mi medicina»   (a quién se le habla)
//   Lentes + Leer               → «Necesito mis lentes para leer un libro»
//   Salir + Parque + Nieto      → «Quiero salir al parque con mi nieto»
//   Dolor cabeza + Dolor pecho  → «Me duelen la cabeza y el pecho»
//   No + Agua                   → «No quiero agua»
//   Frío + Dormir               → «Tengo frío y necesito dormir»
//
// Un pictograma solo dice su frase de siempre (default_phrase).
// Uso: buildPhrase(items) — items son los pictogramas de /api/aac/config.
// Pruebas de las combinaciones: tests/test_phrase_builder.py (ejecuta este archivo con Node).

/**
 * @typedef {'with' | 'help' | 'obj' | 'helpgen' | 'accompany'} Mode
 *   Cómo se relaciona una persona con la acción:
 *   with = «… con mi hijo», help = «Necesito que mi hijo me ayude a …», obj = «llamar a mi hijo»,
 *   helpgen = «Necesito que mi hijo me ayude», accompany = «Quiero que mi hijo me acompañe».
 *
 * @typedef {{kind: 'act', head: string, inf: string, mode?: Mode, imp?: boolean,
 *            objInf?: string, placeVerb?: string, place?: 'go' | 'at' | 'through'}} Act
 *   head + inf = la frase («Quiero» + «caminar»). objInf: infinitivo cuando lleva persona
 *   («llamar» en vez de «hacer una llamada»). placeVerb/place: cómo se une a un lugar.
 * @typedef {{kind: 'place', head: string, go: string, at?: string, through?: string}} Place
 * @typedef {{kind: 'person', head: string, np: string, voc: string}} Person
 * @typedef {{kind: 'thing', np: string}} Thing      objeto que se necesita («mi medicina»)
 * @typedef {{kind: 'food', np: string}} Food
 * @typedef {{kind: 'state', head: string, rest: string}} State   «Estoy» + «cansado»
 * @typedef {{kind: 'pain', part: string}} Pain                   «Me duele» + «la cabeza»
 * @typedef {{kind: 'yes' | 'no' | 'please' | 'more' | 'greeting' | 'phrase', imp?: boolean}} Other
 *   phrase = frase fija (con imp, va como oración aparte: «Abre la puerta por favor»)
 * @typedef {Act | Place | Person | Thing | Food | State | Pain | Other} Lexeme
 *
 * @typedef {{id: string, label: string, default_phrase?: string | null, category_id?: string | null,
 *            grammar?: {noun?: string} | null}} Item
 */

/** @type {Record<string, Lexeme>} */
const LEXICON = {
    // --- Acciones (se hacen CON alguien) ---
    walk: { kind: 'act', head: 'Quiero', inf: 'caminar', mode: 'with', place: 'through' },
    watch_tv: { kind: 'act', head: 'Quiero', inf: 'ver televisión', mode: 'with', place: 'at' },
    aac_tv: { kind: 'act', head: 'Quiero', inf: 'ver televisión', mode: 'with', place: 'at' },
    listen: { kind: 'act', head: 'Quiero', inf: 'escuchar música', mode: 'with', place: 'at' },
    read: { kind: 'act', head: 'Quiero', inf: 'leer un libro', mode: 'with', place: 'at' },
    write: { kind: 'act', head: 'Quiero', inf: 'escribir', mode: 'with', place: 'at' },
    paint: { kind: 'act', head: 'Quiero', inf: 'pintar', mode: 'with', place: 'at' },
    rest: { kind: 'act', head: 'Quiero', inf: 'descansar un rato', mode: 'with', place: 'at' },
    go_out: { kind: 'act', head: 'Quiero', inf: 'salir afuera', mode: 'with', placeVerb: 'salir', place: 'go' },
    pray: { kind: 'act', head: 'Quiero', inf: 'rezar', mode: 'with', place: 'at' },
    aac_dog: { kind: 'act', head: 'Quiero', inf: 'ver al perro', mode: 'with' },
    aac_cat: { kind: 'act', head: 'Quiero', inf: 'ver al gato', mode: 'with' },
    call: { kind: 'act', head: 'Quiero', inf: 'hacer una llamada', objInf: 'llamar', mode: 'obj' },

    // --- Acciones en las que alguien AYUDA ---
    help_up: { kind: 'act', head: 'Ayúdame a', inf: 'levantarme', mode: 'help', imp: true },
    sit_down: { kind: 'act', head: 'Quiero', inf: 'sentarme', mode: 'help' },
    position: { kind: 'act', head: 'Necesito', inf: 'cambiar de posición', mode: 'help' },
    toilet: { kind: 'act', head: 'Necesito', inf: 'ir al baño', mode: 'help' },
    aac_bed: { kind: 'act', head: 'Quiero', inf: 'ir a la cama', mode: 'help' },
    charge_phone: { kind: 'act', head: 'Necesito', inf: 'cargar mi celular', mode: 'help' },
    shower: { kind: 'act', head: 'Quiero', inf: 'bañarme', mode: 'help' },
    wash_hands: { kind: 'act', head: 'Quiero', inf: 'lavarme las manos', mode: 'help' },
    brush_teeth: { kind: 'act', head: 'Quiero', inf: 'lavarme los dientes', mode: 'help' },
    comb: { kind: 'act', head: 'Ayúdame a', inf: 'peinarme', mode: 'help', imp: true },
    groom: { kind: 'act', head: 'Necesito', inf: 'afeitarme', mode: 'help' },
    change_clothes: { kind: 'act', head: 'Quiero', inf: 'cambiarme de ropa', mode: 'help' },
    nails: { kind: 'act', head: 'Necesito', inf: 'cortarme las uñas', mode: 'help' },
    aac_shirt: { kind: 'act', head: 'Quiero', inf: 'ponerme la camisa', mode: 'help' },
    sleep: { kind: 'act', head: 'Necesito', inf: 'dormir' },
    help_gen: { kind: 'act', head: 'Necesito', inf: 'ayuda por favor', mode: 'helpgen' },
    company: { kind: 'act', head: 'Quiero', inf: 'compañía', mode: 'accompany' },

    // --- Lugares ---
    aac_park: { kind: 'place', head: 'Vamos', go: 'al parque', at: 'en el parque', through: 'por el parque' },
    aac_home_place: { kind: 'place', head: 'Quiero ir', go: 'a casa', at: 'en casa' },
    aac_store: { kind: 'place', head: 'Vamos', go: 'a la tienda', at: 'en la tienda', through: 'por la tienda' },
    aac_hospital: { kind: 'place', head: 'Necesito ir', go: 'al doctor' },

    // --- Personas ---
    doctor: { kind: 'person', head: 'Necesito', np: 'el doctor', voc: 'Doctor' },
    nurse: { kind: 'person', head: 'Necesito', np: 'la enfermera', voc: 'Enfermera' },
    caregiver: { kind: 'person', head: 'Necesito', np: 'mi cuidador', voc: 'Cuidador' },
    family: { kind: 'person', head: 'Quiero ver', np: 'mi familia', voc: 'Familia' },
    son: { kind: 'person', head: 'Quiero ver', np: 'mi hijo', voc: 'Hijo' },
    daughter: { kind: 'person', head: 'Quiero ver', np: 'mi hija', voc: 'Hija' },
    husband: { kind: 'person', head: 'Quiero ver', np: 'mi esposo', voc: 'Esposo' },
    wife: { kind: 'person', head: 'Quiero ver', np: 'mi esposa', voc: 'Esposa' },
    grandson: { kind: 'person', head: 'Quiero ver', np: 'mi nieto', voc: 'Nieto' },
    granddaughter: { kind: 'person', head: 'Quiero ver', np: 'mi nieta', voc: 'Nieta' },
    friend: { kind: 'person', head: 'Quiero ver', np: 'un amigo', voc: 'Amigo' },
    neighbor: { kind: 'person', head: 'Quiero ver', np: 'mi vecino', voc: 'Vecino' },
    priest: { kind: 'person', head: 'Quiero ver', np: 'el sacerdote', voc: 'Padre' },

    // --- Objetos que se necesitan ---
    wheelchair: { kind: 'thing', np: 'mi silla de ruedas' },
    glasses: { kind: 'thing', np: 'mis lentes' },
    aac_glasses: { kind: 'thing', np: 'mis lentes' },
    tv_remote: { kind: 'thing', np: 'el control de la TV' },
    phone: { kind: 'thing', np: 'el teléfono' },
    medicine: { kind: 'thing', np: 'mi medicina' },
    pillbox: { kind: 'thing', np: 'mi pastillero' },
    hearing_aid: { kind: 'thing', np: 'mi audífono' },
    dentures: { kind: 'thing', np: 'mi dentadura' },
    aac_shoes: { kind: 'thing', np: 'mis zapatos' },
    aac_chair: { kind: 'thing', np: 'una silla' },
    quiet: { kind: 'thing', np: 'silencio' },

    // --- Sentimientos y estado ---
    happy: { kind: 'state', head: 'Estoy', rest: 'feliz' },
    sad: { kind: 'state', head: 'Estoy', rest: 'triste' },
    tired: { kind: 'state', head: 'Estoy', rest: 'cansado' },
    angry: { kind: 'state', head: 'Estoy', rest: 'enojado' },
    bored: { kind: 'state', head: 'Estoy', rest: 'aburrido' },
    good: { kind: 'state', head: 'Estoy', rest: 'bien' },
    bad: { kind: 'state', head: 'Estoy', rest: 'mal' },
    dizzy: { kind: 'state', head: 'Me siento', rest: 'mareado' },
    pain: { kind: 'state', head: 'Tengo', rest: 'dolor' },
    scared: { kind: 'state', head: 'Tengo', rest: 'miedo' },
    cold: { kind: 'state', head: 'Tengo', rest: 'frío' },
    heat: { kind: 'state', head: 'Tengo', rest: 'calor' },
    pain_head: { kind: 'pain', part: 'la cabeza' },
    pain_chest: { kind: 'pain', part: 'el pecho' },
    pain_stomach: { kind: 'pain', part: 'la panza' },
    pain_back: { kind: 'pain', part: 'la espalda' },
    pain_throat: { kind: 'pain', part: 'la garganta' },
    pain_arm: { kind: 'pain', part: 'el brazo' },
    pain_leg: { kind: 'pain', part: 'la pierna' },

    // --- Respuestas y frases fijas ---
    yes: { kind: 'yes' },
    no: { kind: 'no' },
    please: { kind: 'please' },
    more: { kind: 'more' },
    hello: { kind: 'greeting' },
    bye: { kind: 'greeting' },
    light_on: { kind: 'phrase', imp: true },
    aac_door: { kind: 'phrase', imp: true },
    aac_fish: { kind: 'phrase', imp: true },
    aac_bird: { kind: 'phrase', imp: true },
};

const FOOD_CATEGORIES = ['food', 'drink'];

/**
 * Papel de un pictograma; los que no están en el diccionario se deducen de su categoría.
 * @param {Item} item
 * @returns {Lexeme}
 */
function lexemeOf(item) {
    const known = LEXICON[item.id];
    if (known) return known;
    const noun = (item.grammar && item.grammar.noun) || item.label.toLowerCase();
    if (FOOD_CATEGORIES.includes(item.category_id || '')) return { kind: 'food', np: noun };
    if (item.category_id === 'people') return { kind: 'person', head: 'Quiero ver', np: `mi ${noun}`, voc: item.label };
    return { kind: 'phrase' };
}

/** «a» + frase nominal, con la contracción «a el» → «al». @param {string} np */
const toA = (np) => (np.startsWith('el ') ? `al ${np.slice(3)}` : `a ${np}`);

/**
 * «A, B y C» (con «e» delante de palabras que empiezan por sonido i: «levantarme e ir»).
 * @param {string[]} parts
 */
function joinList(parts) {
    if (parts.length <= 1) return parts.join('');
    const last = /** @type {string} */ (parts[parts.length - 1]);
    const and = /^h?i(?![aeouáéóú])/i.test(last) ? 'e' : 'y';
    return `${parts.slice(0, -1).join(', ')} ${and} ${last}`;
}

/** @param {string} s */
const lowerFirst = (s) => s.replace(/^(¿|¡)?(\p{L})/u, (_, mark, ch) => (mark || '') + ch.toLowerCase());
/** @param {string} s */
const upperFirst = (s) => s.replace(/^(¿|¡)?(\p{L})/u, (_, mark, ch) => (mark || '') + ch.toUpperCase());
/** @param {string} s */
const isQuestionOrExclamation = (s) => /[?!]$/.test(s.trim());

/**
 * @typedef {{pos: number, text: string, standalone: boolean, negatable: boolean,
 *            greeting?: boolean, response?: boolean, neg?: boolean, yes?: boolean, no?: boolean,
 *            please?: boolean}} Clause
 *   Una oración. standalone: va como oración aparte (preguntas, órdenes, respuestas);
 *   si no, se une con las vecinas («Tengo frío y quiero dormir»).
 */

/**
 * @param {Item[]} items
 * @returns {string}
 */
function buildPhrase(items) {
    if (!items || items.length === 0) return '';
    if (items.length === 1) return defaultPhrase(/** @type {Item} */ (items[0]));

    /** @type {{item: Item, lex: Lexeme, pos: number}[]} */
    const all = [];
    const seen = new Set();
    items.forEach((item, pos) => {
        if (seen.has(item.id)) return; // pulsar dos veces lo mismo no lo repite en la frase
        seen.add(item.id);
        all.push({ item, lex: lexemeOf(item), pos });
    });
    if (all.length === 1) return defaultPhrase(/** @type {Item} */ (items[0]));

    /** @param {string} kind */
    const take = (kind) => all.filter((e) => e.lex.kind === kind);
    const people = take('person');
    const personLex = people.map((e) => /** @type {Person} */ (e.lex));
    const nps = joinList(personLex.map((p) => p.np));
    const npsWithA = joinList(personLex.map((p) => toA(p.np)));
    const plural = personLex.length > 1;
    /** Se ha relacionado a las personas con alguna acción (si no, se les habla: «Hijo, …») */
    let peopleUsed = false;

    /** @type {Clause[]} */
    const clauses = [];
    /** @param {number} pos @param {string} text @param {{standalone?: boolean, negatable?: boolean, greeting?: boolean, response?: boolean}} [opts] */
    const add = (pos, text, opts = {}) => clauses.push({
        pos, text, standalone: opts.standalone ?? isQuestionOrExclamation(text),
        negatable: opts.negatable ?? !isQuestionOrExclamation(text), greeting: opts.greeting, response: opts.response,
    });

    // --- Acciones, con su lugar y objeto si los hay ---
    /** @typedef {{entry: typeof all[number], lex: Act, inf: string, placed: boolean}} ActUse */
    /** @type {ActUse[]} */
    const acts = take('act').map((e) => {
        const lex = /** @type {Act} */ (e.lex);
        return { entry: e, lex, inf: lex.inf, placed: false };
    });

    // Lugar: «caminar por el parque», «salir al parque», «leer en casa»
    const places = take('place');
    const unusedPlaces = [];
    for (const p of places) {
        const place = /** @type {Place} */ (p.lex);
        const act = acts.find((a) => a.lex.place && !a.placed && place[a.lex.place]);
        if (act && act.lex.place) {
            act.inf = `${act.lex.placeVerb || act.lex.inf} ${place[act.lex.place]}`;
            act.placed = true;
        } else {
            unusedPlaces.push(p);
        }
    }

    /**
     * El infinitivo de una acción con las personas, si se pueden relacionar («caminar con mi hijo»).
     * @param {ActUse} a
     */
    const actCore = (a) => {
        if (!personLex.length) return a.inf;
        if (a.lex.mode === 'with') { peopleUsed = true; return `${a.inf} con ${nps}`; }
        if (a.lex.mode === 'obj') { peopleUsed = true; return `${a.lex.objInf || a.inf} ${npsWithA}`; }
        return a.inf;
    };

    // Objeto + acción: «Necesito mis lentes para leer un libro»
    const things = take('thing');
    const thingNps = things.map((e) => /** @type {Thing} */ (e.lex).np);
    if (things.length) {
        const pos = Math.min(...things.map((e) => e.pos));
        const forAct = acts.find((a) => a.lex.mode !== 'helpgen' && a.lex.mode !== 'accompany');
        if (forAct) {
            acts.splice(acts.indexOf(forAct), 1);
            add(Math.min(pos, forAct.entry.pos), `Necesito ${joinList(thingNps)} para ${actCore(forAct)}`);
        } else if (things.length === 1) {
            add(pos, defaultPhrase(/** @type {typeof all[number]} */ (things[0]).item));
        } else {
            add(pos, `Necesito ${joinList(thingNps)}`);
        }
    }

    // Acciones agrupadas: con personas según cómo se relacionan; sin ellas, por su verbo
    // («Quiero caminar y escuchar música»).
    /** @type {Map<string, ActUse[]>} */
    const groups = new Map();
    for (const a of acts) {
        const helped = personLex.length && (a.lex.mode === 'help' || a.lex.mode === 'helpgen' || a.lex.mode === 'accompany');
        const key = helped ? `mode:${a.lex.mode}` : `head:${a.lex.head}|${personLex.length ? a.lex.mode : ''}`;
        groups.set(key, [...(groups.get(key) || []), a]);
    }
    for (const [key, group] of groups) {
        const first = /** @type {ActUse} */ (group[0]);
        const pos = first.entry.pos;
        const verb3 = plural ? 'ayuden' : 'ayude';
        if (key === 'mode:help') {
            peopleUsed = true;
            add(pos, `Necesito que ${nps} me ${verb3} a ${joinList(group.map((a) => a.inf))}`);
        } else if (key === 'mode:helpgen') {
            peopleUsed = true;
            add(pos, `Necesito que ${nps} me ${verb3}`);
        } else if (key === 'mode:accompany') {
            peopleUsed = true;
            add(pos, `Quiero que ${nps} me ${plural ? 'acompañen' : 'acompañe'}`);
        } else if (group.length === 1 && !first.placed && !personLex.length) {
            add(pos, defaultPhrase(first.entry.item), { standalone: first.lex.imp });
        } else if (first.lex.mode === 'with' && personLex.length) {
            // La compañía va una sola vez al final: «Quiero caminar y rezar con mi hijo»
            peopleUsed = true;
            add(pos, `${first.lex.head} ${joinList(group.map((a) => a.inf))} con ${nps}`);
        } else {
            add(pos, `${first.lex.head} ${joinList(group.map(actCore))}`, { standalone: first.lex.imp });
        }
    }

    // Lugares sueltos: «Vamos al parque con mi hijo», «Vamos al parque y a la tienda»
    /** @type {Map<string, typeof all>} */
    const placeGroups = new Map();
    for (const p of unusedPlaces) {
        const head = /** @type {Place} */ (p.lex).head;
        placeGroups.set(head, [...(placeGroups.get(head) || []), p]);
    }
    for (const [head, group] of placeGroups) {
        let text = `${head} ${joinList(group.map((p) => /** @type {Place} */ (p.lex).go))}`;
        if (personLex.length) { text += ` con ${nps}`; peopleUsed = true; }
        add(/** @type {typeof all[number]} */ (group[0]).pos, text);
    }

    // Comida y bebida: «Quiero más café con leche y pan»
    const food = take('food');
    if (food.length) {
        const names = food.map((e) => /** @type {Food} */ (e.lex).np);
        // «café/té» + «leche» → «café con leche»
        const milk = names.indexOf('leche');
        const hot = names.findIndex((n) => n === 'café' || n === 'té');
        if (milk >= 0 && hot >= 0) {
            names[hot] = `${names[hot]} con leche`;
            names.splice(milk, 1);
        }
        const more = take('more').length ? 'más ' : '';
        const pos = Math.min(...food.map((e) => e.pos));
        if (food.length === 1 && !more) add(pos, defaultPhrase(/** @type {typeof all[number]} */ (food[0]).item));
        else add(pos, `Quiero ${more}${joinList(names)}`);
    } else if (take('more').length) {
        add(/** @type {typeof all[number]} */ (take('more')[0]).pos, 'Quiero más');
    }

    // Sentimientos: «Estoy cansado y triste», «Tengo frío y miedo»
    /** @type {Map<string, typeof all>} */
    const states = new Map();
    for (const e of take('state')) {
        const head = /** @type {State} */ (e.lex).head;
        states.set(head, [...(states.get(head) || []), e]);
    }
    for (const [head, group] of states) {
        const first = /** @type {typeof all[number]} */ (group[0]);
        add(first.pos, group.length === 1 ? defaultPhrase(first.item)
            : `${head} ${joinList(group.map((e) => /** @type {State} */ (e.lex).rest))}`);
    }

    // Dolores: «Me duelen la cabeza y la espalda»
    const pains = take('pain');
    if (pains.length) {
        const parts = pains.map((e) => /** @type {Pain} */ (e.lex).part);
        add(Math.min(...pains.map((e) => e.pos)), `${parts.length > 1 ? 'Me duelen' : 'Me duele'} ${joinList(parts)}`);
    }

    // Frases fijas y saludos, cada una en su sitio
    for (const e of [...take('phrase'), ...take('greeting')]) {
        const lex = /** @type {Other} */ (e.lex);
        const text = defaultPhrase(e.item);
        const greeting = lex.kind === 'greeting';
        // «Gracias», «Espera un momento»… son respuestas: van como oración aparte
        const isResponse = e.item.category_id === 'responses' || greeting;
        add(e.pos, text, { standalone: lex.imp || isResponse || isQuestionOrExclamation(text), negatable: false, greeting, response: isResponse });
    }

    // Solo personas: «Quiero ver a mi hijo y a mi hija», «Necesito al doctor y a la enfermera»
    // (con solo un saludo, se le habla: «Hola, hijo»)
    if (personLex.length && clauses.length === 0) {
        /** @type {Map<string, Person[]>} */
        const byHead = new Map();
        for (const p of personLex) byHead.set(p.head, [...(byHead.get(p.head) || []), p]);
        for (const [head, group] of byHead) {
            const firstPos = people.find((e) => /** @type {Person} */ (e.lex).head === head)?.pos ?? 0;
            add(firstPos, `${head} ${joinList(group.map((p) => toA(p.np)))}`);
        }
        peopleUsed = true;
    }

    clauses.sort((a, b) => a.pos - b.pos);

    // Respuestas que modifican a su vecina: «No» + «Quiero agua» → «No quiero agua»;
    // «Sí» + … → «Sí, …»; «Por favor» se añade a la frase anterior (o a la siguiente).
    for (const e of all) {
        const kind = e.lex.kind;
        if (kind !== 'yes' && kind !== 'no' && kind !== 'please') continue;
        const next = clauses.find((c) => c.pos > e.pos && !c.greeting);
        const prev = [...clauses].reverse().find((c) => c.pos < e.pos && !c.greeting);
        if (kind === 'no' && next && next.negatable && !next.neg && !next.yes) next.neg = true;
        else if (kind === 'no' && next && next.response && !next.yes && !next.neg) next.no = true; // «No, gracias»
        else if (kind === 'yes' && next && !next.yes && !next.neg) next.yes = true;
        else if (kind === 'please' && (prev || next)) /** @type {Clause} */ (prev || next).please = true;
        else add(e.pos, defaultPhrase(e.item), { standalone: true, negatable: false });
    }
    clauses.sort((a, b) => a.pos - b.pos);

    for (const c of clauses) {
        if (c.neg) c.text = `No ${lowerFirst(c.text)}`;
        if (c.please && !/por favor/i.test(c.text)) {
            c.text = isQuestionOrExclamation(c.text) ? c.text.replace(/([?!])$/, ', por favor$1') : `${c.text}, por favor`;
        }
        if (c.yes || c.no) { c.text = `${c.yes ? 'Sí' : 'No'}, ${lowerFirst(c.text)}`; c.standalone = true; }
    }

    // A quién se le habla si no se relacionó con ninguna acción: «Hijo, necesito mi medicina»
    // (con un saludo delante: «Hola, hijo. Necesito mi medicina»)
    const vocative = personLex.length && !peopleUsed ? joinList(personLex.map((p, i) => (i ? lowerFirst(p.voc) : p.voc))) : '';

    /** @type {string[]} */
    const sentences = [];
    /** @type {string[]} */
    let current = [];
    const flush = () => {
        if (current.length) sentences.push(upperFirst(joinList(current.map((t, i) => (i ? lowerFirst(t) : t)))));
        current = [];
    };
    let vocativeDone = !vocative;
    for (const c of clauses) {
        let text = c.text;
        if (!vocativeDone) {
            text = c.greeting ? `${text}, ${lowerFirst(vocative)}` : `${vocative}, ${lowerFirst(text)}`;
            vocativeDone = true;
        }
        if (c.standalone) { flush(); sentences.push(upperFirst(text)); } else current.push(text);
    }
    flush();

    return sentences.reduce((out, s) => (out ? `${out}${isQuestionOrExclamation(out) ? ' ' : '. '}${s}` : s), '');
}

/** @param {Item} item */
function defaultPhrase(item) {
    return (item.default_phrase || item.label).trim();
}
