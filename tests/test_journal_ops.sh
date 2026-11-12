#!/bin/bash
# Mac dry run of the journaled phone changes (debloat/ops.sh, restore/restore.sh, privacy/firewall.sh) against a fake
# adb that records every command: rows written before the change, values that survive the phone's shell (quotes,
# spaces, ;), one row per change, Solana packages and system uids refused, a restore that a later reapply respects.
set -euo pipefail
cd "$(dirname "$0")/.."
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/debloat" "$T/restore" "$T/privacy"
cp debloat/ops.sh "$T/debloat/"; cp restore/restore.sh "$T/restore/"; cp privacy/firewall.sh "$T/privacy/"
cat > "$T/adb.sh" <<'A'
a() {  # fake adb: logs each call as adb would send it (arguments joined by spaces), answers what the scripts ask
  printf '%s\n' "$*" >> "$CALLS"
  case "$*" in
    "get-state") echo device ;;
    "shell settings get global device_name") printf "Alex's phone\r\n" ;;
    "shell pm list packages -U com.android.location.fused") echo "package:com.android.location.fused uid:1000" ;;
    "shell pm list packages -U org.example.app") echo "package:org.example.app uid:10123" ;;
    "shell pm list packages "*) echo "package:${@: -1}" ;;
    "shell cmd connectivity get-chain3-enabled") echo false ;;
    "shell cmd connectivity get-package-networking-enabled"*) echo true ;;
    "shell settings put"*) [ -z "${FAIL_PUT:-}" ] ;;
  esac; }
A
export CALLS=$T/calls
sh_args() { sh -c "printf '[%s]' $1"; }  # how the phone's shell splits what adb sends
cd "$T"
( GROUP=T1; . ./adb.sh; . debloat/ops.sh
  op_setting global device_name "it's new; reboot" >/dev/null
  FAIL_PUT=1 op_setting global device_name "never applied" >/dev/null || true
  log role sms $'a\nb' c
  op_disable com.solanamobile.rewards >/dev/null || true )
sent=$(grep '^shell settings put global device_name' calls | head -1); sent=${sent#shell settings put global device_name }
[ "$(sh_args "$sent")" = "[it's new; reboot]" ] || { echo "value split or run by the phone's shell: $sent"; exit 1; }
rows=$(tail -n +2 restore/journal.tsv)
[ "$(grep -c $'\tsetting\tglobal/device_name\t' <<<"$rows")" = 2 ] || { echo "the failed change has no row (written after?)"; exit 1; }
grep -q $'\trole\tsms\ta b\tc$' <<<"$rows" || { echo "a line break split a row"; exit 1; }
grep -q solanamobile calls && { echo "a Solana package reached the phone"; exit 1; }
: > calls
bash restore/restore.sh --dry-run T1 > out
got=$(grep -m1 "would: settings put global device_name" out); got=${got#would: settings put global device_name }
[ "$(sh_args "$got")" = "[Alex's phone]" ] || { echo "restore breaks on a quote: $got"; exit 1; }
GROUP=P12 bash privacy/firewall.sh block com.android.location.fused org.example.app > out
grep -q "REFUSED (shares a system uid" out && ! grep -q "set-package-networking-enabled false com.android.location.fused" calls \
  || { cat out; echo "a system uid was cut off"; exit 1; }
[ "$(bash privacy/firewall.sh status | grep -c org.example.app)" = 1 ] || { echo "block not seen by status"; exit 1; }
printf '%s\tALL\trestored\trestore.sh\t\t\n' "$(date '+%F %T')" >> restore/journal.tsv
[ "$(bash privacy/firewall.sh status | grep -c org.example.app)" = 0 ] || { echo "reapply would undo the restore"; exit 1; }
echo "journal ops dry run: OK"
