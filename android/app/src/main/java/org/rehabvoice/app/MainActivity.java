package org.rehabvoice.app;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.MimeTypeMap;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.window.OnBackInvokedDispatcher;

import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Collections;
import java.util.Date;
import java.util.Locale;

/**
 * Rehab Voice sin servidor: las páginas van dentro de la APK (assets/www, generadas por
 * tools/build_android_web.py) y se sirven desde https://appassets.androidplatform.net (origen
 * seguro: el micrófono solo funciona así). Las rutas /api/... las responde el servidor local en
 * JavaScript; /api/speak/... (la voz) se genera aquí con Piper.
 */
public class MainActivity extends Activity {

    static final String HOST = "appassets.androidplatform.net";
    static final String ORIGIN = "https://" + HOST;
    private static final String TAG = "RehabVoice";
    private static final int REQ_MIC = 1;
    private static final int REQ_EXPORT = 2;
    private static final int REQ_IMPORT = 3;

    private WebView webView;
    private NativeBridge bridge;
    private VoiceSynth voice;
    private PermissionRequest pendingPermission;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#f9fafb"));
        webView = new WebView(this);
        root.addView(webView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(root);
        applySystemBarInsets(root);

        bridge = new NativeBridge(this);
        voice = new VoiceSynth(this);
        configureWebView();
        registerBackHandler();

        if (savedInstanceState != null) webView.restoreState(savedInstanceState);
        else webView.loadUrl(ORIGIN + "/");
    }

    // ------------------------------------------------------------------ WebView

    private void configureWebView() {
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setUserAgentString(s.getUserAgentString() + " RehabVoiceApp/2.0");
        webView.addJavascriptInterface(bridge, "RehabNative");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (HOST.equals(uri.getHost())) return false;
                // Enlaces externos (ARASAAC, licencia): en el navegador del sistema
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (ActivityNotFoundException ignored) {
                }
                return true;
            }

            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (!HOST.equals(uri.getHost())) {
                    // Nada sale a internet: la app funciona igual sin conexión
                    return new WebResourceResponse("text/plain", "utf-8", 403, "Forbidden",
                            Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
                }
                return serveLocal(uri);
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                runOnUiThread(() -> handleWebPermission(request));
            }

            @Override
            public void onPermissionRequestCanceled(PermissionRequest request) {
                if (pendingPermission == request) pendingPermission = null;
            }

