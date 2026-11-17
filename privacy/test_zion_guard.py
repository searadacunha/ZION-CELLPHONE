#!/usr/bin/env python3
"""Self-test for privacy/zion-guard. Fake rish answers from a synthetic fixture (made-up packages, no personal data).
  python3 -I privacy/test_zion_guard.py"""
import contextlib, hashlib, importlib.machinery, importlib.util, io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader("zion_guard", str(HERE / "zion-guard"))
spec = importlib.util.spec_from_loader("zion_guard", loader)
g = importlib.util.module_from_spec(spec)
loader.exec_module(g)

FAKE = f"#!{sys.executable}\nimport json, os, sys\nfx = json.load(open(os.environ['ZION_FIX']))\n" \
       "if sys.argv[1:2] == ['-c'] and sys.argv[2] in fx:\n    sys.stdout.write(fx[sys.argv[2]])\nelse:\n    sys.stderr.write('no fixture'); sys.exit(1)\n"


def pkgdump(ver, grants=(), sig="a1b2c3d4"):
    perms = "".join(f"        android.permission.{p}: granted=true, flags=[ USER_SET]\n" for p in ("INTERNET", *grants))
    return (f"Packages:\n  Package [x] (1):\n    versionCode={ver} minSdk=26 targetSdk=36\n"
            f"    signatures=PackageSignatures{{abc version:2, signatures:[{sig}], past signatures:[]}}\n"
            f"    runtime permissions:\n{perms}")


NETSTATS = """Active interfaces:
UID stats:
  ident=[{{type=1, wifiNetworkKey="HomeNet-SECRET"wpa2-psk, metered=false}}] uid=10201 set=DEFAULT tag=0x0
    NetworkStatsHistory: bucketDuration=3600
      st=1794391200 rb={a} rp=1 tb={b} tp=1 op=0
"""
BPF = """  mAppUidStatsMap:
    uid rxBytes rxPackets txBytes txPackets
    10201 {a} 10 {b} 10
    10202 500 1 500 1
  mStatsMapA:
"""


def phone(**over):
    fx = {
        "id -u": "2000\n",
        "cmd package list packages -3 -i -U":
            "package:com.example.notes  installer=com.android.vending uid:10201\n"
            "package:com.example.keys  installer=null uid:10202\n",
        "dumpsys package com.example.notes": pkgdump(7, ["CAMERA"]),
        "dumpsys package com.example.keys": pkgdump(3),
        "cmd appops query-op REQUEST_INSTALL_PACKAGES allow": "No operations.\n",
        "cmd appops query-op SYSTEM_ALERT_WINDOW allow": "No operations.\n",
        "dumpsys device_policy": "  Enabled Device Admins (User 0, provisioningState: 0):\n  \n    mPasswordOwner=-1\n",
        "dumpsys connectivity": "  NetworkAgentInfo{network{101}  ni{WIFI CONNECTED extra: } created=1}\n",
        "cmd package list packages com.solanamobile": "package:com.solanamobile.seedvaultimpl\n",
        "cmd package list packages -d": "package:com.example.old\n",
        "dumpsys package com.solanamobile.seedvaultimpl": pkgdump(12, sig="5eed5eed"),
        "settings get global adb_enabled": "1\n", "settings get global adb_wifi_enabled": "0\n",
        "settings get global adb_allowed_connection_time": "0\n", "settings get global development_settings_enabled": "1\n",
        "settings get global private_dns_mode": "hostname\n", "settings get global private_dns_specifier": "dns.example.net\n",
        "settings get secure accessibility_enabled": "0\n", "settings get secure enabled_accessibility_services": "null\n",
        "settings get secure enabled_notification_listeners": "com.android.launcher3/com.android.launcher3.NL\n",
        "settings get secure default_input_method": "com.example.keys/.IME\n",
        "settings get secure lock_screen_allow_private_notifications": "0\n",
        "settings get secure lock_screen_show_notifications": "1\n",
        "dumpsys netstats detail": NETSTATS.format(a=1000, b=1000),
        "cmd package list packages -U": "package:com.example.notes uid:10201\npackage:com.example.keys uid:10202\n",
    }
    for r in g.ROLES:
        fx[f"cmd role get-role-holders android.app.role.{r}"] = f"com.example.{r.lower()}\n"
    fx.update(over)
    return fx


