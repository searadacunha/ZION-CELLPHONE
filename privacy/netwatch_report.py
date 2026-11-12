#!/usr/bin/env python3
"""Aggregate netwatch.sh samples: who (package) talks to whom (IP, reverse DNS, port), how many bytes each app moved
during the window (dumpsys netstats before/after), who listens, and the same grouped by vendor (Google, Solana Mobile,
MediaTek, Android system, other apps).
  python3 -I privacy/netwatch_report.py privacy/<run>                  REPORT.md + summary.json in the run folder
  python3 -I privacy/netwatch_report.py --compare privacy/<A> privacy/<B>   B against A: bytes, connections, new talkers
  python3 -I privacy/netwatch_report.py --selftest"""
import collections, ipaddress, json, re, socket, sys
from pathlib import Path

SYSTEM_UIDS = {0: "root", 1000: "system", 1001: "radio", 1051: "netd", 1052: "dns", 1073: "networkstack", 1010: "wifi"}
GOOGLE_HOSTS = re.compile(r"(1e100\.net|google(apis|usercontent|video|syndication|adservices)?\.com|gstatic\.com|gvt\d\.com|"
                          r"googlezip\.net|doubleclick\.net|app-measurement\.com|youtube\.com|ggpht\.com)$")


def vendor(pkgs, uid):
    p = ",".join(pkgs)
    if uid < 10000:
        return "android-system"
    if re.search(r"com\.google\.|com\.android\.vending", p):
        return "google"
    if "com.solanamobile." in p:
        return "solana-mobile"
    if re.search(r"com\.mediatek\.|^vendor\.", p):
        return "mediatek"
    if "com.termux" in p:
        return "termux"
    return "other-apps"


def load_uids(run):
    uids = collections.defaultdict(list)
    for line in (run / "uids.txt").read_text().splitlines():
        uid, pkg = line.split(" ", 1)
        uids[int(uid.split(",")[0])].append(pkg)
    return uids


def owner(uids, uid):
    if uid in uids:
        return ",".join(uids[uid][:3]) + ("…" if len(uids[uid]) > 3 else "")
    return SYSTEM_UIDS.get(uid, f"uid{uid}")


def addr(hexaddr):
    ip, port = hexaddr.split(":")
    b = bytes.fromhex(ip)
    if len(b) == 4:
        a = ipaddress.IPv4Address(b[::-1])
    else:  # /proc stores IPv6 as four little-endian 32-bit words
        a = ipaddress.IPv6Address(b"".join(b[i:i + 4][::-1] for i in range(0, 16, 4)))
        a = a.ipv4_mapped or a
    return a, int(port, 16)


def netstats_bytes(text):
    """uid -> rx+tx bytes summed over every bucket of its untagged (tag=0x0) histories, all networks and sets."""
    total, uid = collections.Counter(), None
    for line in text.splitlines():
        m = re.search(r"\buid=(-?\d+) set=\w+ tag=0x0\b", line)
        if m:
            uid = int(m.group(1))
            continue
        if "ident=" in line or not line.startswith("      st="):
            if "ident=" in line:
                uid = None
            continue
        if uid is not None:
            b = re.search(r"rb=(\d+) rp=\d+ tb=(\d+)", line)
            if b:
                total[uid] += int(b.group(1)) + int(b.group(2))
    return total


def bpf_bytes(text):
    """uid -> rx+tx bytes from the live eBPF counters (mAppUidStatsMap, cumulative since boot, exact, no polling)."""
    out, on = collections.Counter(), False
    for line in text.splitlines():
        if line.strip() == "uid rxBytes rxPackets txBytes txPackets":
            on = True
            continue
        if on:
            f = line.split()
            if len(f) != 5 or not all(x.lstrip("-").isdigit() for x in f):
                break
            out[int(f[0])] += int(f[1]) + int(f[3])
    return out


def analyse(run, resolve=True):
    uids = load_uids(run)
    conns, listens = collections.Counter(), set()
    for line in (run / "raw.txt").read_text().splitlines():
        f = line.split()
        if len(f) < 9 or not f[1].endswith(":"):
            continue
        proto, local, remote, st, uid = f[0], f[2], f[3], f[4], int(f[8])
        (la, lp), (ra, rp) = addr(local), addr(remote)
        if ra.is_unspecified:
            if st == "0A" or proto.startswith("udp"):
                listens.add((owner(uids, uid), proto, str(la), lp))
            continue
        if ra.is_loopback:
            continue
        conns[(uid, str(ra), rp, proto)] += 1
    texts = [(run / n).read_text() if (run / n).exists() else "" for n in ("netstats_before.txt", "netstats_after.txt")]
    before, after = (bpf_bytes(t) for t in texts)
    source = "eBPF counters (exact)"
    if not after:  # older Android, or the section is missing: the 2-hour history buckets (only as fresh as the last poll)
        before, after, source = (*(netstats_bytes(t) for t in texts), "netstats history (approximate)")
    moved = {u: after[u] - before.get(u, 0) for u in after if after[u] - before.get(u, 0) > 0}
    names = {}

    def rdns(ip):
        if not resolve:
            return "-"
        if ip not in names:
            try:
                names[ip] = socket.gethostbyaddr(ip)[0]
            except OSError:
                names[ip] = "-"
        return names[ip]

    talk = [{"uid": u, "owner": owner(uids, u), "vendor": vendor(uids.get(u, []), u), "ip": ip, "rdns": rdns(ip), "port": port,
             "proto": proto, "samples": n} for (u, ip, port, proto), n in conns.items()]
    apps = [{"uid": u, "owner": owner(uids, u), "vendor": vendor(uids.get(u, []), u), "bytes": b} for u, b in moved.items()]
    by_vendor = collections.defaultdict(lambda: {"bytes": 0, "destinations": set(), "apps": set()})
    for a in apps:
        by_vendor[a["vendor"]]["bytes"] += a["bytes"]; by_vendor[a["vendor"]]["apps"].add(a["owner"])
    for t in talk:
        by_vendor[t["vendor"]]["destinations"].add(t["ip"]); by_vendor[t["vendor"]]["apps"].add(t["owner"])
    vend = {k: {"bytes": v["bytes"], "destinations": len(v["destinations"]), "apps": sorted(v["apps"])} for k, v in by_vendor.items()}
    google_dest = sorted({t["ip"] for t in talk if GOOGLE_HOSTS.search(t["rdns"])})
    return {"run": run.name, "talk": talk, "apps": sorted(apps, key=lambda a: -a["bytes"]), "vendors": vend,
            "listening": sorted(map(list, listens)), "google_destinations": google_dest,
            "samples": sum(conns.values()), "distinct_connections": len(conns), "bytes_source": source}


