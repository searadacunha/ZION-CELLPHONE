# Source after adb.sh. Every phone change goes through these functions so restore/restore.sh can undo it.
# Journal: restore/journal.tsv  (time, group, op, target, old, new). Append-only. A row is written BEFORE its change, with
# the old value: if the script dies in between, restore.sh still knows; a row whose change failed undoes to the same state.
J=restore/journal.tsv
[ -f "$J" ] || printf 'time\tgroup\top\ttarget\told\tnew\n' > "$J"
GROUP=${GROUP:-manual}

# Never touched by any script, whatever a group file says (Seed Vault, its update path, TEE, boot/security core).
PROTECTED='^(com\.solanamobile\..*|com\.trustkernel\..*|android|com\.android\.(systemui|settings|phone|server\.telecom|nfc|se|keychain|certinstaller|shell|providers\..*|bluetooth|networkstack.*|rkpdapp|permissioncontroller|packageinstaller)|com\.google\.android\.(permissioncontroller|packageinstaller|webview|ext\.services|ext\.shared|networkstack|modulemetadata|configupdater)|com\.mediatek)$'

# empty fields are written as "-" (`read` with IFS=tab merges consecutive tabs); a tab or line break inside a value
# (multi-line command output) becomes a space, so a row stays one row
log() {
  local f row="$(date '+%F %T')"$'\t'"$GROUP"
  for f in "$1" "$2" "${3:--}" "${4:--}"; do row+=$'\t'"${f//[$'\t\r\n']/ }"; done
  printf '%s\n' "$row" >> "$J"; }
q() { printf "'%s'" "${1//\'/\'\\\'\'}"; }  # one argument for the phone's shell, whatever it holds

op_disable() {  # reversible: pm disable-user keeps app data
  local p=$1 st
  [[ $p =~ $PROTECTED ]] && { echo "REFUSED (protected): $p"; return 1; }
  a shell pm list packages "$p" | grep -qx "package:$p" || { echo "skip (absent): $p"; return 0; }
  a shell pm list packages -d "$p" | grep -qx "package:$p" && { echo "skip (already disabled): $p"; return 0; }
  log disable "$p" enabled disabled-user
  st=$(a shell pm disable-user --user 0 "$p" 2>&1)
  if grep -q "new state: disabled-user" <<<"$st"; then echo "disabled: $p"
  else echo "FAILED: $p -> $st"; return 1; fi
}

op_setting() {  # ns key value
  local old; old=$(a shell settings get "$1" "$2" | tr -d '\r')
  log setting "$1/$2" "$old" "$3"
  a shell settings put "$1" "$2" "$(q "$3")" && echo "setting $1/$2: $old -> $3"
}

op_install() {  # apk path on the Mac; signature must already be verified by the caller
  local pkg; pkg=$("${ANDROID_SDK_ROOT:-/opt/homebrew/share/android-commandlinetools}/build-tools/37.0.0/aapt2" dump packagename "$1")
  log install "$pkg" - "$(basename "$1")"
  a install -r "$1" 2>&1 | grep -q "^Success" && echo "installed: $pkg"
}

op_revoke() {  # pkg perm: revoke a runtime permission, mark it user-set so default grants do not bring it back
  local st; st=$(a shell dumpsys package "$1" | grep -m1 " $2: granted=true") || { echo "skip (not granted): $1 $2"; return 0; }
  grep -q -E "SYSTEM_FIXED|POLICY_FIXED" <<<"$st" && { echo "skip (fixed by system): $1 $2"; return 0; }
  log revoke "$1 $2" granted revoked
  a shell pm revoke "$1" "$2" && a shell pm set-permission-flags "$1" "$2" user-set && echo "revoked: $1 $2"
}

op_role() {  # role pkg: make pkg the default holder (dialer, sms, browser, home)
  local old; old=$(a shell cmd role get-role-holders "$1" | tr -d '\r'); old=${old:--}
  [ "$old" = "$2" ] && { echo "skip (already): $1 $2"; return 0; }
  log role "$1" "$old" "$2"
  a shell cmd role add-role-holder "$1" "$2" 0 && echo "role $1: $old -> $2"
}

op_ime() {  # ime component: enable and make it the default keyboard
  local old; old=$(a shell settings get secure default_input_method | tr -d '\r')
  log ime default "$old" "$1"
  a shell ime enable "$1" >/dev/null && a shell ime set "$1" >/dev/null && echo "keyboard: $old -> $1"
}
