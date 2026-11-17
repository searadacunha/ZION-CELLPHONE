package zero.seeker.launcher;

import android.app.Activity;
import android.app.WallpaperManager;
import android.content.Intent;
import android.content.SharedPreferences;
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
import android.text.InputType;
import android.text.TextWatcher;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** ZION ZERO home screen: black, monospace, one menu, no feeds. */
public class Main extends Activity {
    static final int FG = 0xFFE6E6E6, DIM = 0xFF808080, BG = 0xFF000000;
    static final String TERMUX = "com.termux";
    static final String RULE = "-----------------------";
    // Termux scripts in ~/.shortcuts (terminal/zion-shell-setup.sh) that this launcher may open
    static final List<String> SCRIPTS = Arrays.asList("dashboard", "ai-start", "zion-stop");
    // asked for before its shortcut existed, opened as soon as Termux pins it. Static: Android delivers the pin request
    // with FLAG_ACTIVITY_CLEAR_TASK, so it reaches a new instance of this activity (seen on the phone, 12/11)
    static String pendingScript;

    interface Act { void run(); }
    static final class Item {
        final String label; final Act act, longAct;
        Item(String label, Act act, Act longAct) { this.label = label; this.act = act; this.longAct = longAct; }
    }

    LinearLayout root;
    ScrollView sv;
    boolean atHome = true;
    Runnable resumed;  // what the screen shown refreshes when it comes back to the front (from Termux, say)

