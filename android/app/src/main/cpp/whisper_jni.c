// Puente JNI mínimo con whisper.cpp para org.rehabvoice.app.WhisperEngine.
// Mismos parámetros que el servidor (voice_processor.py): español, sin traducir, sin contexto
// previo, búsqueda en haz (beam) y temperatura configurables, pista inicial opcional.
#include <jni.h>
#include <stdlib.h>
#include <string.h>
#include <android/log.h>
#include "whisper.h"

#define TAG "RehabWhisper"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, TAG, __VA_ARGS__)

static void quiet_log(enum ggml_log_level level, const char *text, void *user) {
    (void) user;
    if (level >= GGML_LOG_LEVEL_WARN) __android_log_write(ANDROID_LOG_WARN, TAG, text);
}

JNIEXPORT jlong JNICALL
Java_org_rehabvoice_app_WhisperEngine_nativeInit(JNIEnv *env, jclass cls, jstring jpath) {
    (void) cls;
    whisper_log_set(quiet_log, NULL);
    const char *path = (*env)->GetStringUTFChars(env, jpath, NULL);
    struct whisper_context_params cparams = whisper_context_default_params();
    cparams.use_gpu = false;
    struct whisper_context *ctx = whisper_init_from_file_with_params(path, cparams);
    (*env)->ReleaseStringUTFChars(env, jpath, path);
    LOGI("modelo cargado: %s", ctx ? "sí" : "NO");
    return (jlong) (intptr_t) ctx;
}

JNIEXPORT void JNICALL
Java_org_rehabvoice_app_WhisperEngine_nativeFree(JNIEnv *env, jclass cls, jlong handle) {
    (void) env; (void) cls;
    if (handle) whisper_free((struct whisper_context *) (intptr_t) handle);
}

JNIEXPORT jbyteArray JNICALL
Java_org_rehabvoice_app_WhisperEngine_nativeTranscribe(JNIEnv *env, jclass cls, jlong handle, jfloatArray jpcm,
                                                       jstring jprompt, jint beam, jfloat temperature, jint threads) {
    (void) cls;
    struct whisper_context *ctx = (struct whisper_context *) (intptr_t) handle;
    if (!ctx) return NULL;

    struct whisper_full_params p = whisper_full_default_params(
            beam > 1 ? WHISPER_SAMPLING_BEAM_SEARCH : WHISPER_SAMPLING_GREEDY);
    p.n_threads = threads > 0 ? threads : 4;
    p.language = "es";
    p.translate = false;
    p.no_context = true;
    p.single_segment = false;
    p.print_progress = false;
    p.print_realtime = false;
    p.print_special = false;
    p.print_timestamps = false;
    p.suppress_blank = true;
    p.temperature = temperature;
    if (beam > 1) {
        p.beam_search.beam_size = beam;
    } else {
        p.greedy.best_of = 5;
    }

    const char *prompt = NULL;
    if (jprompt) {
        prompt = (*env)->GetStringUTFChars(env, jprompt, NULL);
        if (prompt && prompt[0]) p.initial_prompt = prompt;
    }

    jsize n = (*env)->GetArrayLength(env, jpcm);
    jfloat *pcm = (*env)->GetFloatArrayElements(env, jpcm, NULL);
    int rc = whisper_full(ctx, p, pcm, n);
    (*env)->ReleaseFloatArrayElements(env, jpcm, pcm, JNI_ABORT);
    if (prompt) (*env)->ReleaseStringUTFChars(env, jprompt, prompt);
    if (rc != 0) return NULL;

    // Une el texto de todos los segmentos
    size_t cap = 256, len = 0;
    char *out = malloc(cap);
    if (!out) return NULL;
    out[0] = '\0';
    int segments = whisper_full_n_segments(ctx);
    for (int i = 0; i < segments; i++) {
        const char *t = whisper_full_get_segment_text(ctx, i);
        size_t tl = strlen(t);
        if (len + tl + 2 > cap) {
            while (len + tl + 2 > cap) cap *= 2;
            char *grown = realloc(out, cap);
            if (!grown) { free(out); return NULL; }
            out = grown;
        }
        if (len && out[len - 1] != ' ' && t[0] != ' ') out[len++] = ' ';
        memcpy(out + len, t, tl);
        len += tl;
        out[len] = '\0';
    }
    // Como bytes: NewStringUTF aborta con UTF-8 incompleto (Whisper puede cortar un carácter)
    jbyteArray result = (*env)->NewByteArray(env, (jsize) len);
    if (result) (*env)->SetByteArrayRegion(env, result, 0, (jsize) len, (const jbyte *) out);
    free(out);
    return result;
}
