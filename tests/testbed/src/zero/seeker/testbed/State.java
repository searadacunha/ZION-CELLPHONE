package zero.seeker.testbed;

import android.content.Context;
import android.util.Log;
import android.view.View;
import java.io.File;
import java.io.FileOutputStream;
import org.json.JSONObject;

/** The whole app state, one process-wide copy, mirrored after every change to files/state.json (tmp + rename). */
final class State {
    static String nom = "", quantite = "", ecran = "main";
    static boolean modeTest, accepte, loaded;
    static int valide, selection = -1;

    static File file(Context c) {
        File d = c.getExternalFilesDir(null);
        return new File(d != null ? d : c.getFilesDir(), "state.json");
    }

    static synchronized void load(Context c) {
        if (loaded) return;
        loaded = true;
        try {
            byte[] b = java.nio.file.Files.readAllBytes(file(c).toPath());
            JSONObject o = new JSONObject(new String(b, "UTF-8"));
            nom = o.optString("nom");
            quantite = o.isNull("quantite") ? "" : o.optString("quantite");
            modeTest = o.optBoolean("mode_test");
            accepte = o.optBoolean("accepte");
            valide = o.optInt("valide");
            selection = o.isNull("selection") ? -1 : o.optInt("selection", -1);
        } catch (Exception e) { /* first start: defaults */ }
    }

    static synchronized void reset(Context c) {
        nom = ""; quantite = ""; modeTest = false; accepte = false; valide = 0; selection = -1;
        save(c);
    }

    static synchronized void save(Context c) {
        try {
            JSONObject o = new JSONObject();
            o.put("nom", nom);
            Object q = JSONObject.NULL;
            try { q = Integer.valueOf(Integer.parseInt(quantite.trim())); } catch (NumberFormatException e) { /* empty or not a number */ }
            o.put("quantite", q);
            o.put("mode_test", modeTest);
            o.put("accepte", accepte);
            o.put("valide", valide);
            o.put("selection", selection < 0 ? JSONObject.NULL : (Object) Integer.valueOf(selection));
            o.put("ecran", ecran);
            o.put("t", System.currentTimeMillis());
            File f = file(c), tmp = new File(f.getPath() + ".tmp");
            try (FileOutputStream out = new FileOutputStream(tmp)) { out.write(o.toString().getBytes("UTF-8")); }
            if (!tmp.renameTo(f)) throw new java.io.IOException("rename failed");
            Log.i("ZIONTB", o.toString());
        } catch (Exception e) {
            Log.e("ZIONTB", "save failed: " + e);
        }
    }

    /** Edge-to-edge is forced on targetSdk 35: keep the content out from under the bars. */
    static void insets(View v) {
        v.setOnApplyWindowInsetsListener((x, w) -> {
            x.setPadding(32, w.getSystemWindowInsetTop() + 16, 32, w.getSystemWindowInsetBottom() + 16);
            return w;
        });
    }
}
