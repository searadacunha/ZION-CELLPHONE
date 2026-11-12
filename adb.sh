# Source this file: defines `a`, an adb pinned to the Seeker only (a TCL TV is also attached).
# The Homebrew cask adb is blocked by Gatekeeper (App Store-only mode); the SDK copy is not quarantined.
# The phone's serial (from `adb devices`): $SEEKER_SERIAL, else the one-line file .serial next to this script (not in git).
SEEKER_SERIAL=${SEEKER_SERIAL:-$(cat "$(dirname "${BASH_SOURCE[0]:-.}")/.serial" 2>/dev/null)}
[ -n "$SEEKER_SERIAL" ] || echo "adb.sh: set SEEKER_SERIAL or write your phone's serial into .serial" >&2
ADB_BIN=${ADB_BIN:-/opt/homebrew/share/android-commandlinetools/platform-tools/adb}
[ -x "$ADB_BIN" ] || ADB_BIN=adb
# stdin from /dev/null: `adb shell` would otherwise swallow the input of the calling `while read` loop
a() { "$ADB_BIN" -s "$SEEKER_SERIAL" "$@" </dev/null; }
ai() { "$ADB_BIN" -s "$SEEKER_SERIAL" "$@"; }  # same, when stdin must reach the phone
