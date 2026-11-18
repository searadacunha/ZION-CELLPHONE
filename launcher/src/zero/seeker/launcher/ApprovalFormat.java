package zero.seeker.launcher;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/** The owner's approvals without Android (no android.* here: launcher/test/ApprovalVectorTest runs it on a Mac).
 *  A request comes from Termux as one JSON object, kept byte for byte in a private folder; an approval signs
 *  "zion-approval-v1\n" + id + "\n" + sha256(request bytes) + "\n" + "approve" + "\n" + signed_at; a denial is unsigned. */
final class ApprovalFormat {
    static final int MAX_BYTES = 4096, MAX_PENDING = 20, MAX_SUMMARY = 200, MAX_DETAIL = 1500, MAX_LIFE = 86400, SKEW = 300;
    static final Pattern ID = Pattern.compile("[0-9A-Za-z_-]{6,64}"), CLASS = Pattern.compile("[0-9A-Za-z_.-]{1,40}");
    // control, format (bidi overrides, zero-width), lone surrogate, private and unassigned characters: they could make
    // what the owner reads differ from what he signs
    static final Pattern HIDDEN = Pattern.compile("\\p{C}");
    static final Set<String> KEYS = new HashSet<>(Arrays.asList("v", "id", "created", "expires", "class", "summary", "detail"));
    static final Object LOCK = new Object();  // the receiver and the approval screen work on the same files

    static final class Req {
        final String raw, id, cls, summary, detail;
        final long created, expires;

        Req(String raw, String id, String cls, String summary, String detail, long created, long expires) {
            this.raw = raw; this.id = id; this.cls = cls; this.summary = summary; this.detail = detail;
            this.created = created; this.expires = expires;
        }
    }

    static IllegalArgumentException bad(String why) { return new IllegalArgumentException(why); }

    /** One flat JSON object with exactly KEYS, strings and integers only, nothing before or after: everything the
     *  signature covers is shown to the owner. Times are checked by fresh(). */
    static Req parse(String raw) {
        if (raw == null || raw.getBytes(StandardCharsets.UTF_8).length > MAX_BYTES) throw bad("missing, or over 4096 bytes");
        Cursor c = new Cursor(raw);
        Map<String, Object> m = new HashMap<>();
        c.ws();
        c.expect('{');
        c.ws();
        if (c.peek() != '}') for (;;) {
            String k = c.string();
            c.ws();
            c.expect(':');
            c.ws();
            if (m.put(k, c.peek() == '"' ? c.string() : (Object) c.integer()) != null) throw bad("key twice: " + k);
            c.ws();
            if (c.peek() != ',') break;
            c.i++;
            c.ws();
        }
        c.expect('}');
        c.ws();
        if (c.i != raw.length()) throw bad("text after the object");
        if (!m.keySet().equals(KEYS)) throw bad("keys must be exactly v, id, created, expires, class, summary, detail");
        Object v = m.get("v"), id = m.get("id"), cr = m.get("created"), ex = m.get("expires"), cl = m.get("class"),
            su = m.get("summary"), de = m.get("detail");
        if (!Long.valueOf(1).equals(v)) throw bad("v must be the integer 1");
        if (!(id instanceof String) || !ID.matcher((String) id).matches()) throw bad("id must match [0-9A-Za-z_-]{6,64}");
        if (!(cr instanceof Long) || !(ex instanceof Long)) throw bad("created and expires must be integers");
        if (!(cl instanceof String) || !CLASS.matcher((String) cl).matches()) throw bad("class must match [0-9A-Za-z_.-]{1,40}");
        if (!(su instanceof String) || !(de instanceof String)) throw bad("summary and detail must be strings");
        String s = (String) su, d = (String) de;
        if (s.trim().isEmpty() || s.codePointCount(0, s.length()) > MAX_SUMMARY || HIDDEN.matcher(s).find())
            throw bad("summary: 1 to 200 characters, no control or invisible character");
        if (d.codePointCount(0, d.length()) > MAX_DETAIL || HIDDEN.matcher(d.replace('\n', ' ').replace('\t', ' ')).find())
            throw bad("detail: 1500 characters at most, no control or invisible character except new line and tab");
        return new Req(raw, (String) id, (String) cl, s, d, (Long) cr, (Long) ex);
    }

