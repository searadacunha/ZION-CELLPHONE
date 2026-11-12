#!/bin/bash
# Network baseline without VPN or root: samples /proc/net/{tcp,tcp6,udp,udp6} through adb (they carry the owner uid),
# maps uid -> package, and names remote IPs by reverse DNS. Domain names per request need PCAPdroid (on the phone).
#   privacy/netwatch.sh [seconds=120] [label=baseline]   -> privacy/<date>_<label>/
set -u
cd "$(dirname "$0")/.." && . ./adb.sh
SECS=${1:-120}; LABEL=${2:-baseline}
OUT=privacy/$(date +%Y%m%d_%H%M%S)_$LABEL; mkdir -p "$OUT"
a shell pm list packages -U | sed -E 's/package:(.*) uid:(.*)/\2 \1/' | sort -n > "$OUT/uids.txt"
a shell dumpsys netstats detail > "$OUT/netstats_before.txt"
end=$(( $(date +%s) + SECS ))
while [ "$(date +%s)" -lt "$end" ]; do
  a shell 'for f in tcp tcp6 udp udp6; do sed 1d /proc/net/$f | sed "s/^/$f /"; done' >> "$OUT/raw.txt"
  sleep 2
done
a shell dumpsys netstats detail > "$OUT/netstats_after.txt"
python3 -I privacy/netwatch_report.py "$OUT"
