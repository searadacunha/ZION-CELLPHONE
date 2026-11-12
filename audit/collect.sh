#!/bin/bash
# Read-only audit of the Seeker. Writes audit/<timestamp>/. Changes nothing on the phone.
# Never reads Seed Vault secrets: only package metadata and public service state.
set -u
cd "$(dirname "$0")/.." && . ./adb.sh
OUT=audit/$(date +%Y%m%d_%H%M%S); mkdir -p "$OUT"
s() { a shell "$@" 2>&1; }

a get-state | grep -qx device || { echo "Seeker $SEEKER_SERIAL not connected"; exit 1; }

s getprop > "$OUT/getprop.txt"
for f in "" -s -3 -d -e -u; do
  s pm list packages -f -U --show-versioncode $f | sort > "$OUT/packages${f:-_all}.txt"
done
s pm list packages --user 0 -u | sort > "$OUT/packages_u0_incl_uninstalled.txt"
s pm list users > "$OUT/users.txt"
s pm list features | sort > "$OUT/features.txt"
s pm list permissions -g -f > "$OUT/permissions.txt"
s cmd package list packages -a --apex-only > "$OUT/apex.txt"
s dumpsys package > "$OUT/dumpsys_package.txt"
s dumpsys account | sed -E 's/name=[^,]+/name=<redacted>/' > "$OUT/accounts_redacted.txt"
s dumpsys device_policy > "$OUT/device_policy.txt"
s dumpsys biometric > "$OUT/biometric.txt"
s dumpsys fingerprint > "$OUT/fingerprint.txt"
s dumpsys connectivity > "$OUT/connectivity.txt"
s dumpsys netpolicy > "$OUT/netpolicy.txt"
s dumpsys role > "$OUT/roles.txt"
s dumpsys deviceidle > "$OUT/deviceidle.txt"
s dumpsys meminfo -s > "$OUT/meminfo.txt"
s cat /proc/meminfo > "$OUT/proc_meminfo.txt"
s cat /proc/cpuinfo > "$OUT/cpuinfo.txt"
s df -h > "$OUT/df.txt"
s settings list global > "$OUT/settings_global.txt"
s settings list secure > "$OUT/settings_secure.txt"
s settings list system > "$OUT/settings_system.txt"
s service list > "$OUT/services.txt"
s ps -A -o USER,PID,NAME > "$OUT/processes.txt"
s cmd overlay list > "$OUT/overlays.txt"
s dumpsys activity services > "$OUT/running_services.txt"
s cmd package resolve-activity --brief -c android.intent.category.HOME -a android.intent.action.MAIN > "$OUT/home_launcher.txt"
s 'ls -l /dev/block/by-name 2>&1; ls /vendor/etc/vintf/manifest* /vendor/etc/vintf/manifest/ 2>&1' > "$OUT/partitions_and_vintf.txt"
s 'cat /vendor/etc/vintf/manifest.xml /vendor/etc/vintf/manifest/*.xml 2>/dev/null' > "$OUT/vintf_manifest.xml"
s 'ls -la /data/local/tmp' > "$OUT/data_local_tmp.txt"

# Summary of the key facts asked for in Phase 1.
{
  for p in ro.product.model ro.product.brand ro.product.device ro.product.name ro.build.fingerprint \
           ro.build.version.release ro.build.version.sdk ro.build.version.security_patch ro.vendor.build.security_patch \
           ro.build.type ro.build.tags ro.product.cpu.abi ro.board.platform ro.soc.model ro.hardware \
           ro.boot.verifiedbootstate ro.boot.flash.locked ro.boot.vbmeta.device_state ro.boot.veritymode \
           ro.crypto.state ro.crypto.type ro.debuggable ro.secure ro.adb.secure persist.sys.usb.config \
           ro.oem_unlock_supported sys.oem_unlock_allowed ro.treble.enabled ro.boot.slot_suffix ro.virtual_ab.enabled; do
    printf '%-36s %s\n' "$p" "$(grep -F "[$p]" "$OUT/getprop.txt" | sed -E 's/.*\]: \[(.*)\]/\1/')"
  done
  echo "oem_unlock (settings global): $(s settings get global oem_unlock_allowed)"
  echo "packages total=$(wc -l < "$OUT/packages_all.txt") system=$(wc -l < "$OUT/packages-s.txt") user=$(wc -l < "$OUT/packages-3.txt") disabled=$(wc -l < "$OUT/packages-d.txt")"
  echo "google-ish packages: $(grep -c -i -E 'google|android\.vending|gms' "$OUT/packages_all.txt")"
  echo "solana/seed packages:"; grep -i -E 'solana|seed|saga|osom' "$OUT/packages_all.txt"
} > "$OUT/SUMMARY.txt"
cat "$OUT/SUMMARY.txt"
echo "-> $OUT"