    /** A new request: made now (300 s of clock difference allowed), not expired, living one day at most. */
    static void fresh(Req r, long now) {
        if (r.created > now + SKEW) throw bad("created is in the future");
        if (r.expires <= now) throw bad("already expired");
        if (r.expires <= r.created || r.expires > r.created + MAX_LIFE) throw bad("expires must be after created, by 86400 s at most");
    }

    private static final class Cursor {
        final String s;
        int i;

        Cursor(String s) { this.s = s; }

        int peek() { return i < s.length() ? s.charAt(i) : -1; }

        void ws() { while (peek() == ' ' || peek() == '\t' || peek() == '\n' || peek() == '\r') i++; }

        void expect(char ch) {
            if (peek() != ch) throw bad("expected " + ch + " at " + i);
            i++;
        }

        String string() {
            expect('"');
            StringBuilder b = new StringBuilder();
            for (;;) {
                int ch = peek();
                i++;
                if (ch == '"') return b.toString();
                if (ch < 0x20) throw bad("unterminated string, or control character, at " + (i - 1));  // -1: end of text
                if (ch != '\\') {
                    b.append((char) ch);
                    continue;
                }
                int e = peek();
                i++;
                if (e == 'u') {
                    if (i + 4 > s.length() || !s.substring(i, i + 4).matches("[0-9A-Fa-f]{4}")) throw bad("bad \\u escape at " + i);
                    b.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
                    i += 4;
                } else {
                    int k = "\"\\/bfnrt".indexOf(e);
                    if (k < 0) throw bad("bad escape at " + (i - 1));
                    b.append("\"\\/\b\f\n\r\t".charAt(k));
                }
            }
        }

        long integer() {
            int start = i;
            if (peek() == '-') i++;
            int digits = i;
            while (peek() >= '0' && peek() <= '9') i++;
            int n = i - digits;
            if (n == 0 || n > 15 || (n > 1 && s.charAt(digits) == '0')) throw bad("a value must be a string or an integer, at " + start);
            return Long.parseLong(s.substring(start, i));
        }
    }

