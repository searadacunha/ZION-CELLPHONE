# Sourced by the round scripts inside Termux: Wi-Fi off and on through Shizuku (uid 2000), each step checked.
# Always read rish with 2>&1: it spreads the command's output between stdout and stderr at random.
# On this phone, after a toggle, the system's own scans come back empty and it does not rejoin its network by itself
# (tests/phone/wifi-scan-history-20261112.txt): a scan from Settings > Wi-Fi is what reconnects it.
wifi_off() {
  ~/bin/rish -c "cmd wifi set-wifi-enabled disabled" 2>&1; sleep 6
  ~/bin/rish -c "cmd wifi status" 2>&1 | grep -q "Wifi is disabled" || { echo "== ABORT: Shizuku does not answer or Wi-Fi is still on"; return 1; }
  echo "== offline: Wifi is disabled, $(~/bin/rish -c "dumpsys connectivity" 2>&1 | grep -m1 'Active default network')"
}
wifi_on() {
  local n i s
  s=$(~/bin/rish -c "cmd wifi status" 2>&1 | grep -m1 "Wifi is connected")
  for n in 1 2 3 4; do
    [ -n "$s" ] && break
    ~/bin/rish -c "cmd wifi set-wifi-enabled enabled; sleep 3; am start -a android.settings.WIFI_SETTINGS" >/dev/null 2>&1
    for i in $(seq 20); do
      s=$(~/bin/rish -c "cmd wifi status" 2>&1 | grep -m1 "Wifi is connected"); [ -n "$s" ] && break; sleep 3
    done
  done
  ~/bin/rish -c "am start -n com.termux/com.termux.app.TermuxActivity" >/dev/null 2>&1
  if [ -n "$s" ]; then echo "== wifi back: $s"; else echo "== WIFI NOT RECONNECTED: open Settings > Wi-Fi on the phone"; fi
}
