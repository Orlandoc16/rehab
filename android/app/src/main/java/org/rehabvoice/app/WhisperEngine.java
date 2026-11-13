package org.rehabvoice.app;

import android.content.Context;
import android.util.Log;

import java.io.File;
import java.nio.charset.StandardCharsets;

/**
 * Reconocimiento de voz en la tablet con whisper.cpp y el mismo modelo «base» que el servidor.
 * La lógica de reintentos es la de VoiceProcessor.transcribe_with_retry (voice_processor.py).
 * No es seguro llamarlo desde varios hilos a la vez: lo usa un solo hilo (ver NativeBridge).
 */
final class WhisperEngine {
    static final String MODEL_ASSET = "models/ggml-base-q8_0.bin";
    private static final String TAG = "RehabWhisper";

    static {
        System.loadLibrary("rehab_whisper");
    }

    private static native long nativeInit(String modelPath);
    private static native void nativeFree(long handle);
    private static native byte[] nativeTranscribe(long handle, float[] pcm, String prompt, int beam,
                                                  float temperature, int threads);

    private final Context context;
    private long handle;

    WhisperEngine(Context context) {
        this.context = context.getApplicationContext();
    }

    /** Carga el modelo en segundo plano al abrir la app (sin transcribir nada). */
    void preload() throws Exception {
        ensureLoaded();
    }

    /** Carga el modelo (la primera vez lo copia de la APK a la memoria de la app). */
    private synchronized void ensureLoaded() throws Exception {
        if (handle != 0) return;
        File model = AssetFiles.copyOnce(context, MODEL_ASSET);
        long started = System.currentTimeMillis();
        handle = nativeInit(model.getAbsolutePath());
        if (handle == 0) throw new IllegalStateException("No se pudo cargar el modelo de Whisper");
        Log.i(TAG, "modelo listo en " + (System.currentTimeMillis() - started) + " ms");
    }

    private static int threads() {
        return Math.max(2, Math.min(4, Runtime.getRuntime().availableProcessors() - 1));
    }

    private String run(float[] pcm, String prompt, int beam, float temperature) {
        byte[] bytes = nativeTranscribe(handle, pcm, prompt, beam, temperature, threads());
        return bytes == null ? "" : new String(bytes, StandardCharsets.UTF_8).trim();
    }

    private static boolean isEmpty(String t) {
        String s = t == null ? "" : t.trim();
        return s.isEmpty() || s.equals("[BLANK_AUDIO]") || s.equals("...");
    }

    /**
     * @param pcm   audio 16 kHz mono en [-1, 1]
     * @param prompt pista inicial (null o vacía: sin pista)
     * @param retry true = como analyze() (reintenta si no se oye nada); false = una pasada
     */
    synchronized String transcribe(float[] pcm, String prompt, boolean retry) throws Exception {
        ensureLoaded();
        long started = System.currentTimeMillis();
        String text = run(pcm, prompt, 5, 0f);
        if (retry && isEmpty(text)) text = run(pcm, prompt, 3, 0.2f);
        if (isEmpty(text)) text = "";
        Log.i(TAG, "transcripción en " + (System.currentTimeMillis() - started) + " ms (" + pcm.length / 16 + " ms de audio)");
        return text;
    }

    synchronized void close() {
        if (handle != 0) nativeFree(handle);
        handle = 0;
    }
}
