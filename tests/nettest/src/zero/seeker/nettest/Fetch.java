package zero.seeker.nettest;

import android.app.Activity;
import android.os.Bundle;

/** am start -n zero.seeker.nettest/.Fetch --es url URL --es id N: one GET, its outcome appended to result.txt in this
 *  app's shared files folder (the shell user reads it): "N<TAB>HTTP 200, 1256 bytes" or "N<TAB>FAILED: why". */
public class Fetch extends Activity {
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        final String url = getIntent().getStringExtra("url"), id = getIntent().getStringExtra("id");
        final java.io.File out = new java.io.File(getExternalFilesDir(null), "result.txt");
        new Thread(() -> {
            String got;
            try {
                java.net.HttpURLConnection c = (java.net.HttpURLConnection) new java.net.URL(url).openConnection();
                c.setConnectTimeout(8000);
                c.setReadTimeout(8000);
                c.setUseCaches(false);
                int code = c.getResponseCode(), n = 0;
                try (java.io.InputStream in = code < 400 ? c.getInputStream() : c.getErrorStream()) {
                    byte[] buf = new byte[8192];
                    for (int r; in != null && (r = in.read(buf)) > 0; ) n += r;
                }
                got = "HTTP " + code + ", " + n + " bytes";
            } catch (Exception e) {
                got = "FAILED: " + e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()).replace('\n', ' ');
            }
            try (java.io.FileWriter f = new java.io.FileWriter(out, true)) {
                f.write(id + "\t" + got + "\n");
            } catch (java.io.IOException ignored) { }
        }).start();
        finish();
    }
}
