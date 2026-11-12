#!/usr/bin/env python3
"""Download APKs from the official F-Droid repo with a verified chain:
entry.jar signed (SHA-256) by the F-Droid key whose fingerprint is published on f-droid.org
 -> sha256 of index-v2.json -> sha256 + signer of each APK.
Picks the newest stable (no release channel) arm64-compatible version.
Usage: PATH=/opt/homebrew/opt/openjdk@17/bin:$PATH python3 -I apk-manager/fdroid_fetch.py <pkg> ...
Output: apk-manager/cache/<pkg>.apk, one line per APK in apk-manager/verified.tsv"""
import hashlib, json, re, subprocess, sys, urllib.request, zipfile
from pathlib import Path

FDROID_CERT_SHA256 = "43238d512c1e5eb2d6569f4a3afbf5523418b82e0a3ed1552770abb9a9c9ccab"  # f-droid.org/docs/Release_Channels_and_Signing_Keys
REPO = "https://f-droid.org/repo"
HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"; CACHE.mkdir(exist_ok=True)
APKSIGNER = "/opt/homebrew/share/android-commandlinetools/build-tools/37.0.0/apksigner"

def fetch(url, dest):
    with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20): f.write(chunk)

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()

def run(*cmd): return subprocess.run(cmd, capture_output=True, text=True)

jar = CACHE / "entry.jar"; fetch(f"{REPO}/entry.jar", jar)
v = run("jarsigner", "-J-Duser.language=en", "-verify", "-verbose", str(jar))
# "with signer errors" = self-signed cert (normal for Android repos); trust comes from the pinned fingerprint below
assert "jar verified" in v.stdout and "Digest algorithm: SHA-256" in v.stdout, v.stdout + v.stderr
fps = {m.replace(":", "").lower() for m in re.findall(r"SHA256: ([0-9A-F:]{95})", run("keytool", "-J-Duser.language=en", "-printcert", "-jarfile", str(jar)).stdout)}
assert fps == {FDROID_CERT_SHA256}, f"entry.jar signed by unexpected key(s): {fps}"
entry = json.loads(zipfile.ZipFile(jar).read("entry.json"))
idx = CACHE / "index-v2.json"
if not idx.exists() or sha256(idx) != entry["index"]["sha256"]:
    fetch(REPO + entry["index"]["name"], idx)
assert sha256(idx) == entry["index"]["sha256"], "index-v2.json hash mismatch"
index = json.load(open(idx))
print(f"F-Droid index OK: entry.jar signed by pinned key, index-v2 sha256 matches, {len(index['packages'])} apps")

with open(HERE / "verified.tsv", "a") as out:
    for pkg in sys.argv[1:]:
        assert pkg in index["packages"], f"{pkg} not in F-Droid main repo"
        vers = [x for x in index["packages"][pkg]["versions"].values()
                if not x.get("releaseChannels") and (not x["manifest"].get("nativecode") or "arm64-v8a" in x["manifest"]["nativecode"])]
        ver = max(vers, key=lambda x: x["manifest"]["versionCode"])
        m, dest = ver["manifest"], CACHE / f"{pkg}.apk"
        fetch(REPO + ver["file"]["name"], dest)
        got = sha256(dest)
        assert got == ver["file"]["sha256"], f"{pkg}: hash mismatch"
        s = run(APKSIGNER, "verify", "--print-certs", str(dest))
        assert s.returncode == 0, f"{pkg}: apksigner: {s.stderr}"
        signer = re.search(r"certificate SHA-256 digest: ([0-9a-f]{64})", s.stdout).group(1)
        assert signer in m["signer"]["sha256"], f"{pkg}: signer {signer} not the one in the index"
        print(f"{pkg} {m['versionName']} ({m['versionCode']}): sha256 + signer OK ({signer[:16]}…)")
        out.write(f"{pkg}\t{m['versionName']}\t{m['versionCode']}\t{got}\t{signer}\t{REPO}{ver['file']['name']}\n")
