package zero.seeker.launcher;

import android.app.Activity;
import android.app.KeyguardManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.hardware.biometrics.BiometricManager.Authenticators;
import android.hardware.biometrics.BiometricPrompt;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyPermanentlyInvalidatedException;
import android.security.keystore.KeyProperties;
import android.security.keystore.StrongBoxUnavailableException;
import android.service.notification.StatusBarNotification;
import android.view.View;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.function.Consumer;

/** The owner approves or refuses what ZION asks (ApprovalAsk). An approval is a signature by a key of Android's keystore
 *  that signs only right after the owner's fingerprint or code, asked in Android's own window (BiometricPrompt, a
 *  systemui window OPERATOR never acts on). Not exported, never captured (FLAG_SECURE), not in the recent apps. */
public class Approve extends Activity {
    static final String ALIAS = "zion-approval", CHANNEL = "zion-approvals";
    static final int NOTE = 7401;

    LinearLayout root;
    String said, fp;  // the last outcome, for the owner; the key's fingerprint once read
    boolean busy;     // from "Autoriser" to the end of its signature
    boolean shown;    // resumed: the countdowns tick
    final List<Runnable> ticks = new ArrayList<>();
    final Runnable tick = new Runnable() {
        @Override public void run() {
            for (Runnable t : ticks) t.run();
            if (shown) root.postDelayed(this, 1000);
        }
    };

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);  // before any content: never in a capture
        getWindow().setBackgroundDrawable(new ColorDrawable(Main.BG));
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(Main.BG);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(24), dp(56), dp(24), dp(48));
        sv.addView(root);
        setContentView(sv);
    }

    @Override protected void onResume() {
        super.onResume();
        shown = true;
        render();
    }

    @Override protected void onPause() {
        shown = false;
        root.removeCallbacks(tick);
        super.onPause();
    }

    static long now() { return System.currentTimeMillis() / 1000; }

    static File dir(Context c) { return new File(c.getFilesDir(), "approvals"); }  // the requests: private to this app

    static File out(Context c) { return new File(c.getExternalFilesDir(null), "approvals"); }  // the decisions, for Termux

    /** The requests the owner can still approve. */
    static List<ApprovalFormat.Req> live(Context c) {
        List<ApprovalFormat.Req> l = ApprovalFormat.pending(dir(c));
        long t = now();
        l.removeIf(r -> r.expires <= t);
        return l;
    }

    void render() {
        root.removeCallbacks(tick);
        root.removeAllViews();
        ticks.clear();
        root.addView(text("approbations", Main.FG, 26, true));
        if (said != null) root.addView(text(said, Main.FG, 16, false));
        root.addView(text(Main.RULE, Main.DIM, 20, false));
        List<ApprovalFormat.Req> l = ApprovalFormat.pending(dir(this));
        if (l.isEmpty()) root.addView(text("aucune demande en attente", Main.DIM, 16, false));
        for (ApprovalFormat.Req r : l) {
            root.addView(text("[" + r.cls + "] " + r.summary, Main.FG, 18, true));
            if (!r.detail.isEmpty()) root.addView(text(r.detail, Main.DIM, 16, false));
            TextView when = text("", Main.DIM, 16, false), yes = row("> Autoriser", () -> approve(r));
            root.addView(when);
            root.addView(yes);
            root.addView(row("> Refuser", () -> deny(r)));
            root.addView(text(Main.RULE, Main.DIM, 20, false));
            ticks.add(() -> {
                long s = r.expires - now();
                when.setText(s <= 0 ? "EXPIRÉE : ne peut plus être autorisée" : "expire dans "
                    + (s >= 3600 ? s / 3600 + " h " + s % 3600 / 60 + " min" : s / 60 + " min " + s % 60 + " s"));
                yes.setVisibility(s > 0 ? View.VISIBLE : View.GONE);
            });
        }
        TextView key = text(fp == null ? "clé d'accord : …" : keyLine(fp), Main.DIM, 14, false);
        root.addView(key);
        root.addView(row("< retour", this::finish));
        if (fp == null) new Thread(() -> {  // the first key can take seconds to make
            String f = null, why = null;
            try {
                f = ApprovalFormat.fingerprint(ensureKey(this).getEncoded());
            } catch (Exception e) {
                why = "clé d'accord : " + keyProblem(e);
            }
            String got = f, no = why;
            runOnUiThread(() -> {
                if (got != null) fp = got;
                key.setText(got != null ? keyLine(got) : no);
            });
        }).start();
        tick.run();
    }

    static String keyLine(String fp) {
        return "empreinte de la clé d'accord : " + fp + "\n(à comparer une fois avec celle que Termux affiche à l'enrôlement)";
    }

    void approve(ApprovalFormat.Req r) {
        if (busy) return;
        if (now() >= r.expires) {  // the row lives up to a second longer than the request
            done("Demande expirée : rien n'est signé.");
            return;
        }
        busy = true;
        new Thread(() -> {
            Signature s = null;
            String why = null;
            try {
                s = signer(this);
            } catch (KeyPermanentlyInvalidatedException e) {
                why = renew();
            } catch (Exception e) {
                why = "Clé d'accord indisponible, rien n'est signé : " + keyProblem(e);
            }
            Signature sig = s;
            String no = why;
            runOnUiThread(() -> {
                if (sig == null) {
                    fp = null;  // read again: it may be a new key
                    done(no);
                    return;
                }
                owner(this, "Autoriser l'action de ZION", r.cls, r.summary, new BiometricPrompt.CryptoObject(sig),
                    res -> new Thread(() -> {
                        String m;
                        try {
                            m = ApprovalFormat.approve(dir(this), out(this), r, now(), data -> {
                                Signature x = res.getCryptoObject().getSignature();
                                x.update(data);
                                return x.sign();
                            });
                            if (m == null) {
                                m = "Autorisé et signé : " + r.summary;
                                notifyPending(this, false);
                            }
                        } catch (Exception e) {
                            m = "Échec, rien n'est autorisé : " + e;
                        }
                        String v = m;
                        runOnUiThread(() -> done(v));
                    }).start(),
                    err -> done("Pas d'accord donné : " + err));
            });
        }).start();
    }

    void done(String s) {
        busy = false;
        said = s;
        render();
    }

    void deny(ApprovalFormat.Req r) {
        if (busy) return;
        try {
            ApprovalFormat.deny(dir(this), out(this), r.id, now());
            notifyPending(this, false);
            said = "Refusé : " + r.summary;
        } catch (Exception e) {
            said = "Échec du refus : " + e;
        }
        render();
    }

    String keyProblem(Exception e) {
        return getSystemService(KeyguardManager.class).isDeviceSecure() ? String.valueOf(e)
            : "il faut d'abord un code de verrouillage sur le téléphone (Réglages > Sécurité)";
    }

    /** The keystore invalidated the key (screen lock removed or changed, a fingerprint added): a new one, which Termux
     *  must enroll before its approvals count. */
    String renew() {
        try {
            String f;
            synchronized (ApprovalFormat.LOCK) {
                keyStore().deleteEntry(ALIAS);
                f = ApprovalFormat.fingerprint(ensureKey(this).getEncoded());
            }
            return "Le téléphone a invalidé la clé d'accord (verrouillage ou empreintes changés). Nouvelle clé " + f
                + " : refais l'enrôlement dans Termux, puis autorise à nouveau. Rien n'est signé.";
        } catch (Exception e) {
            return "Clé d'accord invalidée, et pas de nouvelle clé : " + keyProblem(e);
        }
    }

    static KeyStore keyStore() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        return ks;
    }

    /** The approval key, made on first need; its public key (X.509 DER, base64) rewritten to approval.pub each time. */
    static PublicKey ensureKey(Context c) throws Exception {
        synchronized (ApprovalFormat.LOCK) {
            if (keyStore().getCertificate(ALIAS) == null) {
                try {
                    create(true);
                } catch (StrongBoxUnavailableException e) {  // no secure element: the TEE keeps it
                    create(false);
                }
            }
            PublicKey k = keyStore().getCertificate(ALIAS).getPublicKey();
            ApprovalFormat.writeAtomic(new File(c.getExternalFilesDir(null), "approval.pub"),
                (Base64.getEncoder().encodeToString(k.getEncoded()) + "\n").getBytes(StandardCharsets.UTF_8));
            return k;
        }
    }

    static void create(boolean strongBox) throws Exception {
        KeyPairGenerator g = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_RSA, "AndroidKeyStore");
        g.initialize(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setKeySize(2048)
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setSignaturePaddings(KeyProperties.SIGNATURE_PADDING_RSA_PKCS1)
            .setUserAuthenticationRequired(true)
            // 0 s: no window after an unlock, each signature needs its own authentication (a CryptoObject)
            .setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG | KeyProperties.AUTH_DEVICE_CREDENTIAL)
            .setIsStrongBoxBacked(strongBox)
            .build());
        g.generateKeyPair();
    }

    /** A signature with the approval key, which signs once the owner has authenticated for it. */
    static Signature signer(Context c) throws Exception {
        synchronized (ApprovalFormat.LOCK) {
            ensureKey(c);
            Signature s = Signature.getInstance("SHA256withRSA");
            s.initSign((PrivateKey) keyStore().getKey(ALIAS, null));
            return s;
        }
    }

    /** The owner himself, now: a strong biometric or the phone's code, in Android's own window. crypto may be null. */
    static void owner(Activity a, String title, String subtitle, String description, BiometricPrompt.CryptoObject crypto,
                      Consumer<BiometricPrompt.AuthenticationResult> ok, Consumer<String> no) {
        try {
            BiometricPrompt.Builder b = new BiometricPrompt.Builder(a).setTitle(title)
                // with the code allowed, Android forbids a cancel button: back cancels
                .setAllowedAuthenticators(Authenticators.BIOMETRIC_STRONG | Authenticators.DEVICE_CREDENTIAL);
            if (subtitle != null) b.setSubtitle(subtitle);
            if (description != null) b.setDescription(description);
            BiometricPrompt.AuthenticationCallback cb = new BiometricPrompt.AuthenticationCallback() {
                @Override public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult r) { ok.accept(r); }
                @Override public void onAuthenticationError(int code, CharSequence why) { no.accept(String.valueOf(why)); }
            };
            if (crypto == null) b.build().authenticate(new CancellationSignal(), a.getMainExecutor(), cb);
            else b.build().authenticate(crypto, new CancellationSignal(), a.getMainExecutor(), cb);
        } catch (RuntimeException e) {  // a prompt Android refuses to build or show
            no.accept(String.valueOf(e.getMessage()));
        }
    }

    /** One notification while requests wait, with the newest one's summary; none otherwise. alert: a new request
     *  (sound, banner); else only an update of the one already shown. */
    static void notifyPending(Context c, boolean alert) {
        try {
            NotificationManager nm = c.getSystemService(NotificationManager.class);
            List<ApprovalFormat.Req> l = live(c);
            if (l.isEmpty()) {
                nm.cancel(NOTE);
                return;
            }
            boolean shown = false;
            for (StatusBarNotification n : nm.getActiveNotifications()) shown |= n.getId() == NOTE;
            // without POST_NOTIFICATIONS nothing shows: the home menu still counts the requests
            if (!(alert || shown) || !nm.areNotificationsEnabled()) return;
            nm.createNotificationChannel(new NotificationChannel(CHANNEL, "Accords de ZION", NotificationManager.IMPORTANCE_HIGH));
            String s = l.get(l.size() - 1).summary + (l.size() > 1 ? " (" + l.size() + " demandes en attente)" : "");
            nm.notify(NOTE, new Notification.Builder(c, CHANNEL)
                .setSmallIcon(android.R.drawable.stat_sys_warning)
                .setContentTitle("ZION demande ton accord")
                .setContentText(s)
                .setStyle(new Notification.BigTextStyle().bigText(s))
                .setContentIntent(PendingIntent.getActivity(c, 0, new Intent(c, Approve.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                    PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT))
                .setAutoCancel(true)
                .setOnlyAlertOnce(!alert)
                .build());
        } catch (RuntimeException ignored) {  // a notification never blocks a request or a decision
        }
    }

    int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }

    TextView text(String s, int color, float sp, boolean bold) {  // Main's look
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextColor(color);
        t.setTextSize(sp);
        t.setTypeface(Typeface.MONOSPACE, bold ? Typeface.BOLD : Typeface.NORMAL);
        t.setPadding(0, dp(6), 0, dp(6));
        return t;
    }

    TextView row(String s, Runnable r) {
        TextView t = text(s, Main.FG, 20, false);
        t.setPadding(0, dp(12), 0, dp(12));
        t.setOnClickListener(v -> r.run());
        return t;
    }
}
