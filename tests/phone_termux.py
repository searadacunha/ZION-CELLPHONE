#!/usr/bin/env python3
"""Run a script inside Termux on the Seeker, from the Mac, and wait for its end.
  python3 tests/phone_termux.py SCRIPT [--timeout 900] [--push PATH ...] [--keep-front]
adb has no door into Termux (an ordinary app): the script goes to shared storage, ONE short line is typed in Termux's
terminal, and the output comes back in a file. The typed line is checked, because adb's keyboard sometimes loses the
start of a line: typed again when the job has not started after a few seconds.
--push copies files or folders to /sdcard/Download/seeker-zero/ first (the script finds them in $ZION_PUSH).
Needs a Termux session at its shell prompt. Exit code: the script's (124 on timeout, 125 if it never started).
Every job has its own file names: a script that bash is reading is never replaced."""
import argparse, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERIAL = os.environ.get("SEEKER_SERIAL") or (ROOT / ".serial").read_text().strip()
ADB = os.environ.get("ADB_BIN", "/opt/homebrew/share/android-commandlinetools/platform-tools/adb")
BASE = "/sdcard/Download/seeker-zero"


def adb(*args, timeout=120):
    r = subprocess.run([ADB, "-s", SERIAL, *args], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    return r.stdout + r.stderr


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("script")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--push", action="append", default=[])
    ap.add_argument("--keep-front", action="store_true", help="bring Termux back to the front when the job is over")
    a = ap.parse_args()
    name = time.strftime("j-%Y%m%d-%H%M%S")
    job = f"{BASE}/jobs/{name}"
    adb("shell", f"mkdir -p {BASE}/jobs")
    for p in a.push:
        print(adb("push", p, f"{BASE}/{Path(p).name}").strip().splitlines()[-1])
    wrapper = ROOT / "tests" / f".{name}.sh"
    wrapper.write_text(f"#!/data/data/com.termux/files/usr/bin/bash\n: > {job}.started\nexport ZION_PUSH={BASE}\n"
                       f"bash {job}.body > {job}.log 2>&1\necho $? > {job}.rc\n")
    try:
        adb("push", str(wrapper), f"{job}.sh")
        adb("push", a.script, f"{job}.body")
    finally:
        wrapper.unlink()
    for attempt in range(3):
        adb("shell", "am start -n com.termux/.app.TermuxActivity")
        time.sleep(2)
        adb("shell", f"input text 'bash%s{job}.sh'; input keyevent 66")
        for _ in range(6):
            time.sleep(1)
            if "started" in adb("shell", f"ls {job}.started 2>/dev/null"):
                break
        else:
            print(f"job not started (try {attempt + 1}): typing again", file=sys.stderr)
            adb("shell", "input keyevent 66")  # whatever half line is there goes away
            continue
        break
    else:
        sys.exit(125)
    end = time.time() + a.timeout
    rc = ""
    while time.time() < end and not rc:
        time.sleep(2)
        rc = adb("shell", f"cat {job}.rc 2>/dev/null").strip()
    print(adb("shell", f"cat {job}.log 2>/dev/null"), end="")
    if a.keep_front:
        adb("shell", "am start -n com.termux/.app.TermuxActivity")
    if not rc:
        print(f"\n[timeout after {a.timeout} s: the job may still run, see {job}.log on the phone]", file=sys.stderr)
        sys.exit(124)
    sys.exit(int(rc) if rc.isdigit() else 1)


if __name__ == "__main__":
    main()
