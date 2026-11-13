// @ts-check
/**
 * Puntuación de pronunciación: traducción fiel de la parte «pura» de voice_processor.py
 * (_score_transcription y todo lo que usa). La usa la app Android sin servidor; el test
 * tests/test_scoring_parity.py comprueba que da EXACTAMENTE lo mismo que Python.
 *
 * Si cambias la puntuación en voice_processor.py, cambia también este archivo.
 * Se carga como script clásico: expone el global `RehabScoring`.
 */
var RehabScoring = (function () {
    'use strict';

    const MAX_EXTRA_WORDS = 3;
    const EXTRA_WORD_PENALTY = 5;
    const VOWELS = 'aeiouáéíóú';
    const STOP_WORDS = new Set([
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
        'de', 'del', 'al', 'a', 'en', 'por', 'para', 'con',
        'me', 'te', 'se', 'le', 'lo', 'que', 'y', 'o', 'pero',
        'mi', 'tu', 'su', 'muy', 'mas', 'ya',
    ]);

    /** Como `str.split()` de Python: separa por espacios y descarta vacíos. */
    const words = (/** @type {string} */ s) => s.split(/\s+/).filter(Boolean);
    /** Longitud en caracteres (como len() de Python, no en unidades UTF-16). */
    const len = (/** @type {string} */ s) => Array.from(s).length;
    /** `c in s` de Python con cadenas: '' está en cualquier cadena (igual que includes). */
    const inStr = (/** @type {string} */ c, /** @type {string} */ s) => s.includes(c);
    const count = (/** @type {string} */ s, /** @type {string} */ sub) => s.split(sub).length - 1;

    /** @param {string} chars */
    function stripChars(text, chars) {
        const a = Array.from(text);
        let i = 0, j = a.length;
        while (i < j && chars.includes(a[i])) i++;
        while (j > i && chars.includes(a[j - 1])) j--;
        return a.slice(i, j).join('');
    }

    /** @param {string} text */
    function cleanWhisperOutput(text) {
        if (!text) return '';
        text = text.replace(/\[.*?\]/g, '').replace(/\(.*?\)/g, '');
        text = text.replace(/[.,!?;:]+/g, '');
        text = text.replace(/["'«»]/g, '');
        text = stripChars(text, '-–— ');
        return words(text).join(' ').trim();
    }

    /** @param {string} text */
    function normalizeText(text) {
        if (!text) return '';
        text = text.toLowerCase().trim().normalize('NFD');
        let out = '';
        for (const c of text) {
            if (/\p{Mn}/u.test(c)) continue;
            if (/[\p{L}\p{N}]/u.test(c) || /\s/u.test(c)) out += c;
        }
        return words(out).join(' ');
    }

    /** Código fonético tolerante para español (mismas reglas, y rarezas, que Python). */
    function spanishMetaphone(word) {
        if (!word) return '';
        const w = Array.from(word.toLowerCase().trim());
        const n = w.length;
        let code = '';
        let i = 0;
        while (i < n) {
            const c = w[i];
            const next = i + 1 < n ? w[i + 1] : '';
            const prev = i > 0 ? w[i - 1] : '';
            const third = i + 2 < n ? w[i + 2] : '';

            if (c === 'h' && prev !== 'c') { i += 1; continue; }
            if (c === 'c' && next === 'h') { code += 'x'; i += 2; continue; }
            if (c === 'l' && next === 'l') { code += 'y'; i += 2; continue; }
            if (c === 'r' && next === 'r') { code += 'rr'; i += 2; continue; }
            if (c === 'r' && i === 0) { code += 'rr'; i += 1; continue; }
            if (c === 'v') { code += 'b'; i += 1; continue; }
            if (c === 'z' || c === 's') { code += 's'; i += 1; continue; }
            if (c === 'c') { code += (next === 'e' || next === 'i') ? 's' : 'k'; i += 1; continue; }
            if (c === 'q') { code += 'k'; i += next === 'u' ? 2 : 1; continue; }
            if (c === 'k') { code += 'k'; i += 1; continue; }
            if (c === 'x') {
                code += (i === 0 || !inStr(next, VOWELS)) ? 'j' : 'ks';
                i += 1; continue;
            }
            if (c === 'g') {
                if (next === 'e' || next === 'i') code += 'j';
                else if (next === 'u') {
                    if (third === 'e' || third === 'i') { code += 'g'; i += 2; continue; }
                    code += 'g';
                } else code += 'g';
                i += 1; continue;
            }
            if (c === 'y') { code += (inStr(next, VOWELS) || i === 0) ? 'y' : 'i'; i += 1; continue; }
            if (c === 'ñ') { code += 'ny'; i += 1; continue; }
            if (c === 'w') { code += 'u'; i += 1; continue; }
            if (c === 'j') { code += 'j'; i += 1; continue; }
            code += c;
            i += 1;
        }

        /** @type {string[]} */
        const out = [];
        const cc = Array.from(code);
        i = 0;
        while (i < cc.length) {
            const pair = cc.slice(i, i + 2).join('');
            if (pair === 'rr' || pair === 'ny' || pair === 'ks') { out.push(pair); i += 2; }
            else if (out.length > 0 && cc[i] === out[out.length - 1] && !inStr(cc[i], 'aeiou')) i += 1;
            else { out.push(cc[i]); i += 1; }
        }
        return out.join('');
    }

    /**
     * Distancia de edición sobre secuencias (caracteres o palabras).
     * @template T @param {T[]} a @param {T[]} b
     */
    function editDistance(a, b) {
        if (a.length < b.length) [a, b] = [b, a];
        if (b.length === 0) return a.length;
        let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
        for (let i = 0; i < a.length; i++) {
            const cur = [i + 1];
            for (let j = 0; j < b.length; j++) {
                cur.push(Math.min(prev[j + 1] + 1, cur[j] + 1, prev[j] + (a[i] !== b[j] ? 1 : 0)));
            }
            prev = cur;
        }
        return prev[prev.length - 1];
    }

    const levenshtein = (/** @type {string} */ s1, /** @type {string} */ s2) => editDistance(Array.from(s1), Array.from(s2));

    function stringSimilarity(s1, s2) {
        if (!s1 || !s2) return 0;
        return Math.max(0, (1 - levenshtein(s1, s2) / Math.max(len(s1), len(s2))) * 100);
    }

    /** jiwer.wer(referencia, hipótesis): errores de palabra / palabras de la referencia. */
    function wordErrorRate(reference, hypothesis) {
        const ref = words(reference), hyp = words(hypothesis);
        if (!ref.length) throw new Error('referencia vacía');
        return editDistance(ref, hyp) / ref.length;
    }

    function phoneticSimilarity(text1, text2) {
        if (!text1 || !text2) return { spanish_metaphone: 0, average: 0 };
        if (text1 === text2) return { spanish_metaphone: 100, average: 100 };
        const p1 = words(text1).map(spanishMetaphone).join(' ');
        const p2 = words(text2).map(spanishMetaphone).join(' ');
        if (p1 === p2) return { spanish_metaphone: 100, average: 100 };
        const lev = stringSimilarity(p1, p2);
        return { spanish_metaphone: lev, average: lev };
    }

    function textSimilarity(text1, text2) {
        if (!text1 && !text2) return { exact_match: 0, levenshtein: 0, wer: 0, average: 0 };
        if (text1 === text2) return { exact_match: 100, levenshtein: 100, wer: 100, average: 100 };
        /** @type {Record<string, number>} */
        const s = {};
        s.exact_match = 0;
        s.levenshtein = Math.max(0, (1 - levenshtein(text1, text2) / Math.max(len(text1), len(text2), 1)) * 100);
        if (text1 && text2) {
            try {
                s.wer = Math.max(0, (1 - wordErrorRate(text2, text1)) * 100);
            } catch (_) {
                s.wer = s.levenshtein;
            }
        } else {
            s.wer = s.levenshtein;
        }
        s.average = s.exact_match * 0.3 + s.levenshtein * 0.35 + s.wer * 0.35;
        return s;
    }

    function finalScore(phonetic, text) {
        const p = phonetic.average || 0;
        const t = text.average || 0;
        if (t > 90 && (text.levenshtein || 0) > 90) return t;
        const [wp, wt] = (p > 80 && t < 60) ? [0.6, 0.4] : [0.4, 0.6];
        return Math.min(100, Math.max(0, p * wp + t * wt));
    }

    function toleranceThreshold(level, wordLength, offset = 0) {
        const base = { 1: 60, 2: 65, 3: 68, 4: 72, 5: 75 };
        let t = Object.prototype.hasOwnProperty.call(base, level) ? base[level] : 70;
        if (wordLength <= 3) t -= 5;
        else if (wordLength >= 20) t -= 3;
        t = Math.max(50, Math.min(80, t));
        return Math.max(40, Math.min(90, t + Math.max(-15, Math.min(15, offset))));
    }

    function phraseSimilarity(transcription, target) {
        const transWords = new Set(words(normalizeText(transcription)));
        const targetWords = new Set(words(normalizeText(target)));
        let transSig = new Set([...transWords].filter((w) => !STOP_WORDS.has(w)));
        let targetSig = new Set([...targetWords].filter((w) => !STOP_WORDS.has(w)));
        if (!targetSig.size) { targetSig = targetWords; transSig = transWords; }
        if (!targetSig.size) return transSig.size ? 0 : 100;

        let matched = 0;
        for (const tw of targetSig) {
            const twPhone = spanishMetaphone(tw);
            let best = 0;
            for (const trw of transSig) best = Math.max(best, stringSimilarity(twPhone, spanishMetaphone(trw)));
            if (best > 75) matched += 1;
        }
        let coverage = (matched / targetSig.size) * 100;
        const extra = transSig.size - targetSig.size;
        if (extra > 2) coverage -= Math.min(15, extra * 3);
        return Math.max(0, coverage);
    }

    function detectSpecificErrors(transcription, target) {
        const errors = [];
        const transNorm = normalizeText(transcription);
        const targetNorm = normalizeText(target);
        const transPhone = spanishMetaphone(transNorm);
        const targetPhone = spanishMetaphone(targetNorm);

        if (len(transNorm) < len(targetNorm) * 0.6 && transNorm) {
            errors.push({ type: 'truncation', message: 'La palabra parece estar incompleta',
                tip: 'Intenta pronunciar hasta el final de cada sílaba, sin cortarte' });
        }
        if (!transNorm.trim()) {
            errors.push({ type: 'silence', message: 'No se detectó audio claro',
                tip: 'Habla más fuerte y cerca del micrófono' });
            return errors;
        }
        if (targetPhone.includes('rr') || targetPhone.includes('r')) {
            if (transPhone.includes('l') && !targetPhone.includes('l')) {
                errors.push({ type: 'r_l_confusion', message: 'Posible confusión entre R y L',
                    tip: 'Para la R, haz vibrar la punta de la lengua contra el paladar' });
            }
        }
        const nasal = (/** @type {string} */ p) => count(p, 'm') + count(p, 'n') + count(p, 'ny');
        if (nasal(targetPhone) > 0 && nasal(transPhone) < nasal(targetPhone)) {
            errors.push({ type: 'nasal_error', message: 'Falta pronunciar algún sonido nasal (M, N, Ñ)',
                tip: 'Los sonidos nasales requieren que el aire salga por la nariz' });
        }
        const sTarget = count(targetPhone, 's'), sTrans = count(transPhone, 's');
        if (sTarget > 0 && Math.abs(sTarget - sTrans) >= 1 && sTrans < sTarget) {
            errors.push({ type: 'sibilant_missing', message: 'Falta pronunciar el sonido S',
                tip: 'Pronuncia la S con los dientes casi cerrados y la lengua detrás' });
        }
        if (targetPhone.includes('x') && !transPhone.includes('x')) {
            errors.push({ type: 'ch_error', message: 'Falta el sonido CH',
                tip: 'El sonido CH se forma bloqueando el aire con la lengua y soltándolo de golpe' });
        }
        const jTarget = count(targetPhone, 'j'), jTrans = count(transPhone, 'j');
        if (jTarget > 0 && jTrans < jTarget) {
            errors.push({ type: 'j_error', message: 'Falta el sonido J (o G fuerte)',
                tip: 'El sonido J es fricativo, el aire pasa rozando el velo del paladar' });
        }
        return errors.slice(0, 3);
    }

    function findDifferences(transcription, target) {
        if (transcription === target) return [];
        if (!transcription && target) return [{ position: 0, expected: target, heard: '' }];
        if (transcription && !target) return [{ position: 0, expected: '', heard: transcription }];
        const wt = words(transcription), wg = words(target);
        const diffs = [];
        for (let i = 0; i < Math.max(wt.length, wg.length); i++) {
            const heard = wt[i] || '', expected = wg[i] || '';
            if (heard !== expected) diffs.push({ position: i, expected, heard });
        }
        return diffs;
    }

    function pronunciationTips(differences) {
        if (!differences.length) return ['¡Excelente pronunciación!'];
        const tips = [];
        for (const d of differences.slice(0, 3)) {
            const expected = d.expected || '', heard = d.heard || '';
            if (!expected && heard) tips.push(`Se detectó '${heard}' adicional. Intenta decir solo la palabra objetivo.`);
            else if (expected && !heard) tips.push(`Parece que faltó pronunciar '${expected}'.`);
            else if (expected && heard) tips.push(`'${expected}' sonó como '${heard}'. Enfatiza cada sílaba.`);
        }
        if (!tips.length) tips.push('Intenta hablar más despacio y claro.');
        return tips;
    }

    function generateFeedback(score, transcription, target, isCorrect, threshold = 70) {
        if (isCorrect === undefined || isCorrect === null) isCorrect = score >= threshold;
        let level, message, encouragement, shouldRepeat;
        if (isCorrect && score >= 90) {
            level = 'excellent'; message = '¡Excelente! Lo dijiste muy bien.'; encouragement = 'Sigue así.'; shouldRepeat = false;
        } else if (isCorrect) {
            level = 'good'; message = '¡Bien dicho!';
            encouragement = 'Puedes pasar a la siguiente o repetirla para afianzarla.'; shouldRepeat = false;
        } else if (score >= threshold - 15) {
            level = 'fair'; message = 'Casi. Vas por buen camino.';
            encouragement = 'Escucha el ejemplo y dilo despacio y claro.'; shouldRepeat = true;
        } else {
            level = 'retry'; message = 'Vamos a intentarlo otra vez.';
            encouragement = 'Escucha el ejemplo y repítelo con calma.'; shouldRepeat = true;
        }
        const differences = findDifferences(transcription, target);
        return { level, message, encouragement, should_repeat: shouldRepeat, differences,
            tips: pronunciationTips(differences) };
    }

    function perfectResult(transcription, target, level, score, toleranceOffset) {
        return {
            success: true, transcription, target,
            scores: {
                phonetic: { spanish_metaphone: score, average: score },
                text: { exact_match: score, levenshtein: score, wer: score, average: score },
                final: score,
                threshold: toleranceThreshold(level, len(target), toleranceOffset),
            },
            feedback: {
                level: 'excellent', message: '¡Excelente! Lo dijiste muy bien.', encouragement: 'Sigue así.',
                should_repeat: false, differences: [], tips: ['¡Perfecto! Continúa con la siguiente palabra.'],
            },
            is_correct: true, level, timestamp: new Date().toISOString(),
        };
    }

    function scoreCore(transcription, targetWord, level = 1, toleranceOffset = 0) {
        transcription = cleanWhisperOutput(transcription);
        const transClean = normalizeText(transcription);
        const targetClean = normalizeText(targetWord);
        const targetPhone = spanishMetaphone(targetClean);

        if (transClean && targetClean) {
            if (transClean === targetClean) return perfectResult(transcription, targetWord, level, 100, toleranceOffset);
            if (spanishMetaphone(transClean) === targetPhone) {
                return perfectResult(transcription, targetWord, level, 95, toleranceOffset);
            }
        }

        /** @type {Record<string, number>} */
        const phonetic = phoneticSimilarity(transClean, targetClean);
        const text = textSimilarity(transClean, targetClean);
        if ((targetClean ? words(targetClean).length : 0) >= 2) {
            const phrase = phraseSimilarity(transClean, targetClean);
            phonetic.phrase_similarity = phrase;
            phonetic.average = (phonetic.spanish_metaphone || 0) * 0.5 + phrase * 0.5;
        }
        const final = finalScore(phonetic, text);
        const threshold = toleranceThreshold(level, targetClean ? len(targetClean) : 0, toleranceOffset);
        const isCorrect = final >= threshold;
        const specific = detectSpecificErrors(transClean, targetClean);
        /** @type {Record<string, any>} */
        const feedback = generateFeedback(final, transClean, targetClean, isCorrect, threshold);
        if (specific.length && !isCorrect) {
            feedback.specific_errors = specific;
            feedback.tips = specific.map((e) => e.tip);
        }
        return {
            success: true, transcription, target: targetWord,
            scores: { phonetic, text, final, threshold },
            feedback, is_correct: isCorrect, level, timestamp: new Date().toISOString(),
        };
    }

    function bestWindow(transClean, targetClean) {
        const ws = words(transClean);
        const tw = words(targetClean);
        const n = tw.length;
        if (!n || ws.length <= n) return ['', 0];
        const targetPhone = tw.map(spanishMetaphone).join(' ');
        let best = '', bestSim = -1;
        for (let i = 0; i <= ws.length - n; i++) {
            const cand = ws.slice(i, i + n);
            const sim = stringSimilarity(cand.map(spanishMetaphone).join(' '), targetPhone);
            if (sim > bestSim) { best = cand.join(' '); bestSim = sim; }
        }
        return [best, ws.length - n];
    }

    /**
     * Puntúa lo que se oyó frente a la palabra objetivo (= VoiceProcessor._score_transcription).
     * @param {string} transcription @param {string} targetWord
     * @param {number} [level] @param {number} [toleranceOffset]
     */
    function scoreTranscription(transcription, targetWord, level = 1, toleranceOffset = 0) {
        const base = scoreCore(transcription, targetWord, level, toleranceOffset);
        const [window, extra] = bestWindow(normalizeText(cleanWhisperOutput(transcription)), normalizeText(targetWord));
        if (!window || !(extra >= 1 && extra <= MAX_EXTRA_WORDS)) return base;
        const w = scoreCore(window, targetWord, level, toleranceOffset);
        const adjusted = Math.max(0, w.scores.final - EXTRA_WORD_PENALTY * extra);
        if (adjusted <= base.scores.final) return base;
        const threshold = w.scores.threshold;
        const isCorrect = adjusted >= threshold;
        w.transcription = base.transcription;
        w.scores = { ...w.scores, final: adjusted, extra_words: extra };
        w.is_correct = isCorrect;
        w.feedback = generateFeedback(adjusted, window, normalizeText(targetWord), isCorrect, threshold);
        return w;
    }

    return {
        scoreTranscription, normalizeText, cleanWhisperOutput, spanishMetaphone,
        stringSimilarity, toleranceThreshold, levenshtein,
    };
})();
