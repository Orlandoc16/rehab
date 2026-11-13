package org.rehabvoice.app;

import android.content.Context;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.util.Log;

import com.k2fsa.sherpa.onnx.GeneratedAudio;
import com.k2fsa.sherpa.onnx.OfflineTts;
import com.k2fsa.sherpa.onnx.OfflineTtsConfig;
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig;
import com.k2fsa.sherpa.onnx.OfflineTtsVitsModelConfig;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Voz de /api/speak/: Piper con la misma voz que el servidor (es_MX-claude-high) mediante
 * sherpa-onnx; si no carga, la voz de Android. Los audios se guardan en caché (misma frase y
 * velocidad -> mismo archivo), como hace el servidor.
 */
final class VoiceSynth {
    private static final String TAG = "RehabVoiceSynth";
    private static final String VOICE_ASSETS = "tts/voice";

    private final Context context;
    private final File cacheDir;
    private OfflineTts piper;
    private boolean piperFailed;
    private TextToSpeech androidTts;
    private boolean androidReady;

    VoiceSynth(Context context) {
        this.context = context.getApplicationContext();
        this.cacheDir = new File(this.context.getCacheDir(), "tts");
        //noinspection ResultOfMethodCallIgnored
        cacheDir.mkdirs();
    }

    /** WAV con el texto dicho, o null si no hay ninguna voz disponible. */
    synchronized File synthesize(String text, String speed) {
        if (text == null || text.trim().isEmpty() || text.length() > 500) return null;
        // Igual que piper_tts.py: «lenta» alarga un 30 % (length_scale 1.3); el resto, normal
        boolean slow = "lenta".equals(speed);
        File out = new File(cacheDir, hash(text + "|" + (slow ? "lenta" : "normal")) + ".wav");
        if (out.exists() && out.length() > 44) return out;
        try {
            if (ensurePiper()) {
                GeneratedAudio audio = piper.generate(text, 0, slow ? 1f / 1.3f : 1f);
                writeWav(out, audio.getSamples(), audio.getSampleRate());
                return out;
            }
        } catch (Throwable t) {
            Log.e(TAG, "Piper falló; se usa la voz de Android", t);
        }
        return androidSynthesize(text, slow, out) ? out : null;
    }

    private boolean ensurePiper() {
        if (piper != null) return true;
        if (piperFailed) return false;
        try {
            File dir = AssetFiles.copyDirOnce(context, VOICE_ASSETS);
            OfflineTtsVitsModelConfig vits = new OfflineTtsVitsModelConfig();
            vits.setModel(new File(dir, "model.onnx").getAbsolutePath());
            vits.setTokens(new File(dir, "tokens.txt").getAbsolutePath());
            vits.setDataDir(new File(dir, "espeak-ng-data").getAbsolutePath());
            OfflineTtsModelConfig model = new OfflineTtsModelConfig();
            model.setVits(vits);
            model.setNumThreads(2);
            model.setProvider("cpu");
            OfflineTtsConfig config = new OfflineTtsConfig();
            config.setModel(model);
            long started = System.currentTimeMillis();
            piper = new OfflineTts(null, config);
            Log.i(TAG, "Piper listo en " + (System.currentTimeMillis() - started) + " ms");
            return true;
        } catch (Throwable t) {
            Log.e(TAG, "No se pudo cargar Piper", t);
            piperFailed = true;
            return false;
        }
    }

    // ------------------------------------------------------------------ voz de Android (respaldo)

    private boolean androidSynthesize(String text, boolean slow, File out) {
        if (!ensureAndroidTts()) return false;
        CountDownLatch done = new CountDownLatch(1);
        final boolean[] ok = {false};
        androidTts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
            @Override public void onStart(String id) {}
            @Override public void onDone(String id) { ok[0] = true; done.countDown(); }
            @Override @SuppressWarnings("deprecation") public void onError(String id) { done.countDown(); }
        });
        androidTts.setSpeechRate(slow ? 0.75f : 0.9f);
        int rc = androidTts.synthesizeToFile(text, new Bundle(), out, "rv");
        if (rc != TextToSpeech.SUCCESS) return false;
        try {
            done.await(15, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        return ok[0] && out.length() > 44;
    }

    private boolean ensureAndroidTts() {
        if (androidTts != null) return androidReady;
        CountDownLatch init = new CountDownLatch(1);
        androidTts = new TextToSpeech(context, status -> {
            androidReady = status == TextToSpeech.SUCCESS;
            init.countDown();
        });
        try {
            init.await(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        if (androidReady) {
            int r = androidTts.setLanguage(new Locale("es", "MX"));
            if (r < TextToSpeech.LANG_AVAILABLE) androidTts.setLanguage(new Locale("es", "ES"));
        }
        return androidReady;
    }

    // ------------------------------------------------------------------ utilidades

    private static void writeWav(File out, float[] samples, int rate) throws IOException {
        File tmp = new File(out.getPath() + ".part");
        ByteBuffer b = ByteBuffer.allocate(44 + samples.length * 2).order(ByteOrder.LITTLE_ENDIAN);
        b.put("RIFF".getBytes(StandardCharsets.US_ASCII)).putInt(36 + samples.length * 2)
                .put("WAVEfmt ".getBytes(StandardCharsets.US_ASCII)).putInt(16).putShort((short) 1).putShort((short) 1)
                .putInt(rate).putInt(rate * 2).putShort((short) 2).putShort((short) 16)
                .put("data".getBytes(StandardCharsets.US_ASCII)).putInt(samples.length * 2);
        for (float s : samples) b.putShort((short) Math.round(Math.max(-1f, Math.min(1f, s)) * 32767f));
        try (OutputStream os = new FileOutputStream(tmp)) {
            os.write(b.array());
        }
        if (!tmp.renameTo(out)) throw new IOException("No se pudo guardar " + out);
    }

    private static String hash(String s) {
        try {
            byte[] d = MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 16; i++) sb.append(String.format(Locale.ROOT, "%02x", d[i]));
            return sb.toString();
        } catch (Exception e) {
            return Integer.toHexString(s.hashCode());
        }
    }

    synchronized void close() {
        if (piper != null) piper.release();
        piper = null;
        if (androidTts != null) androidTts.shutdown();
        androidTts = null;
    }
}
