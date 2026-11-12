#!/usr/bin/env python3
"""Drive the phone's screen from the Mac by what it says, through adb (uiautomator dump + input tap).
  python3 tests/phone_ui.py texts                 every visible text, with its center
  python3 tests/phone_ui.py tap "> terminal"      tap the first node whose text equals it (else contains it)
  python3 tests/phone_ui.py long "> ai"           long press
  python3 tests/phone_ui.py focus                 the focused window
Uses the serial of adb.sh (.serial file or SEEKER_SERIAL). The dump never leaves the phone and the Mac's memory."""
import html, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERIAL = os.environ.get("SEEKER_SERIAL") or (ROOT / ".serial").read_text().strip()
ADB = os.environ.get("ADB_BIN", "/opt/homebrew/share/android-commandlinetools/platform-tools/adb")


def adb(*args, timeout=30):
    return subprocess.run([ADB, "-s", SERIAL, *args], capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL).stdout


def nodes():
    """[(text, (x, y))] of the current screen; the dump is read from the phone's tmp, then deleted there."""
    path = "/data/local/tmp/zion-ui.xml"
    adb("shell", f"uiautomator dump {path} >/dev/null 2>&1")
    xml = adb("shell", f"cat {path}; rm -f {path}")
    out = []
    for m in re.finditer(r'<node [^>]*?text="([^"]*)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
        t, x1, y1, x2, y2 = html.unescape(m.group(1)), *map(int, m.groups()[1:])
        if t:
            out.append((t, ((x1 + x2) // 2, (y1 + y2) // 2)))
    return out


def find(text):
    ns = nodes()
    return next((c for t, c in ns if t == text), None) or next((c for t, c in ns if text in t), None)


def tap(text, long=False, tries=3):
    for _ in range(tries):
        c = find(text)
        if c:
            if long:
                adb("shell", f"input swipe {c[0]} {c[1]} {c[0]} {c[1]} 900")
            else:
                adb("shell", f"input tap {c[0]} {c[1]}")
            return c
        time.sleep(1.5)
    raise SystemExit(f"not on screen: {text!r}")


def focus():
    m = re.search(r"mCurrentFocus=(\S+ \S+ \S+)", adb("shell", "dumpsys window"))
    return m.group(1) if m else "?"


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:] or ["texts"]
    if cmd == "texts":
        for t, c in nodes():
            print(f"{c[0]:5} {c[1]:5}  {t}")
    elif cmd in ("tap", "long"):
        print("tapped", rest[0], "at", tap(rest[0], long=cmd == "long"))
    elif cmd == "focus":
        print(focus())