def report(run):
    s = analyse(run)
    (run / "summary.json").write_text(json.dumps(s, indent=1))
    L = [f"# netwatch {run.name}: {s['samples']} samples of {s['distinct_connections']} distinct connections", "",
         f"## By vendor (bytes moved during the window, from {s['bytes_source']} | distinct destinations | apps)"]
    for k, v in sorted(s["vendors"].items(), key=lambda x: -x[1]["bytes"]):
        L.append(f"{k} | {v['bytes']:,} | {v['destinations']} | {', '.join(v['apps'][:6])}")
    L += ["", "## Bytes per app during the window (dumpsys netstats, rx+tx)"]
    L += [f"{a['owner']} | {a['vendor']} | {a['bytes']:,}" for a in s["apps"]]
    L += ["", "## Outgoing (package | remote ip | reverse dns | port | proto | samples)"]
    for t in sorted(s["talk"], key=lambda t: (t["owner"], -t["samples"])):
        L.append(f"{t['owner']} | {t['ip']} | {t['rdns']} | {t['port']} | {t['proto']} | {t['samples']}")
    L += ["", "## Listening sockets (package | proto | local ip | port)"] + [" | ".join(map(str, x)) for x in s["listening"]]
    (run / "REPORT.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


def compare(a_dir, b_dir):
    A, B = (json.loads((d / "summary.json").read_text()) if (d / "summary.json").exists() else analyse(d) for d in (a_dir, b_dir))
    L = [f"# {B['run']} compared with {A['run']}", "", "vendor | bytes before | bytes after | destinations before | after"]
    for k in sorted(set(A["vendors"]) | set(B["vendors"])):
        va, vb = A["vendors"].get(k, {}), B["vendors"].get(k, {})
        L.append(f"{k} | {va.get('bytes', 0):,} | {vb.get('bytes', 0):,} | {va.get('destinations', 0)} | {vb.get('destinations', 0)}")
    tot = lambda S: sum(v["bytes"] for v in S["vendors"].values())
    L.append(f"total | {tot(A):,} | {tot(B):,} | {sum(v['destinations'] for v in A['vendors'].values())} | "
             f"{sum(v['destinations'] for v in B['vendors'].values())}")
    seen = {(t["owner"], t["ip"]) for t in A["talk"]}
    new = sorted({(t["owner"], t["ip"], t["rdns"]) for t in B["talk"] if (t["owner"], t["ip"]) not in seen})
    L += ["", f"## New talkers in {B['run']} ({len(new)}): owner | ip | reverse dns"] + [" | ".join(x) for x in new]
    print("\n".join(L))
    return L


def selftest():
    ns = ("  ident=[{type=1}] uid=10113 set=FOREGROUND tag=0x0\n    NetworkStatsHistory: bucketDuration=7200\n"
          "      st=1 rb=100 rp=1 tb=50 tp=1 op=0\n      st=2 rb=10 rp=1 tb=5 tp=1 op=0\n"
          "  ident=[{type=1}] uid=10113 set=FOREGROUND tag=0x401\n    NetworkStatsHistory: bucketDuration=7200\n"
          "      st=1 rb=999 rp=1 tb=999 tp=1 op=0\n  ident=[{type=1}] uid=1000 set=DEFAULT tag=0x0\n"
          "    NetworkStatsHistory: bucketDuration=7200\n      st=1 rb=7 rp=1 tb=3 tp=1 op=0\n")
    assert netstats_bytes(ns) == {10113: 165, 1000: 10}, netstats_bytes(ns)
    bpf = "  mAppUidStatsMap:\n    uid rxBytes rxPackets txBytes txPackets\n    10049 9950 32 9740 41\n    1000 20 1 5 1\n  mStatsMapA: OK\n"
    assert bpf_bytes(bpf) == {10049: 19690, 1000: 25}, bpf_bytes(bpf)
    assert vendor(["com.google.android.gms"], 10113) == "google" and vendor([], 1000) == "android-system"
    assert vendor(["com.solanamobile.wallet"], 10200) == "solana-mobile" and vendor(["org.fdroid.fdroid"], 10300) == "other-apps"
    assert addr("0100007F:1F90") == (ipaddress.IPv4Address("127.0.0.1"), 8080)
    assert GOOGLE_HOSTS.search("lhr48s29-in-f14.1e100.net") and not GOOGLE_HOSTS.search("mullvad.net")
    print("netwatch_report self-check: OK")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--selftest"]:
        selftest()
    elif sys.argv[1:2] == ["--compare"]:
        compare(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        report(Path(sys.argv[1]))