            @Override
            public boolean onConsoleMessage(android.webkit.ConsoleMessage m) {
                // Errores de las páginas en el registro del sistema (adb logcat -s RehabVoice)
                Log.i(TAG, "consola " + m.messageLevel() + ": " + m.message() + " (" + m.sourceId() + ":" + m.lineNumber() + ")");
                return true;
            }
        });
    }

    /** Páginas y estáticos de assets/www; la voz de /api/speak/. */
    private WebResourceResponse serveLocal(Uri uri) {
        String path = uri.getPath() == null ? "/" : uri.getPath();
        if (path.startsWith("/api/speak/")) return speak(uri);
        String asset;
        if (path.equals("/") || path.isEmpty()) asset = "www/index.html";
        else if (path.startsWith("/static/")) asset = "www" + path;
        else asset = "www" + path + ".html";          // /practice -> www/practice.html
        if (asset.contains("..")) return notFound();
        InputStream in;
        try {
            in = getAssets().open(asset);
        } catch (IOException missing) {
            Log.w(TAG, "no existe: " + asset);
            return notFound();
        }
        return new WebResourceResponse(mimeType(asset), asset.endsWith(".html") || asset.endsWith(".js")
                || asset.endsWith(".css") || asset.endsWith(".json") ? "utf-8" : null, in);
    }

    private WebResourceResponse speak(Uri uri) {
        String text = Uri.decode(uri.getPath().substring("/api/speak/".length()));
        String speed = uri.getQueryParameter("speed");
        File wav = voice.synthesize(text, speed == null ? "normal" : speed);
        if (wav == null) {
            // Igual que el servidor sin motor de voz: la página usa entonces la del dispositivo
            return new WebResourceResponse("application/json", "utf-8", 503, "Service Unavailable",
                    Collections.emptyMap(), new ByteArrayInputStream("{\"detail\":\"sin voz\"}".getBytes(StandardCharsets.UTF_8)));
        }
        try {
            return new WebResourceResponse("audio/wav", null, 200, "OK",
                    Collections.singletonMap("Cache-Control", "no-store"), new FileInputStream(wav));
        } catch (IOException e) {
            return notFound();
        }
    }

    private static WebResourceResponse notFound() {
        return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found",
                Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
    }

    private static String mimeType(String path) {
        String ext = MimeTypeMap.getFileExtensionFromUrl(path).toLowerCase(Locale.ROOT);
        switch (ext) {
            case "html": return "text/html";
            case "js": return "application/javascript";
            case "css": return "text/css";
            case "json": return "application/json";
            case "svg": return "image/svg+xml";
            case "webp": return "image/webp";
            case "woff2": return "font/woff2";
            case "png": return "image/png";
            default:
                String m = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
                return m != null ? m : "application/octet-stream";
        }
    }

    /** Resultado de Whisper hacia la página (bridge.js -> RehabBridge._transcribed). */
    void deliverTranscription(String id, boolean ok, String text) {
        String js = "window.RehabBridge && RehabBridge._transcribed(" + JSONObject.quote(id) + "," + ok + ","
                + JSONObject.quote(text == null ? "" : text) + ")";
        runOnUiThread(() -> webView.evaluateJavascript(js, null));
    }

    // ------------------------------------------------------------------ micrófono

    private void handleWebPermission(PermissionRequest request) {
        boolean wantsAudio = false;
        for (String r : request.getResources()) {
            if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r)) wantsAudio = true;
        }
        if (!wantsAudio || !HOST.equals(request.getOrigin().getHost())) {
            request.deny();
            return;
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
        } else {
            if (pendingPermission != null) pendingPermission.deny();
            pendingPermission = request;
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQ_MIC || pendingPermission == null) return;
        if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            pendingPermission.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
        } else {
            pendingPermission.deny();
        }
        pendingPermission = null;
    }

    // ------------------------------------------------------------------ copias de seguridad

    void startBackupExport() {
        String name = "rehab-voice-" + new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(new Date()) + ".db";
        Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                .setType("application/octet-stream").putExtra(Intent.EXTRA_TITLE, name);
        startActivityForResult(i, REQ_EXPORT);
    }

    void startBackupImport() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
        startActivityForResult(i, REQ_IMPORT);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        if (requestCode == REQ_EXPORT) exportTo(uri);
        else if (requestCode == REQ_IMPORT) importFrom(uri);
    }

    private void exportTo(Uri uri) {
        synchronized (bridge) {
            try (InputStream in = new FileInputStream(bridge.dbFile());
                 OutputStream out = getContentResolver().openOutputStream(uri)) {
                if (out == null) throw new IOException("sin destino");
                copy(in, out);
                notice("Copia guardada", "Los datos de todos los pacientes se han guardado.");
            } catch (IOException e) {
                Log.e(TAG, "exportar", e);
                notice("No se pudo guardar la copia", String.valueOf(e.getMessage()));
            }
        }
    }

    private void importFrom(Uri uri) {
        File tmp = new File(getCacheDir(), "restore.db");
        try (InputStream in = getContentResolver().openInputStream(uri); OutputStream out = new FileOutputStream(tmp)) {
            if (in == null) throw new IOException("sin archivo");
            copy(in, out);
        } catch (IOException e) {
            notice("No se pudo leer la copia", String.valueOf(e.getMessage()));
            return;
        }
        if (!BackupCheck.looksLikeRehabDb(tmp)) {
            //noinspection ResultOfMethodCallIgnored
            tmp.delete();
            notice("Archivo no válido", "Ese archivo no es una copia de Rehab Voice.");
            return;
        }
        synchronized (bridge) {
            bridge.closeDb();
            File dst = bridge.dbFile();
            File journal = new File(dst.getPath() + "-journal");
            //noinspection ResultOfMethodCallIgnored
            journal.delete();
            if (!tmp.renameTo(dst)) {
                try (InputStream in = new FileInputStream(tmp); OutputStream out = new FileOutputStream(dst)) {
                    copy(in, out);
                } catch (IOException e) {
                    notice("No se pudo restaurar", String.valueOf(e.getMessage()));
                }
            }
            bridge.openDb();
        }
        webView.loadUrl(ORIGIN + "/patients");
        notice("Copia restaurada", "Se han cargado los datos de la copia.");
    }

    private static void copy(InputStream in, OutputStream out) throws IOException {
        byte[] buf = new byte[1 << 16];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
    }

    private void notice(String title, String message) {
        runOnUiThread(() -> new AlertDialog.Builder(this).setTitle(title).setMessage(message)
                .setPositiveButton("Aceptar", null).show());
    }

    // ------------------------------------------------------------------ atrás y ciclo de vida

    private void registerBackHandler() {
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::handleBack);
        }
    }

    @SuppressWarnings("deprecation")
    @Override
    public void onBackPressed() {
        handleBack();
    }

    private void handleBack() {
        if (webView.canGoBack()) {
            webView.goBack();
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle("¿Salir de Rehab Voice?")
                .setPositiveButton("Salir", (d, w) -> finish())
                .setNegativeButton("Cancelar", null)
                .show();
    }

    private void applySystemBarInsets(View root) {
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int left, top, right, bottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(
                        WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                left = bars.left; top = bars.top; right = bars.right; bottom = bars.bottom;
            } else {
                left = insets.getSystemWindowInsetLeft();
                top = insets.getSystemWindowInsetTop();
                right = insets.getSystemWindowInsetRight();
                bottom = insets.getSystemWindowInsetBottom();
            }
            v.setPadding(left, top, right, bottom);
            return insets;
        });
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        webView.saveState(outState);
    }

    @Override
    protected void onResume() {
        super.onResume();
        webView.onResume();
    }

    @Override
    protected void onPause() {
        webView.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (pendingPermission != null) pendingPermission.deny();
        webView.destroy();
        bridge.shutdown();
        voice.close();
        super.onDestroy();
    }
}
