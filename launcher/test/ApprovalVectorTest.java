package zero.seeker.launcher;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.util.Base64;
import java.util.Comparator;

/** ApprovalFormat on a Mac (plain JDK, no Android): request checks, payload, .ok/.no, the pending folder, and the
 *  vectors file the Termux-side verifier is tested with (argument: where to write it). Run: launcher/test/run.sh */
public class ApprovalVectorTest {
    static int checks;
    static final long T = 1795000000L;  // 2026-11-18, the request's "created"

    static void check(boolean ok, String what) {
        checks++;
        if (!ok) throw new AssertionError(what);
    }

    static void refused(String raw, long now, String what) {
        try {
            ApprovalFormat.fresh(ApprovalFormat.parse(raw), now);
        } catch (IllegalArgumentException e) {
            checks++;
            if (Boolean.getBoolean("why")) System.out.println(what + " -> " + e.getMessage());  // java -Dwhy=true
            return;
        }
        throw new AssertionError("accepted: " + what);
    }

    static String req(String id, long created, long expires, String cls, String summary, String detail) {
        return "{\"v\":1,\"id\":" + ApprovalFormat.q(id) + ",\"created\":" + created + ",\"expires\":" + expires + ",\"class\":"
            + ApprovalFormat.q(cls) + ",\"summary\":" + ApprovalFormat.q(summary) + ",\"detail\":" + ApprovalFormat.q(detail) + "}";
    }

    static byte[] sign(KeyPair k, byte[] data) throws Exception {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initSign(k.getPrivate());
        s.update(data);
        return s.sign();
    }

    static boolean verify(KeyPair k, byte[] data, byte[] sig) throws Exception {
        Signature s = Signature.getInstance("SHA256withRSA");
        s.initVerify(k.getPublic());
        s.update(data);
        return s.verify(sig);
    }

    static String read(File f) throws Exception { return new String(Files.readAllBytes(f.toPath()), StandardCharsets.UTF_8); }

