package zero.seeker.launcher;

import android.app.Activity;
import android.app.WallpaperManager;
import android.content.Intent;
import android.content.pm.LauncherApps;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.content.pm.ShortcutInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.text.Editable;
import android.text.TextWatcher;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** ZION ZERO home screen: black, monospace, one menu, no feeds. */
public class Main extends Activity {
    static final int FG = 0xFFE6E6E6, DIM = 0xFF808080, BG = 0xFF000000;
    static final String TERMUX = "com.termux";
    static final String RULE = "-----------------------";
    // Termux scripts in ~/.shortcuts (terminal/zion-shell-setup.sh) that this launcher may open
    static final List<String> SCRIPTS = Arrays.asList("terminal", "operator", "dashboard");
    // asked for before its shortcut existed, opened as soon as Termux pins it. Static: Android delivers the pin request
    // with FLAG_ACTIVITY_CLEAR_TASK, so it reaches a new instance of this activity (seen on the phone, 12/11)
    static String pendingScript;

    interface Act { void run(); }
    static final class Item {
        final String label; final Act act, longAct;
        Item(String label, Act act, Act longAct) { this.label = label; this.act = act; this.longAct = longAct; }
    }

    LinearLayout root;
    boolean atHome = true;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(BG);
        sv.setFillViewport(true);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(24), dp(56), dp(24), dp(48)); // targetSdk 35 draws edge to edge: keep clear of the bars
        sv.addView(root);
        getWindow().setBackgroundDrawable(new ColorDrawable(BG)); // never the wallpaper behind the menu
        setContentView(sv);
        showHome();
        if (b == null) {  // a recreated activity (rotation, dark mode, process restored) must not replay an old request
            wallpaperAction(getIntent());
            pinRequest(getIntent());
        }
        getIntent().removeExtra("wallpaper");
    }

    @Override protected void onNewIntent(Intent i) { super.onNewIntent(i); showHome(); wallpaperAction(i); pinRequest(i); } // home button = main menu

    /** From adb: am start -n zero.seeker.launcher/.Main --es wallpaper black|restore */
    void wallpaperAction(Intent i) {
        String w = i == null ? null : i.getStringExtra("wallpaper");
        if ("black".equals(w)) new Thread(this::blackWallpaper).start();
        if ("restore".equals(w)) new Thread(this::restoreWallpaper).start();
    }

    java.io.File backupDir() { return new java.io.File(getExternalFilesDir(null), "wallpaper-backup"); }
    java.io.File blackIds() { return new java.io.File(getExternalFilesDir(null), "black-wallpaper.ids"); }
    static String ids(WallpaperManager wm) {
        return wm.getWallpaperId(WallpaperManager.FLAG_SYSTEM) + " " + wm.getWallpaperId(WallpaperManager.FLAG_LOCK);
    }
    static void deleteTree(java.io.File f) {
        java.io.File[] kids = f.listFiles();
        if (kids != null) for (java.io.File k : kids) deleteTree(k);
        f.delete();
    }

    /** Home and lock screens become plain black. The current images are copied first, and nothing changes if that copy
     *  fails. An existing copy is kept, unless the wallpaper changed since this launcher set black (the ids it then
     *  noted differ): then the new wallpaper is copied instead, so it is never lost. Result in files/wallpaper.log. */
    void blackWallpaper() {
        WallpaperManager wm = WallpaperManager.getInstance(this);
        java.io.File dir = backupDir();
        try {
            boolean stale = dir.isDirectory() && blackIds().isFile()
                && !ids(wm).equals(new String(java.nio.file.Files.readAllBytes(blackIds().toPath())).trim());
            if (!dir.isDirectory() || stale) {
                java.io.File tmp = new java.io.File(dir.getPath() + ".tmp"), old = new java.io.File(dir.getPath() + ".old");
                deleteTree(tmp);
                tmp.mkdirs();
                int saved = 0;
                for (int which : new int[]{WallpaperManager.FLAG_SYSTEM, WallpaperManager.FLAG_LOCK}) {
                    try (android.os.ParcelFileDescriptor pfd = wm.getWallpaperFile(which)) {
                        if (pfd == null) continue;  // no separate lock image: the home image is used for both
                        try (java.io.InputStream in = new java.io.FileInputStream(pfd.getFileDescriptor());
                             java.io.OutputStream out = new java.io.FileOutputStream(new java.io.File(tmp,
                                 which == WallpaperManager.FLAG_SYSTEM ? "system.img" : "lock.img"))) {
                            byte[] buf = new byte[65536];
                            for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
                        }
                        saved++;
                    }
                }
                if (saved == 0) throw new java.io.IOException("no wallpaper file could be read");
                deleteTree(old);
                if (dir.isDirectory() && !dir.renameTo(old)) throw new java.io.IOException("cannot set the old copy aside");
                if (!tmp.renameTo(dir)) { old.renameTo(dir); throw new java.io.IOException("cannot keep the backup"); }
                deleteTree(old);
            }
            android.util.DisplayMetrics m = getResources().getDisplayMetrics();
            Bitmap black = Bitmap.createBitmap(Math.max(m.widthPixels, 1), Math.max(m.heightPixels, 1), Bitmap.Config.ARGB_8888);
            black.eraseColor(BG);
            wm.setBitmap(black, null, true, WallpaperManager.FLAG_SYSTEM | WallpaperManager.FLAG_LOCK);
            java.nio.file.Files.write(blackIds().toPath(), ids(wm).getBytes());
            report("black: done, previous wallpaper kept in " + dir + (stale ? " (new copy: the wallpaper had changed)" : ""));
        } catch (Exception | OutOfMemoryError e) {  // SecurityException included: then the wallpaper is left as it was
            report("black: NOT done, " + e);
        }
    }

    /** Puts back the images saved by blackWallpaper(). Without a copy nothing changes (never wipe what was not saved);
     *  both images are read before anything is set, so a bad copy cannot leave home and lock half restored. */
    void restoreWallpaper() {
        WallpaperManager wm = WallpaperManager.getInstance(this);
        try {
            java.io.File sys = new java.io.File(backupDir(), "system.img"), lock = new java.io.File(backupDir(), "lock.img");
            if (!sys.isFile()) {
                report("restore: no copy, nothing changed");
                return;
            }
            Bitmap s = BitmapFactory.decodeFile(sys.getPath());
            Bitmap l = lock.isFile() ? BitmapFactory.decodeFile(lock.getPath()) : null;
            if (s == null || (lock.isFile() && l == null)) throw new java.io.IOException("unreadable copy in " + backupDir());
            if (l != null) {
                wm.setBitmap(s, null, true, WallpaperManager.FLAG_SYSTEM);
                wm.setBitmap(l, null, true, WallpaperManager.FLAG_LOCK);
            } else {
                wm.setBitmap(s, null, true, WallpaperManager.FLAG_SYSTEM | WallpaperManager.FLAG_LOCK);
            }
            blackIds().delete();  // the wallpaper is no longer our black
            report("restore: done from " + backupDir());
        } catch (Exception | OutOfMemoryError e) {
            report("restore: NOT done, " + e);
        }
    }

    void report(String s) {
        try (java.io.FileWriter f = new java.io.FileWriter(new java.io.File(getExternalFilesDir(null), "wallpaper.log"), true)) {
            f.write(new java.util.Date() + " " + s + "\n");
        } catch (java.io.IOException ignored) { }
        runOnUiThread(() -> toast("wallpaper " + s));
    }
    @SuppressWarnings("deprecation")
    @Override public void onBackPressed() { if (!atHome) showHome(); }

    void showHome() {
        atHome = true;
        menu("ZION ZERO", Arrays.asList(
            new Item("terminal", () -> termuxScript("terminal"), () -> details(TERMUX)),
            new Item("ai", () -> termuxScript("operator"), this::showAiAgent),  // long press: status
            new Item("applications", this::showApps, null),
            new Item("privacy", () -> sub("privacy",
                app("rethinkdns (firewall, dns)", "com.celzero.bravedns"),
                app("pcapdroid (traffic capture)", "com.emanuelef.remote_capture"),
                set("permissions", "android.intent.action.MANAGE_PERMISSIONS"),
                set("privacy dashboard", "android.intent.action.REVIEW_PERMISSION_USAGE"),
                set("network & private dns", Settings.ACTION_WIRELESS_SETTINGS)), null),
            new Item("radio", () -> sub("radio",
                set("internet (wifi + mobile data)", Settings.Panel.ACTION_INTERNET_CONNECTIVITY),
                set("wifi", Settings.ACTION_WIFI_SETTINGS),
                set("bluetooth", Settings.ACTION_BLUETOOTH_SETTINGS),
                set("nfc", Settings.ACTION_NFC_SETTINGS),
                set("airplane mode", Settings.ACTION_AIRPLANE_MODE_SETTINGS)), null),
            new Item("system", () -> sub("system",
                set("settings", Settings.ACTION_SETTINGS),
                set("apps", Settings.ACTION_MANAGE_APPLICATIONS_SETTINGS),
                new Item("ai status (also: long press on ai)", this::showAiAgent, null),
                set("home app (back to the old launcher)", Settings.ACTION_HOME_SETTINGS),
                new Item("wallpaper: black", () -> new Thread(this::blackWallpaper).start(), null),
                new Item("wallpaper: restore previous", () -> new Thread(this::restoreWallpaper).start(), null),
                set("battery", Intent.ACTION_POWER_USAGE_SUMMARY),
                set("storage", Settings.ACTION_INTERNAL_STORAGE_SETTINGS),
                set("developer options", Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS),
                set("about phone", Settings.ACTION_DEVICE_INFO_SETTINGS)), null),
            new Item("seed-vault", () -> sub("seed-vault",
                app("seed vault wallet", "com.solanamobile.wallet"),
                new Item("seed vault", () -> start(new Intent(Intent.ACTION_MAIN)
                    .setClassName("com.solanamobile.seedvaultimpl", "com.solanamobile.seedvaultimpl.MainActivity")), null),
                app("dapp store", "com.solanamobile.dappstore")), null)));
    }

    /** AI AGENT: live status read from llama-server on 127.0.0.1:8080 (OPERATOR's engine, inside Termux). */
    void showAiAgent() {
        sub("ai agent",
            new Item("open operator", () -> termuxScript("operator"), null),
            new Item("dashboard", () -> termuxScript("dashboard"), null),
            new Item("refresh", this::showAiAgent, null));
        TextView st = text("status: checking...", DIM, 16, false);
        root.addView(st, 2);
        new Thread(() -> { String v = agentStatus(); runOnUiThread(() -> st.setText(v)); }).start();
    }

    static String http(String path) throws java.io.IOException {
        java.net.HttpURLConnection c = (java.net.HttpURLConnection) new java.net.URL("http://127.0.0.1:8080" + path).openConnection();
        c.setConnectTimeout(1500);
        c.setReadTimeout(3000);
        try {
            if (c.getResponseCode() != 200) throw new java.io.IOException("HTTP " + c.getResponseCode());
            java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
            try (java.io.InputStream in = c.getInputStream()) {
                byte[] buf = new byte[8192];
                for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
            }
            return out.toString("UTF-8");
        } finally { c.disconnect(); }
    }

    static String agentStatus() {
        try { http("/health"); }
        catch (java.io.IOException e) {
            return e.getMessage() != null && e.getMessage().contains("503") ? "status: LOADING the model" : "status: STOPPED (in Termux: ai --start)";
        }
        StringBuilder b = new StringBuilder("status: ONLINE");
        try {
            org.json.JSONObject p = new org.json.JSONObject(http("/props"));
            if (p.optBoolean("is_sleeping")) b = new StringBuilder("status: SLEEPING (model unloaded, wakes on use)");
            String m = p.optString("model_path", "?");
            b.append("\nmodel: ").append(m.substring(m.lastIndexOf('/') + 1));
            org.json.JSONObject g = p.optJSONObject("default_generation_settings");
            if (g != null) b.append("\ncontext: ").append(g.optInt("n_ctx")).append(" tokens");
        } catch (Exception e) { /* older server: no props */ }
        try {
            for (String l : http("/metrics").split("\n")) {
                String[] f = l.split(" ");
                if (f.length != 2) continue;
                if (f[0].equals("llamacpp:predicted_tokens_seconds")) b.append(String.format("\ngeneration: %.1f tok/s", Double.parseDouble(f[1])));
                if (f[0].equals("llamacpp:prompt_tokens_seconds")) b.append(String.format("\nprompt: %.1f tok/s", Double.parseDouble(f[1])));
            }
        } catch (Exception e) { /* metrics off */ }
        return b.toString();
    }

    void sub(String title, Item... items) {
        atHome = false;
        List<Item> l = new ArrayList<>(Arrays.asList(items));
        l.add(new Item("< back", this::showHome, null));
        menu(title, l);
    }

    void menu(String title, List<Item> items) {
        root.removeAllViews();
        root.addView(text(title, FG, 26, true));
        root.addView(text(RULE, DIM, 20, false));
        for (Item it : items) root.addView(row("> " + it.label, it));
        root.addView(text(RULE, DIM, 20, false));
    }

    void showApps() {
        atHome = false;
        root.removeAllViews();
        root.addView(text("applications", FG, 26, true));
        EditText filter = new EditText(this);
        filter.setTypeface(Typeface.MONOSPACE);
        filter.setTextColor(FG);
        filter.setHintTextColor(DIM);
        filter.setHint("filter");
        filter.setSingleLine(true);
        root.addView(filter);
        LinearLayout rows = new LinearLayout(this);
        rows.setOrientation(LinearLayout.VERTICAL);
        root.addView(rows);

        PackageManager pm = getPackageManager();
        List<ResolveInfo> apps = pm.queryIntentActivities(
            new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0);
        List<String[]> entries = new ArrayList<>(); // {label, package, activity}
        for (ResolveInfo r : apps)
            entries.add(new String[]{r.loadLabel(pm).toString(), r.activityInfo.packageName, r.activityInfo.name});
        entries.sort((x, y) -> x[0].compareToIgnoreCase(y[0]));

        Runnable fill = () -> {
            rows.removeAllViews();
            String q = filter.getText().toString().toLowerCase();
            for (String[] e : entries) {
                if (!q.isEmpty() && !e[0].toLowerCase().contains(q) && !e[1].contains(q)) continue;
                rows.addView(row("> " + e[0], new Item(e[0],
                    () -> start(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER).setClassName(e[1], e[2])),
                    seedVault(e[1]) ? null : () -> details(e[1]))));
            }
            rows.addView(row("< back", new Item("back", this::showHome, null)));
        };
        filter.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int b, int c) {}
            public void onTextChanged(CharSequence s, int a, int b, int c) {}
            public void afterTextChanged(Editable s) { fill.run(); }
        });
        fill.run();
    }

    /** Opens a Termux session running ~/.shortcuts/NAME. Termux from Google Play takes no command from other apps (no
     *  RUN_COMMAND; its RUN alias needs a Termux-only permission): it runs a script only from its own shortcut, which it
     *  pins through the home app, this one, and which the home app may then start. First time: Termux lists its scripts
     *  and the user taps NAME once. */
    void termuxScript(String name) {
        if (getPackageManager().getLaunchIntentForPackage(TERMUX) == null) { toast("Termux is not installed"); return; }
        LauncherApps la = getSystemService(LauncherApps.class);
        try {
            ShortcutInfo s = pinned(la, name);
            if (s != null) { la.startShortcut(s, null, null); return; }
        } catch (RuntimeException e) {  // not the default home app, Termux stopped or updating...
            toast("cannot open " + name + ": " + e.getMessage());
            return;
        }
        pendingScript = name;
        toast("Termux: tap \"" + name + "\" (first time only)");
        start(new Intent(Intent.ACTION_CREATE_SHORTCUT).setClassName(TERMUX, "com.termux.widget.TermuxCreateShortcutActivity"));
    }

    /** Termux names a script's shortcut after the file; its id is the file's path. */
    static boolean isScript(ShortcutInfo s, String name) {
        return TERMUX.equals(s.getPackage())
            && (name.contentEquals(String.valueOf(s.getShortLabel())) || s.getId().endsWith("/.shortcuts/" + name));
    }

    ShortcutInfo pinned(LauncherApps la, String name) {
        LauncherApps.ShortcutQuery q = new LauncherApps.ShortcutQuery().setPackage(TERMUX)
            .setQueryFlags(LauncherApps.ShortcutQuery.FLAG_MATCH_PINNED);
        List<ShortcutInfo> l = la.getShortcuts(q, android.os.Process.myUserHandle());
        if (l != null) for (ShortcutInfo s : l) if (s.isEnabled() && isScript(s, name)) return s;
        return null;
    }

    /** Android asks the home app to confirm a pinned shortcut: accepted only for our Termux scripts, never others. */
    void pinRequest(Intent i) {
        if (i == null || !LauncherApps.ACTION_CONFIRM_PIN_SHORTCUT.equals(i.getAction())) return;
        try {  // the request comes through an exported filter: a malformed one must not crash the home screen
            LauncherApps la = getSystemService(LauncherApps.class);
            LauncherApps.PinItemRequest r = la.getPinItemRequest(i);
            ShortcutInfo s = r == null ? null : r.getShortcutInfo();
            String name = null;
            if (s != null) for (String n : SCRIPTS) if (isScript(s, n)) name = n;
            if (name == null || !r.isValid() || !r.accept()) { toast("ZION ZERO keeps no other shortcuts"); return; }
            if (name.equals(pendingScript)) {
                pendingScript = null;
                la.startShortcut(s, null, null);
            }
        } catch (RuntimeException e) {
            toast("shortcut request ignored: " + e.getMessage());
        }
    }

    Item app(String label, String pkg) { return new Item(label, () -> launch(pkg), seedVault(pkg) ? null : () -> details(pkg)); }
    /** No long press to App info (one tap from Clear storage / Uninstall) for the Seed Vault and Solana packages. */
    static boolean seedVault(String pkg) { return pkg.startsWith("com.solanamobile.") || pkg.startsWith("com.trustkernel."); }
    Item set(String label, String action) { return new Item(label, () -> start(new Intent(action)), null); }

    void launch(String pkg) {
        Intent i = getPackageManager().getLaunchIntentForPackage(pkg);
        if (i == null) toast(pkg + " is not installed or is disabled"); else start(i);
    }
    void details(String pkg) { start(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + pkg))); }
    void start(Intent i) {
        try { startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); }
        catch (RuntimeException e) { toast("cannot open: " + e.getMessage()); }
    }
    void toast(String s) { Toast.makeText(this, s, Toast.LENGTH_LONG).show(); }
    int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }

    TextView text(String s, int color, float sp, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextColor(color);
        t.setTextSize(sp);
        t.setTypeface(Typeface.MONOSPACE, bold ? Typeface.BOLD : Typeface.NORMAL);
        t.setPadding(0, dp(6), 0, dp(6));
        return t;
    }

    TextView row(String s, Item it) {
        TextView t = text(s, FG, 20, false);
        t.setPadding(0, dp(12), 0, dp(12)); // finger-sized rows
        t.setOnClickListener(v -> it.act.run());
        if (it.longAct != null) t.setOnLongClickListener(v -> { it.longAct.run(); return true; });
        return t;
    }
}
