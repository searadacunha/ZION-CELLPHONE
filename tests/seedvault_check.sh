#!/bin/bash
# Seed Vault invariants, read-only. Never queries the vault's content, only package/service/HAL state.
#   tests/seedvault_check.sh baseline   -> writes tests/seedvault_baseline.txt
#   tests/seedvault_check.sh            -> compares the phone to the baseline, exit 1 on any difference
set -u
cd "$(dirname "$0")/.." && . ./adb.sh
BASE=tests/seedvault_baseline.txt

snapshot() {
  local p
  for p in com.solanamobile.seedvaultimpl com.solanamobile.wallet com.solanamobile.dappstore com.solanamobile.dappstore.updater com.trustkernel.android.se; do
    local d; d=$(a shell dumpsys package "$p")
    echo "pkg $p path=$(a shell pm path "$p" | head -1 | sed 's/package://') $(grep -m1 -o 'versionCode=[0-9]*' <<<"$d") $(grep -m1 -o 'version:[0-9]*, signatures:\[[^]]*\]' <<<"$d") enabled=$(a shell pm list packages -e "$p" | grep -cx "package:$p")"
  done
  echo "seedvault_apk_sha256 $(a shell sha256sum /system/app/SeedVault/SeedVault.apk | cut -d' ' -f1)"
  echo "service_seedvault $(a shell service check seedvault)"
  for act in SIGN_TRANSACTION SIGN_MESSAGE GET_PUBLIC_KEY AUTHORIZE_SEED_ACCESS CREATE_SEED IMPORT_SEED; do
    echo "intent $act -> $(a shell cmd package query-activities --brief -a com.solanamobile.seedvault.wallet.v1.ACTION_$act | grep / | sort | tr -d " " | paste -sd, -)"
  done
  for h in android.hardware.security.keymint.IKeyMintDevice/default android.hardware.security.keymint.IKeyMintDevice/strongbox \
           android.hardware.weaver.IWeaver/default android.hardware.gatekeeper.IGatekeeper/default android.hardware.secure_element.ISecureElement/eSE1; do
    echo "hal $h $(a shell service list | grep -c -F "$h:")"
  done
  for p in ro.boot.verifiedbootstate ro.boot.flash.locked ro.boot.vbmeta.device_state ro.crypto.state; do echo "prop $p $(a shell getprop $p)"; done
  echo "wallet_perm_privileged $(a shell dumpsys package com.solanamobile.wallet | grep -m1 'ACCESS_SEED_VAULT_PRIVILEGED: granted' | grep -o 'granted=[a-z]*')"
  echo "lockscreen_disabled $(a shell locksettings get-disabled)"
  echo "fingerprints_enrolled $(a shell dumpsys fingerprint | grep -o '"count":[0-9]*' | head -1)"
}

a get-state | grep -qx device || { echo "Seeker not connected"; exit 2; }
if [ "${1:-}" = baseline ]; then snapshot > "$BASE"; cat "$BASE"; exit 0; fi
[ -f "$BASE" ] || { echo "no baseline, run: $0 baseline"; exit 2; }
if diff <(cat "$BASE") <(snapshot); then echo "SEED VAULT INVARIANTS: OK"; else echo "SEED VAULT INVARIANTS: CHANGED (see diff above)"; exit 1; fi
