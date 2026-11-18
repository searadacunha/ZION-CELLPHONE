#!/bin/bash
# The per-app firewall, for real, on the phone. A throwaway app (tests/nettest: it fetches one URL when asked and writes
# what happened) is installed, asked for a web page with its network open, cut by privacy/firewall.sh, then open again.
# The block is real if the request works, fails, then works. It also asks 127.0.0.1 while cut, to learn whether the
# chain cuts an app off the phone's own services. The phone ends as it started: restore.sh undoes the group, the test
# app is removed.
#   tests/firewall_real.sh | tee tests/phone/<date>-firewall/firewall.log
set -u
cd "$(dirname "$0")/.." && . ./adb.sh
PKG=zero.seeker.nettest; export GROUP=P12-firewall-test
WEB=https://example.com/ LOCAL=http://127.0.0.1:8080/health   # the second one: OPERATOR's llama-server, in Termux
R=/sdcard/Android/data/$PKG/files/result.txt
[ -f tests/nettest/build/nettest.apk ] || bash launcher/build.sh tests/nettest nettest >/dev/null
a install -r tests/nettest/build/nettest.apk 2>&1 | tail -1
fetch() {  # id url: asks the app, waits for its line
  local out=
  a shell am start -n $PKG/.Fetch --es url "$2" --es id "$1" >/dev/null 2>&1
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14; do
    sleep 1; out=$(a shell "grep -m1 '^$1[[:space:]]' $R 2>/dev/null" | tr -d '\r'); [ -n "$out" ] && break
  done
  echo "${out:-$1 NO RESULT (the app wrote nothing in 14 s)}"; }
date; echo "before: $(a shell cmd connectivity get-chain3-enabled | tr -d '\r'), $(a shell cmd connectivity get-package-networking-enabled $PKG | tr -d '\r')"
open1=$(fetch open1 $WEB); echo "$open1"
fetch local1 $LOCAL
bash privacy/firewall.sh block $PKG
cut=$(fetch cut $WEB); echo "$cut"
fetch cutlocal $LOCAL
bash privacy/firewall.sh status
bash privacy/firewall.sh allow $PKG
open2=$(fetch open2 $WEB); echo "$open2"
bash restore/restore.sh "$GROUP" | tail -1
echo "after: $(a shell cmd connectivity get-chain3-enabled | tr -d '\r'), $(a shell cmd connectivity get-package-networking-enabled $PKG | tr -d '\r')"
a uninstall $PKG | tail -1
case "$open1|$cut|$open2" in
  *"HTTP 200"*"|"*FAILED*"|"*"HTTP 200"*) echo "VERDICT: the block is real (the request works, fails while cut, works again)" ;;
  *) echo "VERDICT: NOT ESTABLISHED"; exit 1 ;;
esac