    public static void main(String[] args) throws Exception {
        // ---- the request: as Termux sends it, UTF-8 text unescaped, a \n escape in detail
        String sample = "{\"v\":1,\"id\":\"zion-test_0001\",\"created\":" + T + ",\"expires\":" + (T + 3600)
            + ",\"class\":\"system\",\"summary\":\"Désactiver l'appli com.example.app\","
            + "\"detail\":\"OPERATOR veut désactiver com.example.app (pm disable-user).\\nAnnulable : réactiver l'appli.\"}";
        ApprovalFormat.Req r = ApprovalFormat.parse(sample);
        check(r.id.equals("zion-test_0001") && r.cls.equals("system") && r.created == T && r.expires == T + 3600, "fields");
        check(r.summary.equals("Désactiver l'appli com.example.app"), "summary decoded");
        check(r.detail.equals("OPERATOR veut désactiver com.example.app (pm disable-user).\nAnnulable : réactiver l'appli."), "detail escape");
        check(r.raw == sample, "raw kept as given");
        ApprovalFormat.fresh(r, T + 10);
        ApprovalFormat.fresh(ApprovalFormat.parse(" \n{ \"detail\" : \"\", \"summary\":\"\\u00e9t\\u00e9 \\ud83d\\ude00\",\"class\":\"a\",\"expires\":"
            + (T + 1) + ",\"created\":" + T + ",\"id\":\"abcdef\",\"v\":1 }\r\n"), T);  // order, spaces, escapes, a pair
        String emoji = "\ud83d\ude00".repeat(200), euro = "€".repeat(1500);
        String longest = req("abcdef", T, T + 60, "c", emoji, "é\n\t" + "é".repeat(1497));  // 200 and 1500 characters
        check(longest.getBytes(StandardCharsets.UTF_8).length <= 4096 && ApprovalFormat.parse(longest).detail.length() == 1500,
            "longest summary and detail");
        checks += 2;

        // ---- refused: not one flat object of exactly these keys, types and lengths
        String ok = req("abcdef", T, T + 60, "system", "s", "d");
        refused(null, T, "null");
        refused("", T, "empty");
        refused(ok + "x", T, "text after");
        refused(ok + "{}", T, "two objects");
        refused("\ufeff" + ok, T, "byte order mark");
        refused(ok.replace("{\"v\":1,", "{\"v\":1,\"v\":1,"), T, "key twice");
        refused(ok.replace("\"detail\":\"d\"", "\"detail\":\"d\",\"extra\":\"x\""), T, "unknown key");
        refused(ok.replace(",\"detail\":\"d\"", ""), T, "missing key");
        refused(ok.replace("\"v\":1", "\"v\":2"), T, "v 2");
        refused(ok.replace("\"v\":1", "\"v\":\"1\""), T, "v as a string");
        refused(ok.replace("\"v\":1", "\"v\":1.0"), T, "v as a float");
        refused(ok.replace("\"v\":1", "\"v\":true"), T, "v true");
        refused(ok.replace("\"v\":1", "\"v\":01"), T, "leading zero");
        refused(ok.replace("\"created\":" + T, "\"created\":\"" + T + "\""), T, "created as a string");
        refused(ok.replace("\"expires\":" + (T + 60), "\"expires\":1.79500006e9"), T, "exponent");
        refused(ok.replace("\"expires\":" + (T + 60), "\"expires\":1234567890123456"), T, "16 digits");
        refused(ok.replace("\"expires\":" + (T + 60), "\"expires\":null"), T, "null");
        refused(ok.replace("\"detail\":\"d\"", "\"detail\":[\"d\"]"), T, "array");
        refused(ok.replace("\"detail\":\"d\"", "\"detail\":{}"), T, "object");
        refused(ok.replace("\"", "'"), T, "single quotes");
        refused(ok.replace("\"v\":", "v:"), T, "bare key");
        refused(ok.replace("}", ",}"), T, "trailing comma");
        refused(ok.replace("{", "{/* */"), T, "comment");
        refused(req("abc", T, T + 60, "system", "s", "d"), T, "id too short");
        refused(req("x".repeat(65), T, T + 60, "system", "s", "d"), T, "id too long");
        refused(req("../../x", T, T + 60, "system", "s", "d"), T, "id with a path");
        refused(req("abcdef.ok", T, T + 60, "system", "s", "d"), T, "id with a dot");
        refused(req("abcdef", T, T + 60, "", "s", "d"), T, "empty class");
        refused(req("abcdef", T, T + 60, "a b", "s", "d"), T, "class with a space");
        refused(req("abcdef", T, T + 60, "system", "", "d"), T, "empty summary");
        refused(req("abcdef", T, T + 60, "system", "   ", "d"), T, "blank summary");
        refused(req("abcdef", T, T + 60, "system", emoji + "a", "d"), T, "summary 201");
        refused(req("abcdef", T, T + 60, "system", "a\nb", "d"), T, "new line in summary");
        refused(req("abcdef", T, T + 60, "system", "fichier \u202egpj.exe", "d"), T, "bidi override in summary");
        refused(req("abcdef", T, T + 60, "system", "a\u200bb", "d"), T, "zero-width space in summary");
        refused(req("abcdef", T, T + 60, "system", "s", "d\u2066x\u2069"), T, "bidi isolate in detail");
        refused(req("abcdef", T, T + 60, "system", "s", "a\rb"), T, "carriage return in detail");
        refused(ok.replace("\"summary\":\"s\"", "\"summary\":\"\\ud800\""), T, "lone surrogate escape");
        refused(ok.replace("\"summary\":\"s\"", "\"summary\":\"\ud800\""), T, "lone surrogate");
        refused(ok.replace("\"summary\":\"s\"", "\"summary\":\"a\\x\""), T, "bad escape");
        refused(ok.replace("\"summary\":\"s\"", "\"summary\":\"a\\u12\""), T, "short \\u escape");
        refused(ok.replace("\"summary\":\"s\"", "\"summary\":\"a\tb\""), T, "raw tab in a string");
        refused(ok.replace("\"detail\":\"d\"}", "\"detail\":\"d"), T, "unterminated");
        refused(req("abcdef", T, T + 60, "system", "s", "é".repeat(1501)), T, "detail 1501 (3 KB)");
        refused(req("abcdef", T, T + 60, "system", "s", euro), T, "1500 characters but 4500 bytes");
        // ---- refused: times
        refused(ok, T + 60, "expired: expires == now");
        refused(ok, T + 61, "expired");
        refused(req("abcdef", T + 301, T + 400, "system", "s", "d"), T, "created in the future");
        ApprovalFormat.fresh(ApprovalFormat.parse(req("abcdef", T + 300, T + 400, "system", "s", "d")), T);  // 300 s of skew
        refused(req("abcdef", T, T + 86401, "system", "s", "d"), T, "lives more than a day");
        ApprovalFormat.fresh(ApprovalFormat.parse(req("abcdef", T, T + 86400, "system", "s", "d")), T);
        refused(req("abcdef", T + 100, T + 50, "system", "s", "d"), T, "expires before created");
        checks += 2;

        // ---- formats
        check(ApprovalFormat.sha256Hex("abc".getBytes(StandardCharsets.UTF_8))
            .equals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"), "sha256 hex");
        check(ApprovalFormat.payload("abcdef", "00ff", "approve", 42).equals("zion-approval-v1\nabcdef\n00ff\napprove\n42"), "payload");
        check(ApprovalFormat.okJson("abcdef", "00ff", 42, "c2ln+/=").equals(
            "{\"v\":1,\"id\":\"abcdef\",\"req_sha256\":\"00ff\",\"decision\":\"approve\",\"signed_at\":42,\"sig\":\"c2ln+/=\"}"), "ok json");
        check(ApprovalFormat.noJson("abcdef", 42).equals("{\"v\":1,\"id\":\"abcdef\",\"decision\":\"deny\",\"t\":42}"), "no json");
        check(ApprovalFormat.q("a\"b\\c\nd\u0001é").equals("\"a\\\"b\\\\c\\nd\\u0001é\""), "json string");
        check(ApprovalFormat.fingerprint(new byte[0]).equals("e3b0 c442 98fc 1c14"), "fingerprint of sha256('')");

        // ---- the pending folder (the launcher's private files/approvals) and the decisions (shared files/approvals)
        File tmp = Files.createTempDirectory("zion-approval").toFile(), dir = new File(tmp, "private"), out = new File(tmp, "shared");
        try {
            check(ApprovalFormat.intake(dir, sample, T + 10).equals("zion-test_0001"), "intake");
            check(read(new File(dir, "zion-test_0001.req")).equals(sample), "request kept byte for byte");
            refused2(() -> ApprovalFormat.intake(dir, sample, T + 11), "same id twice");
            for (int i = 1; i < ApprovalFormat.MAX_PENDING; i++)
                ApprovalFormat.intake(dir, req(String.format("fill-%02d", i), T + i, T + 600, "c", "s" + i, ""), T + 20);
            check(ApprovalFormat.pending(dir).size() == 20, "20 pending");
            refused2(() -> ApprovalFormat.intake(dir, req("one-more", T, T + 600, "c", "s", ""), T + 20), "21st");
            check(ApprovalFormat.pending(dir).get(0).id.equals("zion-test_0001"), "oldest first");
            check(ApprovalFormat.cancel(dir, "fill-01") && !ApprovalFormat.cancel(dir, "fill-01"), "cancel once");
            refused2(() -> ApprovalFormat.cancel(dir, "../private/x"), "cancel of a path");
            check(ApprovalFormat.intake(dir, req("one-more", T, T + 600, "c", "s", ""), T + 20).equals("one-more"), "room again");
            check(ApprovalFormat.intake(dir, req("later-1", T + 700, T + 900, "c", "s", ""), T + 700).equals("later-1")
                && ApprovalFormat.pending(dir).size() == 2, "expired ones dropped at intake: sample (T+3600) and later stay");
            Files.write(new File(dir, "broken.req").toPath(), "{\"v\":1}".getBytes(StandardCharsets.UTF_8));
            check(ApprovalFormat.pending(dir).size() == 2 && !new File(dir, "broken.req").exists(), "unreadable request dropped");

            KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
            g.initialize(2048);
            KeyPair key = g.genKeyPair();
            ApprovalFormat.Req shown = ApprovalFormat.pending(dir).get(0);
            // refusals first: nothing is signed, nothing written, the request stays
            check(ApprovalFormat.approve(dir, out, ApprovalFormat.parse(sample.replace("app\"", "app2\"")), T + 30, d -> sign(key, d)) != null,
                "changed bytes refused");
            check(ApprovalFormat.approve(dir, out, shown, T + 3600, d -> sign(key, d)) != null, "expired refused");
            try {
                ApprovalFormat.approve(dir, out, shown, T + 30, d -> { throw new java.security.SignatureException("keystore says no"); });
                throw new AssertionError("signer failure hidden");
            } catch (java.security.SignatureException e) {
                checks++;
            }
            check(!new File(out, "zion-test_0001.ok").exists() && new File(dir, "zion-test_0001.req").exists(), "nothing written");
            // the approval
            long signedAt = T + 30;
            check(ApprovalFormat.approve(dir, out, shown, signedAt, d -> sign(key, d)) == null, "approved");
            String sha = ApprovalFormat.sha256Hex(sample.getBytes(StandardCharsets.UTF_8));
            String payload = "zion-approval-v1\nzion-test_0001\n" + sha + "\napprove\n" + signedAt;
            String sig = Base64.getEncoder().encodeToString(sign(key, payload.getBytes(StandardCharsets.UTF_8)));
            String okFile = read(new File(out, "zion-test_0001.ok"));
            check(okFile.equals(ApprovalFormat.okJson("zion-test_0001", sha, signedAt, sig) + "\n"), "ok file");
            check(verify(key, payload.getBytes(StandardCharsets.UTF_8), Base64.getDecoder().decode(sig)), "signature verifies");
            check(!new File(dir, "zion-test_0001.req").exists(), "request dropped");
            check(ApprovalFormat.approve(dir, out, shown, signedAt, d -> sign(key, d)) != null, "no second signature");
            ApprovalFormat.deny(dir, out, "later-1", T + 40);
            check(read(new File(out, "later-1.no")).equals("{\"v\":1,\"id\":\"later-1\",\"decision\":\"deny\",\"t\":" + (T + 40) + "}\n")
                && !new File(dir, "later-1.req").exists(), "denial");
            File[] left = out.listFiles((d, n) -> n.endsWith(".tmp"));
            check(left != null && left.length == 0, "no temporary file left");

            // ---- the vectors: this approval, and a signature presented for another request
            String other = sample.replace("com.example.app", "com.example.evil");
            String shaOther = ApprovalFormat.sha256Hex(other.getBytes(StandardCharsets.UTF_8));
            String payloadOther = ApprovalFormat.payload("zion-test_0001", shaOther, "approve", signedAt);
            check(!verify(key, payloadOther.getBytes(StandardCharsets.UTF_8), Base64.getDecoder().decode(sig)), "negative fails");
            byte[] spki = key.getPublic().getEncoded();
            String json = "{\n"
                + "  \"about\": " + ApprovalFormat.q("launcher/test/ApprovalVectorTest.java: a software RSA-2048 key stands for the phone's"
                + " AndroidKeyStore key. sig = RSASSA-PKCS1-v1_5 SHA-256 over the UTF-8 bytes of payload; req_sha256 = sha256 of the"
                + " UTF-8 bytes of req; spki_b64 = what approval.pub holds; ok_json = the exact .ok file") + ",\n"
                + "  \"spki_b64\": " + ApprovalFormat.q(Base64.getEncoder().encodeToString(spki)) + ",\n"
                + "  \"fingerprint\": " + ApprovalFormat.q(ApprovalFormat.fingerprint(spki)) + ",\n"
                + "  \"req\": " + ApprovalFormat.q(sample) + ",\n"
                + "  \"req_sha256\": " + ApprovalFormat.q(sha) + ",\n"
                + "  \"signed_at\": " + signedAt + ",\n"
                + "  \"payload\": " + ApprovalFormat.q(payload) + ",\n"
                + "  \"sig_b64\": " + ApprovalFormat.q(sig) + ",\n"
                + "  \"ok_json\": " + ApprovalFormat.q(okFile) + ",\n"
                + "  \"negative\": {\n"
                + "    \"why\": \"the signature of req above, presented for another request (other summary): must be rejected\",\n"
                + "    \"req\": " + ApprovalFormat.q(other) + ",\n"
                + "    \"req_sha256\": " + ApprovalFormat.q(shaOther) + ",\n"
                + "    \"payload\": " + ApprovalFormat.q(payloadOther) + ",\n"
                + "    \"sig_b64\": " + ApprovalFormat.q(sig) + ",\n"
                + "    \"ok_json\": " + ApprovalFormat.q(ApprovalFormat.okJson("zion-test_0001", shaOther, signedAt, sig) + "\n") + ",\n"
                + "    \"expect\": \"reject\"\n"
                + "  }\n"
                + "}\n";
            if (args.length > 0) Files.write(new File(args[0]).toPath(), json.getBytes(StandardCharsets.UTF_8));
        } finally {
            Files.walk(tmp.toPath()).sorted(Comparator.reverseOrder()).forEach(p -> p.toFile().delete());
        }
        System.out.println("ApprovalVectorTest: " + checks + " checks OK" + (args.length > 0 ? ", vectors in " + args[0] : ""));
    }

    interface Call { Object run() throws Exception; }

    static void refused2(Call c, String what) throws Exception {
        try {
            c.run();
        } catch (IllegalArgumentException e) {
            checks++;
            return;
        }
        throw new AssertionError("accepted: " + what);
    }
}