class Env:
    def __init__(self, tc):
        self.tmp = tempfile.TemporaryDirectory()
        tc.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.fake = d / "rish"
        self.fake.write_text(FAKE)
        self.fake.chmod(0o755)
        self.fix = d / "fx.json"
        os.environ.update(ZION_RISH=str(self.fake), ZION_FIX=str(self.fix), ZION_STATE=str(d / "state"))
        self.dir = d

    def set(self, fx):
        self.fix.write_text(json.dumps(fx))

    def run(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = g.main(list(argv))
        return code, out.getvalue()


class Guard(unittest.TestCase):
    def setUp(self):
        self.e = Env(self)
        self.e.set(phone())

    def base(self):
        self.assertEqual(self.e.run("baseline")[0], 0)

    def test_clean_check_exit0(self):
        self.base()
        code, out = self.e.run("check")
        self.assertEqual(code, 0, out)
        self.assertIn("rien de nouveau", out)
        self.assertIn("hardening.adb-never-expires", out)  # info advice, not drift
        last = json.loads((self.e.dir / "state/guard/last.json").read_text())
        self.assertEqual(last["exit"], 0)
        self.assertNotIn("HomeNet", out)

    def test_baseline_refuses_overwrite(self):
        self.base()
        code, out = self.e.run("baseline")
        self.assertEqual(code, 1)
        self.assertIn("--force", out)
        self.assertEqual(self.e.run("baseline", "--force")[0], 0)

    def test_no_baseline_is_not_ok(self):
        code, out = self.e.run("check")
        self.assertEqual(code, 2)
        self.assertIn("non mesuré", out)

    def test_new_package(self):
        self.base()
        fx = phone()
        fx["cmd package list packages -3 -i -U"] += "package:com.example.newapp installer=null uid:10203\n"
        fx["dumpsys package com.example.newapp"] = pkgdump(1)
        self.e.set(fx)
        code, out = self.e.run("check")
        self.assertEqual(code, 1)
        self.assertIn("pkg.added.com.example.newapp", out)

    def test_new_dangerous_grant(self):
        self.base()
        self.e.set(phone(**{"dumpsys package com.example.keys": pkgdump(3, ["RECORD_AUDIO"])}))
        code, out = self.e.run("check")
        self.assertEqual(code, 1)
        self.assertIn("[haute] perm.new.com.example.keys.RECORD_AUDIO", out)

    def test_installer_change_and_seedvault_signature(self):
        self.base()
        fx = phone(**{"dumpsys package com.solanamobile.seedvaultimpl": pkgdump(12, sig="deadbeef")})
        fx["cmd package list packages -3 -i -U"] = fx["cmd package list packages -3 -i -U"].replace("installer=null", "installer=com.example.store")
        self.e.set(fx)
        code, out = self.e.run("check")
        self.assertEqual(code, 1)
        self.assertIn("pkg.installer.com.example.keys", out)
        self.assertIn("[haute] seedvault.com.solanamobile.seedvaultimpl.sig", out)

    def test_accessibility_with_overlay_is_risky(self):
        self.base()
        self.e.set(phone(**{
            "settings get secure enabled_accessibility_services": "com.example.keys/com.example.keys.A11y\n",
            "settings get secure accessibility_enabled": "1\n",
            "cmd appops query-op SYSTEM_ALERT_WINDOW allow": "Package com.example.keys:\n  SYSTEM_ALERT_WINDOW: allow\n"}))
        code, out = self.e.run("check", "--json")
        self.assertEqual(code, 1)
        ids = {f["id"]: f["severity"] for f in json.loads(out)["findings"]}
        self.assertEqual(ids["risk.a11y-overlay.com.example.keys"], "haute")
        self.assertEqual(ids["a11y.added.com.example.keys/com.example.keys.A11y"], "haute")

    def test_known_risk_in_baseline_is_info(self):
        self.e.set(phone(**{
            "settings get secure enabled_accessibility_services": "com.example.keys/.A\n",
            "cmd appops query-op SYSTEM_ALERT_WINDOW allow": "com.example.keys\n"}))
        self.base()
        code, out = self.e.run("check")
        self.assertEqual(code, 0, out)
        self.assertIn("risque déjà présent", out)

    def test_rish_missing_exit2(self):
        self.base()
        os.environ["ZION_RISH"] = str(self.e.dir / "nope")
        code, out = self.e.run("check")
        self.assertEqual(code, 2)
        self.assertIn("non mesuré", out)
        self.assertNotIn("rien de nouveau", out)

    def test_partial_unmeasured_never_ok(self):
        self.base()
        fx = phone()
        del fx["dumpsys device_policy"]
        self.e.set(fx)
        code, out = self.e.run("check")
        self.assertEqual(code, 2)
        self.assertIn("unmeasured.admins", out)
        self.assertNotIn("Verdict: rien de nouveau", out)

    def test_egress_diff(self):
        self.e.set(phone(**{"dumpsys netstats detail": BPF.format(a=1000, b=1000)}))
        self.assertEqual(self.e.run("egress", "snapshot", "t0")[0], 0)
        self.e.set(phone(**{"dumpsys netstats detail": BPF.format(a=3_001_000, b=1000)}))
        self.e.run("egress", "snapshot", "t1")
        code, out = self.e.run("egress", "diff", "t0", "t1")
        self.assertEqual(code, 0)
        self.assertIn("uid 10201 com.example.notes: +3.00 Mo", out)
        self.assertNotIn("10202", out)
        self.assertIn("10201", self.e.run("egress", "diff", "t0", "t1", "--package", "com.example.notes")[1])
        self.assertIn("Aucune", self.e.run("egress", "diff", "t0", "t1", "--uid", "10202")[1])

    def test_egress_history_fallback_hides_ssid(self):
        self.e.set(phone(**{"dumpsys netstats detail": NETSTATS.format(a=10, b=20)}))
        code, out = self.e.run("egress", "snapshot", "h")
        self.assertEqual(code, 0)
        self.assertIn("history", out)
        self.assertNotIn("HomeNet", (self.e.dir / "state/guard/egress/h.json").read_text())

    def test_script_exit_code_via_subprocess(self):
        env = dict(os.environ, ZION_RISH=str(self.e.dir / "nope"))
        p = subprocess.run([sys.executable, "-I", str(HERE / "zion-guard"), "check"], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)


class Chain(unittest.TestCase):
    def mk(self, n=4):
        self.f = Path(tempfile.mkdtemp()) / "j.jsonl"
        self.addCleanup(lambda: self.f.parent.exists() and __import__("shutil").rmtree(self.f.parent))
        for i in range(n):
            g.chain_append(self.f, {"i": i, "t": "é"})
        return self.f.read_text().splitlines()

    def test_spec_algorithm(self):
        lines = self.mk(2)
        first = json.loads(lines[0])
        self.assertEqual(first["prev"], "0" * 64)
        body = {k: v for k, v in first.items() if k != "hash"}
        want = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        self.assertEqual(first["hash"], want)
        self.assertEqual(json.loads(lines[1])["prev"], want)

    def test_intact(self):
        self.mk()
        ok, msg = g.chain_verify(self.f)
        self.assertTrue(ok)
        self.assertRegex(msg, r"^chaîne intacte: 4 lignes, tête [0-9a-f]{16}$")
        self.assertEqual(g.main(["chain", "verify", str(self.f)]), 0)

    def test_edited_middle(self):
        lines = self.mk()
        lines[1] = lines[1].replace('"i":1', '"i":9')
        self.f.write_text("\n".join(lines) + "\n")
        self.assertEqual(g.chain_verify(self.f)[1].split(":")[0], "ligne 2")
        self.assertEqual(g.main(["chain", "verify", str(self.f)]), 1)

    def test_deleted_line(self):
        lines = self.mk()
        del lines[1]
        self.f.write_text("\n".join(lines) + "\n")
        ok, msg = g.chain_verify(self.f)
        self.assertFalse(ok)
        self.assertTrue(msg.startswith("ligne 2"))

    def test_reordered(self):
        lines = self.mk()
        lines[1], lines[2] = lines[2], lines[1]
        self.f.write_text("\n".join(lines) + "\n")
        ok, msg = g.chain_verify(self.f)
        self.assertFalse(ok)
        self.assertTrue(msg.startswith("ligne 2"))

    def test_garbage_and_blank_line(self):
        lines = self.mk(2)
        self.f.write_text(lines[0] + "\n\n" + lines[1] + "\n")
        self.assertFalse(g.chain_verify(self.f)[0])

    def test_append_continues_chain_and_ignores_forged_fields(self):
        self.mk(2)
        rec = g.chain_append(self.f, {"x": 1, "prev": "evil", "hash": "evil"})
        self.assertNotEqual(rec["prev"], "evil")
        self.assertTrue(g.chain_verify(self.f)[0])


if __name__ == "__main__":
    unittest.main(verbosity=1)
