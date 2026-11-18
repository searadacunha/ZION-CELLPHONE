#!/bin/bash
# Which names does one app ask for? PCAPdroid (already on the phone) as an on-demand recorder, driven from the Mac.
#   privacy/pcap.sh start [PKG]   start a capture (of that app only)
#   privacy/pcap.sh stop          stop it, bring the file to privacy/pcap/<date>.pcap and list the names (pcap_domains.py)
#   privacy/pcap.sh status
# What to know before using it:
# - PCAPdroid records through Android's VPN slot, and Android has only one: while it records, no other VPN app runs
#   (URnetwork, RethinkDNS). It holds the slot only between start and stop.
# - The FIRST start shows two questions on the phone: PCAPdroid's own ("allow this app to control captures") and
#   Android's VPN request. They are the owner's to answer: no script taps them, and OPERATOR's screen tool refuses to.
#   NOT TESTED on the Seeker on 13/11 for that reason: PCAPdroid had never been given the VPN slot (appops: no
#   ACTIVATE_VPN), and nobody was there to answer.
# - With Private DNS on (this phone: AdGuard), DNS questions are not in the capture: names come from TLS and HTTP only.
set -u
cd "$(dirname "$0")/.." && . ./adb.sh
CTRL=com.emanuelef.remote_capture/.activities.CaptureCtrl
running() { a shell dumpsys activity services com.emanuelef.remote_capture | grep -q "CaptureService"; }
case ${1:-status} in
  start)
    a shell pm list packages com.emanuelef.remote_capture | grep -q remote_capture || { echo "PCAPdroid is not installed"; exit 1; }
    filter=(); [ -n "${2:-}" ] && filter=(-e app_filter "$2")
    a shell am start -e action start -e pcap_dump_mode pcap_file -e pcap_name zion.pcap "${filter[@]}" -n "$CTRL" >/dev/null
    echo "asked PCAPdroid to record${2:+ $2}. If the phone shows a question, it is yours to answer."
    sleep 4; running && echo "recording: yes" || echo "recording: not yet (a question is waiting on the phone, or it was refused)" ;;
  stop)
    a shell am start -e action stop -n "$CTRL" >/dev/null; sleep 3
    mkdir -p privacy/pcap; out=privacy/pcap/$(date +%Y%m%d_%H%M%S).pcap
    a pull /sdcard/Download/PCAPdroid/zion.pcap "$out" >/dev/null 2>&1 || { echo "no capture file on the phone (nothing was recorded)"; exit 1; }
    echo "$out"; python3 -I privacy/pcap_domains.py "$out" ;;
  status)
    running && echo "PCAPdroid: recording" || echo "PCAPdroid: not recording"
    echo "VPN slot ever given to PCAPdroid: $(a shell appops get com.emanuelef.remote_capture ACTIVATE_VPN | tr -d '\r' | head -1)" ;;
  *) sed -n '2,5p' "$0"; exit 2 ;;
esac
