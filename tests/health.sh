#!/bin/bash
# Quick health check after each change: Seed Vault invariants, radios, core services, new crashes.
set -u
cd "$(dirname "$0")/.." && . ./adb.sh
fail=0
ok() { printf '  %-28s %s\n' "$1" "$2"; }
bad() { printf '  %-28s %s  <-- FAIL\n' "$1" "$2"; fail=1; }

tests/seedvault_check.sh >/dev/null && ok seedvault "invariants OK" || bad seedvault "invariants changed (tests/seedvault_check.sh)"
boot=$(a shell getprop sys.boot_completed); [ "$boot" = 1 ] && ok boot_completed 1 || bad boot_completed "$boot"
for s in phone isms wifi bluetooth_manager nfc seedvault keystore2 biometric fingerprint package activity; do
  a shell service check $s | grep -q found && ok "service $s" found || bad "service $s" missing
done
wifi=$(a shell cmd wifi status 2>/dev/null | head -1); ok wifi "$wifi"
sim=$(a shell dumpsys telephony.registry | grep -m1 -o 'mVoiceRegState=[0-9]*([A-Z_]*)'); ok "cell voice" "${sim:-?}"
net=$(a shell dumpsys connectivity | grep -m1 -o 'Active default network: [0-9a-z]*'); ok network "${net:-none}"
bt=$(a shell settings get global bluetooth_on); ok bluetooth_on "$bt"
nfc=$(a shell dumpsys nfc | grep -m1 -o 'mState=[a-z_]*'); ok nfc "${nfc:-?}"
sim=$(a shell getprop gsm.sim.state); ok "sim state" "$sim"
# SINCE = phone epoch seconds when the change started (set by apply.sh); default: last 10 min
SINCE=${SINCE:-$(( $(a shell date +%s) - 600 ))}
crashes=$(a logcat -d -b crash -T "$SINCE.000" 2>/dev/null | grep -o 'Process: [^,]*' | sort | uniq -c)
[ -z "$crashes" ] && ok "app crashes" none || bad "app crashes" "$(echo $crashes)"
exit $fail