    @Override protected void onResume() { super.onResume(); if (resumed != null) resumed.run(); }
    @Override protected void onDestroy() { if (aiShown == this) aiShown = null; super.onDestroy(); }

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        sv = new ScrollView(this);
        sv.setBackgroundColor(BG);
        sv.setFillViewport(true);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(24), dp(56), dp(24), dp(48)); // targetSdk 35 draws edge to edge: keep clear of the bars
        sv.addView(root);
        getWindow().setBackgroundDrawable(new ColorDrawable(BG)); // never the wallpaper behind the menu
        setContentView(sv);
        sv.setOnApplyWindowInsetsListener((v, ins) -> {  // edge to edge (targetSdk 35): room for the keyboard is made here
            int kb = ins.getInsets(android.view.WindowInsets.Type.ime()).bottom;
            if (v.getPaddingBottom() != kb) {
                v.setPadding(0, 0, 0, kb);
                if (aiShown == this) scrollDown();
            }
            return ins;
        });
        showHome();
        if (b == null) {  // a recreated activity (rotation, dark mode, process restored) must not replay an old request
            wallpaperAction(getIntent());
            pinRequest(getIntent());
            aiScreen(getIntent());
        }
        getIntent().removeExtra("wallpaper");
        new Thread(this::writeApps).start();
    }

    @Override protected void onNewIntent(Intent i) {  // home button = main menu
        super.onNewIntent(i);
        showHome();
        wallpaperAction(i);
        pinRequest(i);
        aiScreen(i);
    }

    /** am start -n zero.seeker.launcher/.Main --es screen ai: OPERATOR, after working in other apps for a question of
     *  the ai screen, brings that screen back so its answer is read. Showing a screen is all an outside app gets. */
    void aiScreen(Intent i) { if (i != null && "ai".equals(i.getStringExtra("screen"))) showAi(); }

    /** package<TAB>name of every app that can be opened, for OPERATOR's `ui open "name"`: the shell knows package names,
     *  only an app sees the names people read. In this app's shared files folder, which the shell user may read. */
    void writeApps() {
        try {
            PackageManager pm = getPackageManager();
            StringBuilder b = new StringBuilder();
            for (ResolveInfo r : pm.queryIntentActivities(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0))
                b.append(r.activityInfo.packageName).append('\t').append(r.loadLabel(pm).toString().replaceAll("\\s+", " ").trim()).append('\n');
            java.io.File f = new java.io.File(getExternalFilesDir(null), "apps.tsv"), tmp = new java.io.File(f.getPath() + ".tmp");
            java.nio.file.Files.write(tmp.toPath(), b.toString().getBytes(StandardCharsets.UTF_8));
            tmp.renameTo(f);
        } catch (Exception ignored) { }  // OPERATOR then matches package names only
    }

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
        boolean stopped = stopFile().exists();
        int asks = Approve.live(this).size();
        List<Item> top = new ArrayList<>();
        if (stopped) top.add(new Item("reprendre ZION", this::resumeZion, null));
        if (asks > 0) top.add(new Item("approbations (" + asks + ")", () -> start(new Intent(this, Approve.class)), null));
        top.addAll(Arrays.asList(  // 13/11: "ia c'est réponse humaine, terminal c'est termux"
            new Item("terminal", () -> launch(TERMUX), () -> details(TERMUX)),
            new Item("ai", this::showAi, this::showAiAgent),  // long press: technical status
            new Item("applications", this::showApps, null),
            new Item("android", this::showAndroid, null),
            new Item("cyber lab", this::showLab, null),
            new Item("privacy", this::showPrivacy, null),
            new Item("radio", this::showRadio, null),
            new Item("system", this::showSystem, null),
            new Item("seed-vault", () -> sub("seed-vault",
                app("seed vault wallet", "com.solanamobile.wallet"),
                new Item("seed vault", () -> start(new Intent(Intent.ACTION_MAIN)
                    .setClassName("com.solanamobile.seedvaultimpl", "com.solanamobile.seedvaultimpl.MainActivity")), null),
                app("dapp store", "com.solanamobile.dappstore")), null)));
        menu("ZION ZERO", top);
        root.addView(row("■ STOP ZION", new Item("stop", this::stopZion, null)), 2);  // always first, no question asked
        if (stopped) root.addView(text("ZION ARRÊTÉ", FG, 20, true), 3);
        resumed = this::showHome;  // a request or a stop may have come while away
    }

    java.io.File stopFile() { return new java.io.File(getExternalFilesDir(null), "STOP"); }
    static volatile java.net.HttpURLConnection chatConn;  // the ai screen's answer in progress, if any

    /** The owner's emergency stop, at once: the ai screen may no longer drive apps nor send anything, STOP (epoch
     *  seconds) tells ZION's side, and Termux's own ~/.shortcuts/zion-stop runs (first time: Termux lists its scripts). */
    void stopZion() {
        getSharedPreferences("ai", MODE_PRIVATE).edit().putBoolean("drive", false).apply();
        java.net.HttpURLConnection c = chatConn;  // an answer in progress stops now, not at the next question (review 17/11)
        if (c != null) new Thread(c::disconnect).start();
        try {
            ApprovalFormat.writeAtomic(stopFile(), (Approve.now() + "\n").getBytes(StandardCharsets.UTF_8));
        } catch (java.io.IOException e) {
            toast("STOP non écrit : " + e.getMessage());
        }
        showHome();
        termuxScript("zion-stop");
    }

    /** Only the owner resumes: his fingerprint or code unlocks one signature by the approval key over this stop, left
     *  as RESUME next to STOP. ZION's side lifts its own stop only on that signature, so a STOP file deleted by
     *  anything else resumes nothing (review 17/11). Driving apps stays off. */
    void resumeZion() {
        new Thread(() -> {
            java.security.Signature s = null;
            String why = null;
            try {
                s = Approve.signer(this);
            } catch (Exception e) {
                why = "Clé d'accord indisponible, ZION reste arrêté : " + e.getMessage();
            }
            java.security.Signature sig = s;
            String no = why;
            runOnUiThread(() -> {
                if (sig == null) { toast(no); return; }
                Approve.owner(this, "Reprendre ZION", null, "ZION pourra de nouveau agir. Le pilotage des applis reste coupé.",
                    new android.hardware.biometrics.BiometricPrompt.CryptoObject(sig), r -> new Thread(() -> {
                        String m = null;
                        try {
                            String at = new String(java.nio.file.Files.readAllBytes(stopFile().toPath()), StandardCharsets.UTF_8).replaceAll("[^0-9]", "");
                            String id = "resume-" + at, h = ApprovalFormat.sha256Hex(("zion-resume-v1\n" + id).getBytes(StandardCharsets.UTF_8));
                            long now = Approve.now();
                            java.security.Signature x = r.getCryptoObject().getSignature();
                            x.update(ApprovalFormat.payload(id, h, "approve", now).getBytes(StandardCharsets.UTF_8));
                            String b64 = java.util.Base64.getEncoder().encodeToString(x.sign());
                            ApprovalFormat.writeAtomic(new java.io.File(getExternalFilesDir(null), "RESUME"),
                                ApprovalFormat.okJson(id, h, now, b64).getBytes(StandardCharsets.UTF_8));
                            stopFile().delete();
                        } catch (Exception e) {
                            m = "Reprise non signée, ZION reste arrêté : " + e.getMessage();
                        }
                        String v = m;
                        runOnUiThread(() -> { if (v != null) toast(v); showHome(); });
                    }).start(), this::toast);
            });
        }).start();
    }

    /** ANDROID: the apps, and whether OPERATOR may drive them from the ai screen. That screen cannot ask before each
     *  action as the terminal does, so the answer is given here once, by hand, and sent with each signed question. */
    void showAndroid() {
        SharedPreferences p = getSharedPreferences("ai", MODE_PRIVATE);
        boolean on = p.getBoolean("drive", false);
        sub("android",
            new Item("applications", this::showApps, null),
            new Item("the ai may drive apps: " + (on ? "ON" : "off"), () -> {
                if (on) { p.edit().putBoolean("drive", false).apply(); showAndroid(); }  // off: at once, nothing asked
                else Approve.owner(this, "L'IA pourra piloter les applis", null,  // on: the owner himself, not a tap
                    "Sur l'écran ai, OPERATOR pourra ouvrir les applis, lire leur écran, toucher et écrire.", null,
                    r -> { p.edit().putBoolean("drive", true).apply(); showAndroid(); }, this::toast);
            }, null),
            new Item("automations (operator tasks)", () -> showInfo("tasks", "tasks run by OPERATOR\nin the terminal: seeker-ai --task \"...\""), null),
            set("permissions", "android.intent.action.MANAGE_PERMISSIONS"),
            set("default apps", Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS),
            set("all apps (android settings)", Settings.ACTION_MANAGE_APPLICATIONS_SETTINGS));
        root.addView(text(on ? "ON: on the ai screen, OPERATOR may open apps, read their screen, tap and type to do what you ask."
            + " It never reads or touches the wallet or the Seed Vault, a locked phone, a window that forbids capture, nor"
            + " Android's own questions (permissions, installs, VPN). It types a password only if your question gives it."
            : "off: on the ai screen, OPERATOR answers and reads the phone's status. In the terminal it asks you before"
            + " each screen action.", DIM, 14, false), 2);
    }

    /** CYBER LAB: the tools to look at your own phone and network. */
    void showLab() {
        sub("cyber lab",
            new Item("terminal (termux)", () -> launch(TERMUX), null),
            new Item("dashboard: processes, connections, heat", () -> termuxScript("dashboard"), null),
            app("pcapdroid (traffic capture)", "com.emanuelef.remote_capture"),
            new Item("radio: what is plugged in", this::showRadio, null),
            set("wifi", Settings.ACTION_WIFI_SETTINGS),
            set("developer options", Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS));
        root.addView(text("in the terminal: python, clang, git, nmap, dig, tmux; debian: proot-distro login debian;"
            + " ai: seeker-ai. Test only what is yours.", DIM, 14, false), 2);
    }

    /** PRIVACY: what is cut off, where the names are resolved, who may see what. */
    void showPrivacy() {
        sub("privacy",
            new Item("firewall: apps cut off by OPERATOR", () -> showInfo("firewall", "apps OPERATOR cut off the network\n"
                + "(ask the ai, or in the terminal: privacy/firewall.sh from the Mac). Android forgets these at a restart."), null),
            app("rethinkdns (firewall, dns)", "com.celzero.bravedns"),
            app("pcapdroid (traffic capture)", "com.emanuelef.remote_capture"),
            set("permissions", "android.intent.action.MANAGE_PERMISSIONS"),
            set("privacy dashboard", "android.intent.action.REVIEW_PERMISSION_USAGE"),
            set("network & private dns", Settings.ACTION_WIRELESS_SETTINGS));
        String mode = Settings.Global.getString(getContentResolver(), "private_dns_mode");
        String host = Settings.Global.getString(getContentResolver(), "private_dns_specifier");
        root.addView(text("private dns: " + ("hostname".equals(mode) ? host : mode == null ? "automatic" : mode)
            + "\nGoogle Play services stay on (security updates): this phone is private, not invisible.", DIM, 14, false), 2);
    }

    /** RADIO: what is really there now. An accessory shows only while it is plugged in. */
    void showRadio() {
        sub("radio",
            new Item("refresh", this::showRadio, null),
            set("internet (wifi + mobile data)", Settings.Panel.ACTION_INTERNET_CONNECTIVITY),
            set("wifi", Settings.ACTION_WIFI_SETTINGS),
            set("bluetooth", Settings.ACTION_BLUETOOTH_SETTINGS),
            set("nfc", Settings.ACTION_NFC_SETTINGS),
            set("airplane mode", Settings.ACTION_AIRPLANE_MODE_SETTINGS));
        root.addView(text(radioStatus(), DIM, 16, false), 2);
    }

    String radioStatus() {
        StringBuilder b = new StringBuilder();
        try {
            android.hardware.usb.UsbManager um = getSystemService(android.hardware.usb.UsbManager.class);
            java.util.Map<String, android.hardware.usb.UsbDevice> devs = um == null ? null : um.getDeviceList();
            if (devs == null || devs.isEmpty()) b.append("usb: nothing plugged in");
            else for (android.hardware.usb.UsbDevice d : devs.values())  // what the accessory says of itself
                b.append(String.format("usb: %04x:%04x %s %s\n", d.getVendorId(), d.getProductId(),
                    d.getManufacturerName() == null ? "" : d.getManufacturerName(), d.getProductName() == null ? "" : d.getProductName()));
        } catch (RuntimeException e) { b.append("usb: not readable"); }
        b.append(b.length() > 0 && b.charAt(b.length() - 1) != '\n' ? "\n" : "");
        b.append("bluetooth: ").append(onOff(() -> getSystemService(android.bluetooth.BluetoothManager.class).getAdapter().isEnabled()));
        b.append("\nnfc: ").append(onOff(() -> android.nfc.NfcAdapter.getDefaultAdapter(this).isEnabled()));
        b.append("\nwifi: ").append(onOff(() -> getApplicationContext().getSystemService(android.net.wifi.WifiManager.class).isWifiEnabled()));
        b.append("\nwhat an accessory can do: in the terminal, zion-hw");
        return b.toString();
    }

    interface Ask { boolean yes(); }
    static String onOff(Ask a) {
        try { return a.yes() ? "on" : "off"; }
        catch (RuntimeException e) { return "not on this phone, or not readable"; }  // no such radio, or a permission
    }

    /** SYSTEM: memory, battery, heat, storage, measured now; then Android's own settings. */
    void showSystem() {
        sub("system",
            new Item("refresh", this::showSystem, null),
            new Item("ai status (also: long press on ai)", this::showAiAgent, null),
            set("settings", Settings.ACTION_SETTINGS),
            set("battery", Intent.ACTION_POWER_USAGE_SUMMARY),
            set("storage", Settings.ACTION_INTERNAL_STORAGE_SETTINGS),
            set("home app (back to the old launcher)", Settings.ACTION_HOME_SETTINGS),
            new Item("wallpaper: black", () -> new Thread(this::blackWallpaper).start(), null),
            new Item("wallpaper: restore previous", () -> new Thread(this::restoreWallpaper).start(), null),
            set("developer options", Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS),
            set("about phone", Settings.ACTION_DEVICE_INFO_SETTINGS));
        TextView st = text(systemStatus(null), DIM, 16, false);
        root.addView(st, 2);
        SharedPreferences p = getSharedPreferences("ai", MODE_PRIVATE);
        new Thread(() -> {  // the ai service is asked on the network thread, the rest is already on the screen
            String ai;
            try { String state = aiState(p); ai = state == null ? "not answering as ours" : state; }
            catch (java.net.ConnectException e) { ai = "stopped"; }
            catch (Exception e) { ai = "unknown"; }
            String line = ai;
            runOnUiThread(() -> st.setText(systemStatus(line)));
        }).start();
    }

    String systemStatus(String ai) {
        StringBuilder b = new StringBuilder();
        android.app.ActivityManager.MemoryInfo mi = new android.app.ActivityManager.MemoryInfo();
        getSystemService(android.app.ActivityManager.class).getMemoryInfo(mi);
        b.append(String.format("ram: %.1f of %.1f GB used%s", (mi.totalMem - mi.availMem) / 1e9, mi.totalMem / 1e9, mi.lowMemory ? " (LOW)" : ""));
        Intent bat = registerReceiver(null, new android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        if (bat != null) {
            int plug = bat.getIntExtra(android.os.BatteryManager.EXTRA_PLUGGED, 0);
            b.append(String.format("\nbattery: %d %%, %.1f °C, %s", bat.getIntExtra(android.os.BatteryManager.EXTRA_LEVEL, -1),
                bat.getIntExtra(android.os.BatteryManager.EXTRA_TEMPERATURE, 0) / 10.0, plug == 0 ? "on battery" : "plugged in"));
        }
        String[] heat = {"none", "light", "moderate", "severe", "critical", "emergency", "shutdown"};
        int th = getSystemService(android.os.PowerManager.class).getCurrentThermalStatus();
        b.append("\nheat: ").append(th >= 0 && th < heat.length ? heat[th] : String.valueOf(th));
        b.append(" (cpu temperatures: dashboard)");
        android.os.StatFs fs = new android.os.StatFs(android.os.Environment.getDataDirectory().getPath());
        b.append(String.format("\nstorage: %.0f GB free of %.0f", fs.getAvailableBytes() / 1e9, fs.getTotalBytes() / 1e9));
        b.append(String.format("\ncpu: %d cores, up %d h", Runtime.getRuntime().availableProcessors(), android.os.SystemClock.elapsedRealtime() / 3600000));
        b.append("\nai service: ").append(ai == null ? "…" : ai);
        b.append("\nshizuku: ").append(getPackageManager().getLaunchIntentForPackage("moe.shizuku.privileged.api") == null ? "not installed" : "installed (restart it after a reboot)");
        return b.toString();
    }

    /** One list kept by OPERATOR's service (tasks, memory, tools, history, firewall), asked with a signature and believed
     *  only with the service's proof, like its state. */
    void showInfo(String key, String title) {
        sub(key, new Item("refresh", () -> showInfo(key, title), null), new Item("< ai agent", this::showAiAgent, null));
        TextView t = text(title + "\n…", DIM, 16, false);
        t.setTextIsSelectable(true);
        root.addView(t, 2);
        SharedPreferences p = getSharedPreferences("ai", MODE_PRIVATE);
        new Thread(() -> { String v = info(p, key); runOnUiThread(() -> t.setText(title + "\n\n" + v)); }).start();
    }

    static String info(SharedPreferences p, String key) {
        try {
            String k = p.getString("token", ""), nonce = nonce();
            java.net.HttpURLConnection c = (java.net.HttpURLConnection) new java.net.URL(aiUrl(p) + "/info").openConnection();
            try {
                c.setConnectTimeout(1500);
                c.setReadTimeout(8000);
                c.setRequestProperty("X-Zion-Nonce", nonce);
                c.setRequestProperty("X-Zion-Auth", k.isEmpty() ? "-" : signed(k, "info", nonce, new byte[0]));
                if (c.getResponseCode() != 200 || !proven(c, k, "info-ok", nonce))
                    return "(the ai service did not answer as ours: open ai once, then come back)";
                org.json.JSONArray a = new org.json.JSONObject(read(c.getInputStream())).optJSONArray(key);
                StringBuilder b = new StringBuilder();
                for (int i = 0; a != null && i < a.length(); i++) b.append(a.optString(i)).append("\n");
                return b.length() == 0 ? "(nothing yet)" : b.toString();
            } finally {
                c.disconnect();
            }
        } catch (java.net.ConnectException e) {
            return "(the ai service is stopped: ai > démarrer l'IA)";
        } catch (Exception e) {
            return "(not available: " + e.getClass().getSimpleName() + ")";
        }
    }

    /** AI AGENT: live status read from llama-server on 127.0.0.1:8080 (OPERATOR's engine, inside Termux). */
    void showAiAgent() {
        sub("ai agent",
            new Item("tasks", () -> showInfo("tasks", "tasks run by OPERATOR\nin the terminal: seeker-ai --task \"...\""), null),
            new Item("memory", () -> showInfo("memory", "what OPERATOR was asked to remember"), null),
            new Item("tools", () -> showInfo("tools", "OPERATOR's tools and their permission level\n(auto, ask in the terminal, off)"), null),
            new Item("history", () -> showInfo("history", "last requests and the tools they used"), null),
            new Item("dashboard", () -> termuxScript("dashboard"), null),
            new Item("refresh", this::showAiAgent, null));
        TextView st = text("status: checking...", DIM, 16, false);
        root.addView(st, 2);
        new Thread(() -> { String v = agentStatus(); runOnUiThread(() -> st.setText(v)); }).start();
    }

    static final String LLAMA = "http://127.0.0.1:8080";

    static String http(String url) throws java.io.IOException {
        java.net.HttpURLConnection c = (java.net.HttpURLConnection) new java.net.URL(url).openConnection();
        c.setConnectTimeout(1500);
        c.setReadTimeout(8000);  // the service's /status asks llama-server in turn
        try {
            if (c.getResponseCode() != 200) throw new java.io.IOException("HTTP " + c.getResponseCode());
            return read(c.getInputStream());
        } finally { c.disconnect(); }
    }

    /** A whole reply, 64 KB at most: whatever holds a port could otherwise send without end and fill the memory. */
    static String read(java.io.InputStream in) throws java.io.IOException {
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
        try (java.io.InputStream i = in) {
            byte[] buf = new byte[8192];
            for (int n; (n = i.read(buf)) > 0; ) {
                out.write(buf, 0, n);
                if (out.size() > 65536) throw new java.io.IOException("reply too long");
            }
        }
        return out.toString("UTF-8");
    }

    static String agentStatus() {
        try { http(LLAMA + "/health"); }
        catch (java.io.IOException e) {
            return e.getMessage() != null && e.getMessage().contains("503") ? "status: LOADING the model" : "status: STOPPED (in Termux: ai --start)";
        }
        StringBuilder b = new StringBuilder("status: ONLINE");
        try {
            org.json.JSONObject p = new org.json.JSONObject(http(LLAMA + "/props"));
            if (p.optBoolean("is_sleeping")) b = new StringBuilder("status: SLEEPING (model unloaded, wakes on use)");
            String m = p.optString("model_path", "?");
            b.append("\nmodel: ").append(m.substring(m.lastIndexOf('/') + 1));
            org.json.JSONObject g = p.optJSONObject("default_generation_settings");
            if (g != null) b.append("\ncontext: ").append(g.optInt("n_ctx")).append(" tokens");
        } catch (Exception e) { /* older server: no props */ }
        try {
            for (String l : http(LLAMA + "/metrics").split("\n")) {
                String[] f = l.split(" ");
                if (f.length != 2) continue;
                if (f[0].equals("llamacpp:predicted_tokens_seconds")) b.append(String.format("\ngeneration: %.1f tok/s", Double.parseDouble(f[1])));
                if (f[0].equals("llamacpp:prompt_tokens_seconds")) b.append(String.format("\nprompt: %.1f tok/s", Double.parseDouble(f[1])));
            }
        } catch (Exception e) { /* metrics off */ }
        return b.toString();
    }

    // ---- ai: a conversation with OPERATOR outside Termux (13/11: "ia c'est réponse humaine, terminal c'est termux").
    // `seeker-ai --serve` writes the answers in the background (started by Termux's job scheduler, 127.0.0.1); its key
    // reaches this app through AiToken only. The conversation lives as long as this process. An answer still coming when
    // its screen is left or rebuilt (home, back, rotation) goes on in whichever ai screen is shown next.
    static final List<String[]> chat = new ArrayList<>();  // {"toi" | "IA", text}
    static boolean answering;
    static String[] coming;          // the answer being written, already in chat
    static Main aiShown;             // the activity whose ai screen is on display, else null
    static String aiNote, aiAgain;   // for the next ai screen: a sentence for its status line, a question back in its box
    static final int SENT = 12;      // messages sent with each question: the model's context is short (4096 tokens)
    static final String END = "\u0004", FAIL = "\u0015";  // seeker-ai's END and FAIL
    static final String STOPPED = "L'IA est arrêtée. Touche « démarrer l'IA », puis reviens ici.";
    static final String NOT_OURS = "Ce n'est pas l'IA de ZION ZERO qui répond à sa place (une autre application ?). "
        + "Rien ne lui a été envoyé.";
    TextView comingView, aiStatusView, aiStartView;
    EditText aiInput;

    void showAi() {
        String draft = aiShown == this && aiInput != null ? aiInput.getText().toString() : "";  // what is being typed
        atHome = false;
        root.removeAllViews();
        aiShown = this;
        comingView = null;
        root.addView(text("ai", FG, 26, true));
        TextView status = text("", DIM, 16, false);
        root.addView(status);
        root.addView(text(RULE, DIM, 20, false));
        for (String[] m : chat) {
            TextView t = said(m[0], m[1]);
            root.addView(t);
            if (m == coming) comingView = t;
        }
        EditText in = new EditText(this);
        in.setTypeface(Typeface.MONOSPACE);
        in.setTextColor(FG);
        in.setHintTextColor(DIM);
        in.setHint("écris ici…");
        in.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES | InputType.TYPE_TEXT_FLAG_AUTO_CORRECT);
        in.setHorizontallyScrolling(false);  // a long question wraps, and the keyboard's action key sends it
        in.setMaxLines(5);
        in.setImeOptions(EditorInfo.IME_ACTION_SEND);
        in.setText(aiAgain != null && draft.trim().isEmpty() ? aiAgain : draft);
        aiAgain = null;
        root.addView(in);
        TextView start = row("> démarrer l'IA", new Item("start", () -> termuxScript("ai-start"), null));
        start.setVisibility(View.GONE);
        aiStatusView = status;
        aiStartView = start;
        aiInput = in;
        in.setOnEditorActionListener((v, id, e) -> { send(); return true; });
        root.addView(row("> envoyer", new Item("envoyer", this::send, null)));
        root.addView(start);
        root.addView(row("> nouvelle conversation", new Item("new", () -> {
            if (answering) note("Une réponse arrive encore : attends sa fin.");
            else { chat.clear(); showAi(); }
        }, null)));
        root.addView(row("< back", new Item("back", this::showHome, null)));
        // now, and again once a service started from "démarrer l'IA" has had the time to come up
        resumed = () -> { aiStatus(status, start); sv.postDelayed(() -> aiStatus(status, start), 6000); };
        if (aiNote != null) { note(aiNote); aiNote = null; }
        else if (answering) status.setText("L'IA écrit sa réponse…");
        else resumed.run();
        scrollDown();
    }

    void note(String s) {
        aiStatusView.setText(s);
        aiStartView.setVisibility(STOPPED.equals(s) ? View.VISIBLE : View.GONE);
    }

    void scrollDown() { sv.post(() -> sv.scrollTo(0, root.getHeight())); }  // clamped to the end; focus stays in the box

    TextView said(String who, String what) {
        boolean me = who.equals("toi");
        TextView t = text((me ? "toi : " : "IA : ") + what, me ? DIM : FG, 18, false);
        t.setTextIsSelectable(true);  // a long press copies an answer
        return t;
    }

    void send() {
        if (answering) { note("Une réponse arrive encore : attends sa fin."); return; }
        if (stopFile().exists()) { note("ZION est arrêté : rien n'est envoyé. Reprends-le depuis l'accueil."); return; }
        String q = aiInput.getText().toString().trim();
        if (q.isEmpty()) return;
        String[] asked = {"toi", q}, live = {"IA", "…"};
        chat.add(asked);
        List<String[]> history = new ArrayList<>(chat.subList(Math.max(0, chat.size() - SENT), chat.size()));
        chat.add(live);
        coming = live;
        answering = true;
        aiInput.setText("");
        root.addView(said("toi", q), root.indexOfChild(aiInput));  // added in place: the box keeps the focus and keyboard
        comingView = said("IA", "…");
        root.addView(comingView, root.indexOfChild(aiInput));
        aiStatusView.setText("L'IA écrit sa réponse…");
        scrollDown();
        StringBuilder got = new StringBuilder();  // touched on the UI thread only
        new Thread(() -> {
            String err = ask(history, piece -> runOnUiThread(() -> {
                got.append(piece);
                String w = words(got.toString());
                live[1] = w.isEmpty() ? "…" : w;
                if (aiShown != null && aiShown.comingView != null) {
                    aiShown.comingView.setText("IA : " + live[1]);
                    aiShown.scrollDown();
                }
            }));
            runOnUiThread(() -> answered(asked, live, got.toString(), err));
        }).start();
    }

    /** The model's words in what came so far: without the end mark, nor the service's own sentence after FAIL. */
    static String words(String got) {
        int f = got.indexOf(FAIL);
        return (f >= 0 ? got.substring(0, f) : got).replace(END, "").trim();
    }

    /** The answer is over. Only the model's words enter the conversation sent back to it; the service's sentence, or
     *  the note that the answer was cut (no END: the service stopped, Termux killed...), go to the status line. */
    static void answered(String[] asked, String[] live, String got, String err) {
        answering = false;
        coming = null;
        String w = words(got);
        int f = got.indexOf(FAIL);
        if (f >= 0) err = got.substring(f + 1).replace(END, "").trim();
        else if (err == null && !got.endsWith(END)) err = "La réponse a été coupée : l'IA s'est arrêtée. Réessaie.";
        Main m = aiShown;
        if (w.isEmpty()) {  // nothing answered: the question goes back into the box, to send again
            chat.remove(asked);
            chat.remove(live);
            aiAgain = asked[1];
            aiNote = err != null ? err : "Pas de réponse. Réessaie.";
            if (m != null) m.showAi();
            return;
        }
        live[1] = w;
        if (m == null) { aiNote = err; return; }
        if (m.comingView != null) m.comingView.setText("IA : " + w);
        m.comingView = null;
        if (err != null) m.note(err); else m.aiStatus(m.aiStatusView, m.aiStartView);  // the model is loaded now
    }

    static String aiUrl(SharedPreferences p) { return "http://127.0.0.1:" + p.getInt("port", 8095); }

    /** seeker-ai's signed(): HMAC-SHA256 with the key over "what\nnonce\n" + body, in hex. The key never travels: an app
     *  that took the port while the service was down learns nothing from a question, and cannot sign an answer. */
    static String signed(String key, String what, String nonce, byte[] body) throws java.security.GeneralSecurityException {
        javax.crypto.Mac mac = javax.crypto.Mac.getInstance("HmacSHA256");
        mac.init(new javax.crypto.spec.SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        mac.update((what + "\n" + nonce + "\n").getBytes(StandardCharsets.UTF_8));
        StringBuilder hex = new StringBuilder();
        for (byte x : mac.doFinal(body)) hex.append(String.format("%02x", x));
        return hex.toString();
    }

    static String nonce() {
        byte[] r = new byte[16];
        new java.security.SecureRandom().nextBytes(r);
        StringBuilder hex = new StringBuilder();
        for (byte x : r) hex.append(String.format("%02x", x));
        return hex.toString();
    }

    /** The answer carries the service's own signature over this nonce. */
    static boolean proven(java.net.HttpURLConnection c, String key, String what, String nonce) throws Exception {
        String proof = c.getHeaderField("X-Zion-Proof");
        return !key.isEmpty() && proof != null && java.security.MessageDigest.isEqual(
            proof.getBytes(StandardCharsets.UTF_8), signed(key, what, nonce, new byte[0]).getBytes(StandardCharsets.UTF_8));
    }

    /** The service's state, asked with a signature, believed only with its proof; null when no proof holds. The first
     *  refusal (no key yet, or one from an earlier start) has the service send its current key to AiToken: asked once
     *  more 4 s later. Still null: whatever answers on the port is not the service (or the key cannot reach this app). */
    String aiState(SharedPreferences p) throws Exception {
        for (int attempt = 0; attempt < 2; attempt++) {
            if (attempt > 0) Thread.sleep(4000);
            String key = p.getString("token", ""), nonce = nonce();
            java.net.HttpURLConnection c = (java.net.HttpURLConnection) new java.net.URL(aiUrl(p) + "/status").openConnection();
            try {
                c.setConnectTimeout(1500);
                c.setReadTimeout(8000);  // the service asks llama-server in turn
                c.setRequestProperty("X-Zion-Nonce", nonce);
                c.setRequestProperty("X-Zion-Auth", key.isEmpty() ? "-" : signed(key, "status", nonce, new byte[0]));
                if (c.getResponseCode() == 200 && proven(c, key, "state", nonce))
                    return new org.json.JSONObject(read(c.getInputStream())).optString("state");
            } finally {
                c.disconnect();
            }
        }
        return null;
    }

    /** One question to the service; the answer goes to onText as it comes. Returns null once it is complete, else what to
     *  tell the person. Nothing of the conversation leaves this app before the service has proved it holds the key. */
    String ask(List<String[]> history, java.util.function.Consumer<String> onText) {
        try {
            SharedPreferences p = getSharedPreferences("ai", MODE_PRIVATE);
            String state = aiState(p);
            if (state == null) return NOT_OURS;
            if (state.equals("blocked")) return aiSays(state);
            org.json.JSONArray msgs = new org.json.JSONArray();
            for (String[] m : history)
                msgs.put(new org.json.JSONObject().put("role", m[0].equals("toi") ? "user" : "assistant").put("content", m[1]));
            // "drive": the owner's switch in the android section, inside the signed question (see showAndroid)
            byte[] body = new org.json.JSONObject().put("messages", msgs).put("drive", p.getBoolean("drive", false))
                .toString().getBytes(StandardCharsets.UTF_8);
            String key = p.getString("token", ""), nonce = nonce();
            java.net.HttpURLConnection c = (java.net.HttpURLConnection) new java.net.URL(aiUrl(p) + "/chat").openConnection();
            chatConn = c;  // ■ STOP ZION closes it: the service's next write fails and its answer ends there
            try {
                c.setConnectTimeout(3000);
                c.setReadTimeout(300000);  // a cold start loads the model before the first word; a screen step can take minutes
                c.setDoOutput(true);
                c.setFixedLengthStreamingMode(body.length);
                c.setRequestProperty("Content-Type", "application/json");
                c.setRequestProperty("X-Zion-Nonce", nonce);
                c.setRequestProperty("X-Zion-Auth", signed(key, "chat", nonce, body));
                try (java.io.OutputStream o = c.getOutputStream()) { o.write(body); }
                int code = c.getResponseCode();
                if (code == 401) return "L'IA vient de redémarrer. Renvoie ta question.";  // a new key since the state above
                if (code == 503) return aiSays("busy");
                if (code != 200) return "L'IA n'a pas pu répondre (code " + code + "). Réessaie.";
                if (!proven(c, key, "answer", nonce)) return NOT_OURS;
                try (java.io.Reader r = new java.io.InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8)) {
                    char[] buf = new char[512];
                    for (int n; (n = r.read(buf)) > 0; ) onText.accept(new String(buf, 0, n));
                }
                return null;
            } finally {
                c.disconnect();
                if (chatConn == c) chatConn = null;
            }
        } catch (java.net.ConnectException e) {
            return STOPPED;
        } catch (java.net.SocketTimeoutException e) {
            return "L'IA met trop de temps à répondre. Réessaie.";
        } catch (Exception e) {
            return "La réponse a été coupée (" + e.getClass().getSimpleName() + "). Réessaie.";
        }
    }

    void aiStatus(TextView st, TextView start) {
        SharedPreferences p = getSharedPreferences("ai", MODE_PRIVATE);
        new Thread(() -> {
            String say;
            boolean down = false;
            try {
                String state = aiState(p);
                say = state == null ? NOT_OURS : aiSays(state);
            } catch (java.net.ConnectException e) {
                say = STOPPED;
                down = true;
            } catch (Exception e) {
                say = "État de l'IA inconnu.";
            }
            String s = say;
            boolean d = down;
            runOnUiThread(() -> { st.setText(s); start.setVisibility(d ? View.VISIBLE : View.GONE); });
        }).start();
    }

    static String aiSays(String state) {
        switch (state) {
            case "ready": return "IA prête.";
            case "sleeping": return "IA en veille : ta question la réveille en quelques secondes.";
            case "loading": return "L'IA se réveille…";
            case "stopped": return "IA prête. La première réponse prend environ une demi-minute.";
            case "busy": return "IA occupée par une mesure en cours. Réessaie plus tard.";
            case "blocked": return "Une autre application occupe la place du modèle de l'IA : l'IA refuse de lui parler.";
            default: return "État de l'IA inconnu.";
        }
    }

    void sub(String title, Item... items) {
        atHome = false;
        List<Item> l = new ArrayList<>(Arrays.asList(items));
        l.add(new Item("< back", this::showHome, null));
        menu(title, l);
    }

    void menu(String title, List<Item> items) {
        resumed = null;
        if (aiShown == this) aiShown = null;
        root.removeAllViews();
        root.addView(text(title, FG, 26, true));
        root.addView(text(RULE, DIM, 20, false));
        for (Item it : items) root.addView(row("> " + it.label, it));
        root.addView(text(RULE, DIM, 20, false));
    }

    void showApps() {
        atHome = false;
        resumed = null;
        if (aiShown == this) aiShown = null;
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
