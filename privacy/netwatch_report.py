#!/usr/bin/env python3
"""Aggregate netwatch.sh samples: who (package) talks to whom (IP, reverse DNS, port), and who listens.
Usage: python3 -I privacy/netwatch_report.py privacy/<run>"""
import collections, ipaddress, socket, sys
from pathlib import Path

run = Path(sys.argv[1])
uids = collections.defaultdict(list)
for line in (run / "uids.txt").read_text().splitlines():
    uid, pkg = line.split(" ", 1)
    uids[int(uid.split(",")[0])].append(pkg)

def owner(uid):
    if uid in uids: return ",".join(uids[uid][:3]) + ("…" if len(uids[uid]) > 3 else "")
    return {0: "root", 1000: "system", 1001: "radio", 1051: "netd", 1052: "dns", 1073: "networkstack"}.get(uid, f"uid{uid}")

def addr(hexaddr):
    ip, port = hexaddr.split(":")
    b = bytes.fromhex(ip)
    if len(b) == 4: a = ipaddress.IPv4Address(b[::-1])
    else:  # /proc stores IPv6 as four little-endian 32-bit words
        a = ipaddress.IPv6Address(b"".join(b[i:i + 4][::-1] for i in range(0, 16, 4)))
        a = a.ipv4_mapped or a
    return a, int(port, 16)

conns, listens = collections.Counter(), set()
for line in (run / "raw.txt").read_text().splitlines():
    f = line.split()
    if len(f) < 9 or not f[1].endswith(":"): continue
    proto, local, remote, st, uid = f[0], f[2], f[3], f[4], int(f[8])
    (la, lp), (ra, rp) = addr(local), addr(remote)
    if ra.is_unspecified:
        if st == "0A" or proto.startswith("udp"): listens.add((owner(uid), proto, str(la), lp))
        continue
    if ra.is_loopback: continue
    conns[(owner(uid), str(ra), rp, proto)] += 1

names = {}
def rdns(ip):
    if ip not in names:
        try: names[ip] = socket.gethostbyaddr(ip)[0]
        except OSError: names[ip] = "-"
    return names[ip]

lines = [f"# netwatch {run.name}: {sum(conns.values())} samples of {len(conns)} distinct connections", "",
         "## Outgoing (package | remote ip | reverse dns | port | proto | samples)"]
for (who, ip, port, proto), n in sorted(conns.items(), key=lambda x: (x[0][0], -x[1])):
    lines.append(f"{who} | {ip} | {rdns(ip)} | {port} | {proto} | {n}")
lines += ["", "## Listening sockets (package | proto | local ip | port)"]
lines += [" | ".join(map(str, x)) for x in sorted(listens)]
(run / "REPORT.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
