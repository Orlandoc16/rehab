// @ts-check
/**
 * Separación silábica del español ("a-gua", "ca-mi-nar"): traducción de syllables.py para la
 * app sin servidor. tests/test_scoring_parity.py comprueba que coincide con Python.
 * Script clásico: expone el global `RehabSyllables`.
 */
var RehabSyllables = (function () {
    'use strict';

    const VOWELS = new Set('aeiouáéíóúü');
    const STRONG = new Set('aeoáéóíú');
    const CLUSTERS = new Set(['pr', 'br', 'tr', 'dr', 'cr', 'gr', 'fr', 'pl', 'bl', 'cl', 'gl', 'fl']);
    const DIGRAPHS = new Set(['ch', 'll', 'rr']);

    /** @param {string[]} w @param {string[]} low */
    function units(w, low) {
        /** @type {[string, 'V'|'C'][]} */
        const out = [];
        let i = 0;
        while (i < w.length) {
            const c = low[i];
            const two = low.slice(i, i + 2).join('');
            const nxt = low[i + 2] || '';
            if (DIGRAPHS.has(two)) { out.push([w.slice(i, i + 2).join(''), 'C']); i += 2; }
            else if ((two === 'qu' || two === 'gu') && ['e', 'i', 'é', 'í'].includes(nxt)) {
                out.push([w.slice(i, i + 2).join(''), 'C']); i += 2;
            } else if (c === 'y') {
                const after = low[i + 1] || '';
                const isVowel = (after === '' || !VOWELS.has(after)) && i > 0;
                out.push([w[i], isVowel ? 'V' : 'C']); i += 1;
            } else if (VOWELS.has(c)) { out.push([w[i], 'V']); i += 1; }
            else { out.push([w[i], 'C']); i += 1; }
        }
        return out;
    }

    /** @param {string[]} cons */
    function splitConsonants(cons) {
        const n = cons.length;
        if (n <= 1) return 0;
        const lastTwo = (cons[n - 2] + cons[n - 1]).toLowerCase();
        if (n === 2) return CLUSTERS.has(lastTwo) ? 0 : 1;
        if (n === 3) return CLUSTERS.has(lastTwo) ? 1 : 2;
        return n - 2;
    }

    /** @param {string} word */
    function splitWord(word) {
        const w = Array.from(word);
        // lower() carácter a carácter, como Python (mantiene los índices alineados)
        const low = w.map((c) => c.toLowerCase());
        const u = units(w, low);
        if (!u.some(([, k]) => k === 'V')) return word ? [word] : [];

        /** @type {[number, number][]} */
        const nuclei = [];
        let i = 0;
        while (i < u.length) {
            if (u[i][1] !== 'V') { i += 1; continue; }
            const start = i;
            while (i + 1 < u.length && u[i + 1][1] === 'V') {
                const a = u[i][0].toLowerCase(), b = u[i + 1][0].toLowerCase();
                if (STRONG.has(a) && STRONG.has(b)) break;
                i += 1;
            }
            nuclei.push([start, i]);
            i += 1;
        }

        const starts = [0];
        for (let k = 0; k + 1 < nuclei.length; k++) {
            const endPrev = nuclei[k][1], startNext = nuclei[k + 1][0];
            const cons = u.slice(endPrev + 1, startNext).map(([t]) => t);
            starts.push(endPrev + 1 + splitConsonants(cons));
        }
        starts.push(u.length);
        const out = [];
        for (let k = 0; k + 1 < starts.length; k++) out.push(u.slice(starts[k], starts[k + 1]).map(([t]) => t).join(''));
        return out;
    }

    /** "beber agua" -> "be-ber a-gua" @param {string} text */
    function syllabify(text) {
        const words = (text || '').match(/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+/g) || [];
        return words.map((w) => splitWord(w).join('-')).join(' ');
    }

    return { syllabify, splitWord };
})();
