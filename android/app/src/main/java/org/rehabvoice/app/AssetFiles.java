package org.rehabvoice.app;

import android.content.Context;
import android.content.res.AssetManager;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/** Copia modelos de la APK a la memoria de la app (las bibliotecas nativas necesitan rutas reales). */
final class AssetFiles {
    private AssetFiles() {}

    /** Copia un archivo de assets la primera vez (o tras actualizar la app) y devuelve su ruta. */
    static synchronized File copyOnce(Context ctx, String asset) throws IOException {
        File dst = new File(new File(ctx.getFilesDir(), "assets-" + versionCode(ctx)), asset);
        if (dst.exists()) return dst;
        cleanOldVersions(ctx);
        copy(ctx.getAssets(), asset, dst);
        return dst;
    }

    /** Copia una carpeta de assets entera (p. ej. la voz con espeak-ng-data). */
    static synchronized File copyDirOnce(Context ctx, String assetDir) throws IOException {
        File dst = new File(new File(ctx.getFilesDir(), "assets-" + versionCode(ctx)), assetDir);
        File done = new File(dst, ".copied");
        if (done.exists()) return dst;
        cleanOldVersions(ctx);
        copyTree(ctx.getAssets(), assetDir, dst);
        if (!done.createNewFile() && !done.exists()) throw new IOException("No se pudo marcar " + dst);
        return dst;
    }

    private static void copyTree(AssetManager am, String path, File dst) throws IOException {
        String[] children = am.list(path);
        if (children == null || children.length == 0) {
            copy(am, path, dst);
            return;
        }
        for (String child : children) copyTree(am, path + "/" + child, new File(dst, child));
    }

    private static void copy(AssetManager am, String asset, File dst) throws IOException {
        File parent = dst.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) throw new IOException("No se pudo crear " + parent);
        File tmp = new File(dst.getPath() + ".part");
        try (InputStream in = am.open(asset); OutputStream out = new FileOutputStream(tmp)) {
            byte[] buf = new byte[1 << 16];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        }
        if (!tmp.renameTo(dst)) throw new IOException("No se pudo guardar " + dst);
    }

    private static void cleanOldVersions(Context ctx) {
        String keep = "assets-" + versionCode(ctx);
        File[] old = ctx.getFilesDir().listFiles((d, name) -> name.startsWith("assets-") && !name.equals(keep));
        if (old != null) for (File f : old) deleteTree(f);
    }

    private static void deleteTree(File f) {
        File[] kids = f.listFiles();
        if (kids != null) for (File k : kids) deleteTree(k);
        //noinspection ResultOfMethodCallIgnored
        f.delete();
    }

    /** Cambia con cada instalación o actualización: así nunca se usa un modelo copiado de otra versión. */
    private static long versionCode(Context ctx) {
        try {
            return ctx.getPackageManager().getPackageInfo(ctx.getPackageName(), 0).lastUpdateTime;
        } catch (Exception e) {
            return 0;
        }
    }
}
