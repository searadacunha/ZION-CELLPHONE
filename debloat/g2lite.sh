#!/bin/bash
# G2-lite, in a safe order: install replacements, switch defaults, then disable Google apps (apply.sh runs the
# health checks), then revoke Play Services permissions and turn on a filtering Private DNS. Undo: restore/restore.sh G2lite
set -u
cd "$(dirname "$0")/.." && . ./adb.sh
GROUP=G2lite; . debloat/ops.sh
C=apk-manager/cache
for p in helium314.keyboard org.fossify.phone org.fossify.messages org.fossify.contacts org.fossify.gallery org.fossify.clock \
         org.fossify.math org.fossify.calendar org.fossify.filemanager org.mozilla.fennec_fdroid app.comaps.fdroid; do
  a shell pm list packages "$p" | grep -qx "package:$p" && { echo "skip (installed): $p"; continue; }
  grep -q "^$p	" apk-manager/verified.tsv || { echo "NOT VERIFIED, refusing: $p"; exit 1; }
  op_install "$C/$p.apk" || { echo "install failed: $p, stopping before any disable"; exit 1; }
done

kb=$(a shell ime list -a -s | grep -m1 '^helium314.keyboard/')
[ -n "$kb" ] || { echo "HeliBoard input method not found, stopping (Gboard must stay)"; exit 1; }
op_ime "$kb"
op_role android.app.role.DIALER org.fossify.phone
op_role android.app.role.SMS org.fossify.messages
op_role android.app.role.BROWSER org.mozilla.fennec_fdroid

debloat/apply.sh G2lite || exit 1

# Play Services and Play Store keep running for updates and push, without access to these
for pkg in com.google.android.gms com.android.vending; do
  for perm in ACCESS_FINE_LOCATION ACCESS_COARSE_LOCATION ACCESS_BACKGROUND_LOCATION READ_CONTACTS WRITE_CONTACTS \
              RECORD_AUDIO CAMERA READ_CALENDAR WRITE_CALENDAR READ_SMS RECEIVE_SMS SEND_SMS READ_CALL_LOG \
              BODY_SENSORS ACTIVITY_RECOGNITION BLUETOOTH_SCAN BLUETOOTH_CONNECT BLUETOOTH_ADVERTISE NEARBY_WIFI_DEVICES \
              UWB_RANGING READ_MEDIA_IMAGES READ_MEDIA_VIDEO READ_MEDIA_AUDIO READ_EXTERNAL_STORAGE; do
    op_revoke "$pkg" "android.permission.$perm"
  done
done

# Mullvad DNS "base": blocks ads, trackers and malware domains, DNS over TLS for the whole phone
op_setting global private_dns_mode hostname
op_setting global private_dns_specifier base.dns.mullvad.net
sleep 3
tests/health.sh
