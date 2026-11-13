package org.rehabvoice.app;

import android.database.Cursor;
import android.database.sqlite.SQLiteCursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteProgram;
import android.database.sqlite.SQLiteStatement;
import android.util.Base64;
import android.util.Log;
import android.webkit.JavascriptInterface;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Interfaz `RehabNative` que usa static/js/app/bridge.js:
 * base de datos SQLite, reconocimiento de voz (Whisper) y copias de seguridad.
 */
final class NativeBridge {
    static final String DB_NAME = "rehab_voice.db";
    private static final String TAG = "RehabBridge";

    private final MainActivity activity;
    private final WhisperEngine whisper;
    private final ExecutorService speechThread = Executors.newSingleThreadExecutor();
    private SQLiteDatabase db;

    NativeBridge(MainActivity activity) {
        this.activity = activity;
        this.whisper = new WhisperEngine(activity);
        openDb();
        // Carga el modelo en segundo plano para que el primer intento no espere la copia
        speechThread.execute(() -> {
            try {
                Thread.currentThread().setPriority(Thread.MIN_PRIORITY);
                whisper.preload();
                Thread.currentThread().setPriority(Thread.NORM_PRIORITY);
            } catch (Throwable t) {
                Log.w(TAG, "No se pudo precargar Whisper", t);
            }
        });
    }

    File dbFile() {
        return activity.getDatabasePath(DB_NAME);
    }

    synchronized void openDb() {
        File f = dbFile();
        File parent = f.getParentFile();
        if (parent != null) //noinspection ResultOfMethodCallIgnored
            parent.mkdirs();
        db = SQLiteDatabase.openOrCreateDatabase(f, null);
        // Diario clásico (no WAL): el archivo .db está siempre completo y se puede copiar tal cual
        db.disableWriteAheadLogging();
    }

    synchronized void closeDb() {
        if (db != null && db.isOpen()) db.close();
        db = null;
    }

    // ------------------------------------------------------------------ SQL

    private static void bind(SQLiteProgram prog, JSONArray params) throws Exception {
        for (int i = 0; i < params.length(); i++) {
            Object v = params.get(i);
            int idx = i + 1;
            if (v == JSONObject.NULL) prog.bindNull(idx);
            else if (v instanceof Boolean) prog.bindLong(idx, ((Boolean) v) ? 1 : 0);
            else if (v instanceof Integer || v instanceof Long) prog.bindLong(idx, ((Number) v).longValue());
            else if (v instanceof Number) prog.bindDouble(idx, ((Number) v).doubleValue());
            else prog.bindString(idx, v.toString());
        }
    }

    private static String error(Throwable t) {
        try {
            return new JSONObject().put("error", String.valueOf(t.getMessage())).toString();
        } catch (Exception e) {
            return "{\"error\":\"error\"}";
        }
    }

    @JavascriptInterface
    public synchronized String sqlAll(String sql, String paramsJson) {
        try {
            JSONArray params = new JSONArray(paramsJson);
            JSONArray rows = new JSONArray();
            try (Cursor c = db.rawQueryWithFactory((database, driver, table, query) -> {
                try {
                    bind(query, params);
                } catch (Exception e) {
                    throw new IllegalArgumentException(e);
                }
                return new SQLiteCursor(driver, table, query);
            }, sql, null, null)) {
                String[] cols = c.getColumnNames();
                while (c.moveToNext()) {
                    JSONObject row = new JSONObject();
                    for (int i = 0; i < cols.length; i++) {
                        switch (c.getType(i)) {
                            case Cursor.FIELD_TYPE_NULL: row.put(cols[i], JSONObject.NULL); break;
                            case Cursor.FIELD_TYPE_INTEGER: row.put(cols[i], c.getLong(i)); break;
                            case Cursor.FIELD_TYPE_FLOAT: row.put(cols[i], c.getDouble(i)); break;
                            default: row.put(cols[i], c.getString(i));
                        }
                    }
                    rows.put(row);
                }
            }
            return new JSONObject().put("rows", rows).toString();
        } catch (Throwable t) {
            Log.e(TAG, "sqlAll: " + sql, t);
            return error(t);
        }
    }

    @JavascriptInterface
    public synchronized String sqlRun(String sql, String paramsJson) {
        try {
            String head = sql.trim().toUpperCase();
            // Las transacciones van por la API de Android (execSQL("BEGIN") no se permite)
            if (head.equals("BEGIN")) { db.beginTransaction(); return "{}"; }
            if (head.equals("COMMIT")) { db.setTransactionSuccessful(); db.endTransaction(); return "{}"; }
            if (head.equals("ROLLBACK")) { if (db.inTransaction()) db.endTransaction(); return "{}"; }
            try (SQLiteStatement st = db.compileStatement(sql)) {
                bind(st, new JSONArray(paramsJson));
                if (head.startsWith("INSERT") || head.startsWith("UPDATE") || head.startsWith("DELETE") || head.startsWith("REPLACE")) {
                    return new JSONObject().put("changes", st.executeUpdateDelete()).toString();
                }
                st.execute();
                return "{}";
            }
        } catch (Throwable t) {
            Log.e(TAG, "sqlRun: " + sql, t);
            return error(t);
        }
    }

    // ------------------------------------------------------------------ voz

    @JavascriptInterface
    public void transcribe(String id, String pcm16Base64, String prompt, boolean retry) {
        speechThread.execute(() -> {
            try {
                byte[] bytes = Base64.decode(pcm16Base64, Base64.DEFAULT);
                ByteBuffer buf = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
                float[] pcm = new float[bytes.length / 2];
                for (int i = 0; i < pcm.length; i++) pcm[i] = buf.getShort() / 32768f;
                String text = whisper.transcribe(pcm, prompt == null || prompt.isEmpty() ? null : prompt, retry);
                activity.deliverTranscription(id, true, text);
            } catch (Throwable t) {
                Log.e(TAG, "transcribe", t);
                activity.deliverTranscription(id, false, String.valueOf(t.getMessage()));
            }
        });
    }

    // ------------------------------------------------------------------ copias de seguridad

    @JavascriptInterface
    public String exportBackup() {
        activity.runOnUiThread(activity::startBackupExport);
        return "Elige dónde guardar la copia…";
    }

    @JavascriptInterface
    public void importBackup() {
        activity.runOnUiThread(activity::startBackupImport);
    }

    void shutdown() {
        speechThread.shutdownNow();
        whisper.close();
        closeDb();
    }
}
