#!/bin/bash
# Per-app network block without root and without a VPN: Android's own firewall chain FIREWALL_CHAIN_OEM_DENY_3, driven
# by the shell user (adb, or Shizuku's rish on the phone). Every change goes to restore/journal.tsv (undo: restore.sh).
#   privacy/firewall.sh block PKG...     cut PKG off every network (Wi-Fi and mobile)
#   privacy/firewall.sh allow PKG...     give it back
#   privacy/firewall.sh status           chain on/off, and the state of every package journaled here
#   privacy/firewall.sh reapply          after a reboot (Android forgets the chain): block again what the journal says
# Never for the Seed Vault, Solana apps, Android core, Termux, Shizuku or this launcher (same list as debloat/ops.sh).
set -u
cd "$(dirname "$0")/.." && . ./adb.sh
GROUP=${GROUP:-P12-firewall}
. debloat/ops.sh
cmd=${1:-status}; shift || true
state() { a shell cmd connectivity get-package-networking-enabled "$1" 2>&1 | tr -d '\r'; }
chain() { a shell cmd connectivity get-chain3-enabled 2>&1 | tr -d '\r'; }  # "chain:enabled" or "chain:disabled" (seen on the Seeker, 13/11)
chain_on() {  # stops the script if the chain cannot be turned on: a block would be journaled but not real
  case $(chain) in
    chain:enabled) return 0 ;;
    chain:disabled) ;;
    *) echo "chain3 unavailable on this build: $(chain)"; exit 1 ;;
  esac
  log netchain chain3 false true
  a shell cmd connectivity set-chain3-enabled true
  [ "$(chain)" = chain:enabled ] || { echo "chain3 could not be enabled: $(chain)"; exit 1; }; }
blocked_in_journal() {  # packages whose last netblock/netallow entry is a block, and that no later restore.sh undid
  awk -F'\t' '$3 == "netblock" || $3 == "netallow" { last[$4] = $3; grp[$4] = $2 }
               $3 == "restored" { for (p in last) if ($2 == "ALL" || $2 == grp[p]) delete last[p] }
               END { for (p in last) if (last[p] == "netblock") print p }' "$J" | sort
}
system_uid() {  # a uid under 10000 is shared by Android itself (system_server, phone, network stack): never cut it off
  local uid; uid=$(a shell pm list packages -U "$1" | tr -d '\r' | grep -m1 "^package:$1 " | sed 's/.*uid://; s/,.*//')
  [ -z "$uid" ] || [ "$uid" -lt 10000 ]; }
case $cmd in
  block|allow)
    [ $# -gt 0 ] || { echo "usage: $0 $cmd PKG..."; exit 2; }
    [ "$cmd" = block ] && chain_on
    for p in "$@"; do
      if [[ $p =~ $PROTECTED || $p =~ ^(com\.termux|moe\.shizuku\.privileged\.api|zero\.seeker\.launcher)$ ]]; then echo "REFUSED (protected): $p"; continue; fi
      a shell pm list packages "$p" | tr -d '\r' | grep -qx "package:$p" || { echo "skip (not installed): $p"; continue; }
      if [ "$cmd" = block ] && system_uid "$p"; then echo "REFUSED (shares a system uid, or uid unknown): $p"; continue; fi
      before=$(state "$p")
      if [ "$cmd" = block ]; then log netblock "$p" "$before" false; a shell cmd connectivity set-package-networking-enabled false "$p"; want=deny
      else log netallow "$p" "$before" true; a shell cmd connectivity set-package-networking-enabled true "$p"; want=allow; fi
      [ "$(state "$p")" = "$p:$want" ] && echo "$(state "$p")" || echo "FAILED: $p is $(state "$p"), wanted $want"
    done ;;
  reapply)
    chain_on
    for p in $(blocked_in_journal); do a shell cmd connectivity set-package-networking-enabled false "$p"; state "$p"; done ;;
  status)
    chain
    for p in $(blocked_in_journal); do state "$p"; done ;;
  *) sed -n '2,8p' "$0"; exit 2 ;;
esac
