#!/bin/bash
# Undo phone changes from restore/journal.tsv, newest first.
#   restore/restore.sh            undo every group
#   restore/restore.sh <group>    undo one group (e.g. G1)
#   restore/restore.sh --dry-run [group]
# Installed apps are listed, not uninstalled (uninstalling deletes their data): remove them by hand if wanted.
set -u
cd "$(dirname "$0")/.." && . ./adb.sh
DRY=0; [ "${1:-}" = --dry-run ] && { DRY=1; shift; }
WANT=${1:-}
run() { if [ $DRY = 1 ]; then echo "would: $*"; else a shell "$@"; fi; }

a get-state | grep -qx device || { echo "Seeker not connected"; exit 2; }
tail -n +2 restore/journal.tsv | tail -r | while IFS=$'\t' read -r t g op target old new; do
  [ -n "$WANT" ] && [ "$g" != "$WANT" ] && continue
  case $op in
    disable) run pm enable --user 0 "$target" ;;
    setting) ns=${target%%/*}; key=${target#*/}
             if [ "$old" = null ]; then run settings delete "$ns" "$key"; else run settings put "$ns" "$key" "'${old//\'/\'\\\'\'}'"; fi ;;
    install) echo "installed by SEEKER-ZERO, kept: $target (uninstall: adb shell pm uninstall $target)" ;;
    revoke)  pkg=${target% *}; perm=${target#* }
             run pm clear-permission-flags "$pkg" "$perm" user-set; run pm grant "$pkg" "$perm" ;;
    role)    if [ "$old" = - ]; then run cmd role remove-role-holder "$target" "$new" 0
             else for h in ${old//;/ }; do run cmd role add-role-holder "$target" "$h" 0; done; fi ;;
    ime)     run ime set "$old" ;;
    appop)   run appops set --uid "${target% *}" "${target#* }" "$old" ;;
    doze)    run dumpsys deviceidle whitelist "-$target" ;;
    start)   echo "$target: stops by itself at the next reboot" ;;
    wallpaper) run am start -n zero.seeker.launcher/.Main --es wallpaper restore ;;  # the launcher puts its saved copy back
    netblock) run cmd connectivity set-package-networking-enabled true "$target" ;;  # privacy/firewall.sh
    netallow) run cmd connectivity set-package-networking-enabled false "$target" ;;
    netchain) run cmd connectivity set-chain3-enabled "$old" ;;
    restored) ;;
    *) echo "unknown op $op for $target" ;;
  esac
done
[ $DRY = 0 ] && printf '%s\t%s\trestored\t%s\t\t\n' "$(date '+%F %T')" "${WANT:-ALL}" "restore.sh" >> restore/journal.tsv
echo "done; check: tests/seedvault_check.sh"
