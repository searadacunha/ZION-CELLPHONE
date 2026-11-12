#!/bin/bash
# Apply one group file (debloat/groups/<G>.txt): disable each package, then run the health checks.
# Stops on the first failed check; undo with restore/restore.sh <G>.
set -u
cd "$(dirname "$0")/.." && . ./adb.sh
G=$1; F=debloat/groups/$G.txt; [ -f "$F" ] || { echo "no $F"; exit 2; }
GROUP=$G; . debloat/ops.sh
tests/seedvault_check.sh >/dev/null || { echo "Seed Vault check fails BEFORE $G: stopping"; exit 1; }
export SINCE=$(a shell date +%s)
sed -E 's/#.*//' "$F" | while read -r p; do [ -n "$p" ] && op_disable "$p"; done
sleep 5
tests/health.sh || { echo "HEALTH FAILED after $G -> restore/restore.sh $G"; exit 1; }