    static String sha256Hex(byte[] b) {
        try {
            StringBuilder h = new StringBuilder();
            for (byte x : MessageDigest.getInstance("SHA-256").digest(b)) h.append(String.format("%02x", x));
            return h.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    /** What the owner compares once with Termux's enrollment: the first 16 hex digits of sha256(public key DER). */
    static String fingerprint(byte[] spkiDer) {
        String h = sha256Hex(spkiDer);
        return h.substring(0, 4) + " " + h.substring(4, 8) + " " + h.substring(8, 12) + " " + h.substring(12, 16);
    }

    static String payload(String id, String reqSha256, String decision, long signedAt) {
        return "zion-approval-v1\n" + id + "\n" + reqSha256 + "\n" + decision + "\n" + signedAt;
    }

    static String okJson(String id, String reqSha256, long signedAt, String sigB64) {
        return "{\"v\":1,\"id\":" + q(id) + ",\"req_sha256\":" + q(reqSha256) + ",\"decision\":\"approve\",\"signed_at\":"
            + signedAt + ",\"sig\":" + q(sigB64) + "}";
    }

    static String noJson(String id, long t) {
        return "{\"v\":1,\"id\":" + q(id) + ",\"decision\":\"deny\",\"t\":" + t + "}";
    }

    /** A JSON string. */
    static String q(String s) {
        StringBuilder b = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            if (ch == '"' || ch == '\\') b.append('\\').append(ch);
            else if (ch == '\n') b.append("\\n");
            else if (ch < 0x20) b.append(String.format("\\u%04x", (int) ch));
            else b.append(ch);
        }
        return b.append('"').toString();
    }

    static File reqFile(File dir, String id) { return new File(dir, id + ".req"); }

    /** The requests kept in dir, oldest first. One that no longer parses is dropped (only intake() writes there). */
    static List<Req> pending(File dir) {
        List<Req> l = new ArrayList<>();
        File[] fs = dir.listFiles((d, n) -> n.endsWith(".req"));
        for (File f : fs == null ? new File[0] : fs) {
            try {
                l.add(parse(new String(Files.readAllBytes(f.toPath()), StandardCharsets.UTF_8)));
            } catch (IllegalArgumentException e) {
                f.delete();
            } catch (IOException e) {  // kept: a read can fail once without the request being bad
            }
        }
        l.sort(Comparator.comparingLong(r -> r.created));
        return l;
    }

    /** Keeps a new request from Termux, byte for byte (the signature covers their sha256), and returns its id. Expired
     *  ones are dropped first; an id already waiting, or a 21st request, is refused. */
    static String intake(File dir, String raw, long now) throws IOException {
        Req r = parse(raw);
        fresh(r, now);
        synchronized (LOCK) {
            List<Req> l = pending(dir);
            for (Req p : l) if (p.expires <= now) reqFile(dir, p.id).delete();
            l.removeIf(p -> p.expires <= now);
            if (reqFile(dir, r.id).exists()) throw bad("this id is already pending");
            if (l.size() >= MAX_PENDING) throw bad(MAX_PENDING + " requests are already pending");
            if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("cannot create " + dir);
            writeAtomic(reqFile(dir, r.id), raw.getBytes(StandardCharsets.UTF_8));
        }
        return r.id;
    }

    /** Termux withdraws a request. False when it was not pending. */
    static boolean cancel(File dir, String id) {
        if (id == null || !ID.matcher(id).matches()) throw bad("id must match [0-9A-Za-z_-]{6,64}");
        synchronized (LOCK) {
            return reqFile(dir, id).delete();
        }
    }

    interface Signer { byte[] sign(byte[] data) throws Exception; }

    /** The owner approved the request he was shown: signed only if it is still pending with the same bytes and not
     *  expired; then out/<id>.ok is written and the request dropped. Returns null when done, else why nothing was
     *  signed (French, for the owner). */
    static String approve(File dir, File out, Req shown, long now, Signer signer) throws Exception {
        synchronized (LOCK) {
            File f = reqFile(dir, shown.id);
            byte[] raw = f.isFile() ? Files.readAllBytes(f.toPath()) : null;
            if (raw == null || !Arrays.equals(raw, shown.raw.getBytes(StandardCharsets.UTF_8)))
                return "Demande retirée ou changée entre-temps : rien n'est signé.";
            if (now >= shown.expires) return "Demande expirée : rien n'est signé.";
            String sha = sha256Hex(raw);
            String sig = Base64.getEncoder().encodeToString(signer.sign(payload(shown.id, sha, "approve", now).getBytes(StandardCharsets.UTF_8)));
            if (!out.isDirectory() && !out.mkdirs()) throw new IOException("cannot create " + out);
            writeAtomic(new File(out, shown.id + ".ok"), (okJson(shown.id, sha, now, sig) + "\n").getBytes(StandardCharsets.UTF_8));
            f.delete();
            return null;
        }
    }

    /** The owner refused: out/<id>.no, unsigned (a denial is always safe), and the request dropped. */
    static void deny(File dir, File out, String id, long now) throws IOException {
        synchronized (LOCK) {
            if (!out.isDirectory() && !out.mkdirs()) throw new IOException("cannot create " + out);
            writeAtomic(new File(out, id + ".no"), (noJson(id, now) + "\n").getBytes(StandardCharsets.UTF_8));
            reqFile(dir, id).delete();
        }
    }

    /** Readers never see half a file: written beside it, then renamed over it. */
    static void writeAtomic(File f, byte[] data) throws IOException {
        File tmp = new File(f.getPath() + ".tmp");
        try (FileOutputStream o = new FileOutputStream(tmp)) {
            o.write(data);
            o.getFD().sync();
        }
        if (!tmp.renameTo(f)) {
            tmp.delete();
            throw new IOException("cannot rename " + tmp);
        }
    }
}
