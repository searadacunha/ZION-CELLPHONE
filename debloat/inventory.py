#!/usr/bin/env python3
"""Join the phone's package list (audit/<run>) with UAD-NG's list. Writes debloat/inventory.csv.
Usage: python3 -I debloat/inventory.py audit/<run>"""
import csv, json, re, sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
run = Path(sys.argv[1])
uad = json.load(open(root / "debloat/uad/uad_lists.json"))
disabled = {m.group(1) for m in re.finditer(r"=(\S+) versionCode", (run / "packages-d.txt").read_text())}
system = {m.group(1) for m in re.finditer(r"=(\S+) versionCode", (run / "packages-s.txt").read_text())}

rows = []
for line in (run / "packages_all.txt").read_text().splitlines():
    m = re.match(r"package:(.*)=(\S+) versionCode:(\d+) uid:(\d+)", line)
    assert m, line  # a format change in pm output must not silently drop packages
    apk, pkg, ver, uid = m.groups()
    part = apk.split("/")[1] if apk.startswith("/") else "?"
    u = uad.get(pkg, {})
    rows.append(dict(pkg=pkg, partition=part, system=pkg in system, disabled=pkg in disabled, uid=uid,
                     version=ver, uad_list=u.get("list", ""), uad_removal=u.get("removal", "unknown"),
                     uad_desc=" ".join(u.get("description", "").split())[:300]))

with open(root / "debloat/inventory.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)

from collections import Counter
print(len(rows), "packages;", Counter(r["uad_removal"] for r in rows))
