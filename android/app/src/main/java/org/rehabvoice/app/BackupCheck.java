package org.rehabvoice.app;

import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;

import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

/** Comprueba que un archivo es una base de Rehab Voice antes de sustituir la de la tablet. */
final class BackupCheck {
    private BackupCheck() {}

    static boolean looksLikeRehabDb(File f) {
        byte[] head = new byte[16];
        try (FileInputStream in = new FileInputStream(f)) {
            if (in.read(head) != 16) return false;
        } catch (Exception e) {
            return false;
        }
        if (!Arrays.equals(head, "SQLite format 3\0".getBytes(StandardCharsets.US_ASCII))) return false;
        try (SQLiteDatabase db = SQLiteDatabase.openDatabase(f.getPath(), null, SQLiteDatabase.OPEN_READONLY);
             Cursor c = db.rawQuery("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN ('patients', 'progress', 'words')", null)) {
            return c.moveToFirst() && c.getInt(0) == 3;
        } catch (Exception e) {
            return false;
        }
    }
}
