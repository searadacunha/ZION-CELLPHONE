#!/bin/bash
# Mac dry run of tests/termux-eval-tools-chain.sh with fakes (termux-api clients that read stdin, rish through sh -c, fake
# seeker-ai and fake eval_tools.py). Checks: models from `seeker-ai --models` measured in order, each one started and
# evaluated as a child of the chain (busy file = parent PID), the battery floor and the cooling wait, a model that does
# not start is reported and skipped, notification text, and a second run skips the finished models.
set -euo pipefail
cd "$(dirname "$0")/.."
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/home/bin" "$T/d/tests"
command -v timeout >/dev/null || {  # macOS has no GNU timeout (CI runners): perl's alarm stops a command the same way
  printf '%s\n' '#!/bin/sh' 'exec perl -e '"'"'alarm shift; exec @ARGV or die "$ARGV[0]: $!\n"'"'"' "$@"' > "$T/bin/timeout"
  chmod 755 "$T/bin/timeout"; }
TO=$(PATH="$T/bin:$PATH" command -v timeout)
cp tests/termux-eval-tools-chain.sh "$T/d/tests/"
w() { printf '#!/bin/bash\n%s\n' "$2" > "$1"; chmod +x "$1"; }
# battery: 10 % for the first 3 calls (the floor must wait), then 80 %; 45 C for the first 6 (the cooling must wait), then 30 C
w "$T/bin/termux-battery-status" 'cat >/dev/null; f=$CALLS.bat; n=$(( $(cat $f 2>/dev/null || echo 0) + 1 )); echo $n > $f
p=80; [ $n -le 3 ] && p=10; t=30.0; [ $n -le 6 ] && t=45.0; echo "{\"percentage\": $p, \"plugged\": \"PLUGGED_AC\", \"temperature\": $t}"'
w "$T/bin/termux-wake-lock" 'cat >/dev/null; exit 0'; cp "$T/bin/termux-wake-lock" "$T/bin/termux-wake-unlock"
w "$T/home/bin/rish" 'cat >/dev/null; [ "$1" = -c ] && { printf "[%s]\n" "$2" >> "$CALLS"; exit 0; }'
# fake seeker-ai: --models lists three models (default starred, names with spaces after the star as in the real output);
# --model X --start records X, the busy file head and its own parent; Ministral does not load
w "$T/bin/seeker-ai" 'cat >/dev/null
case "$1" in
  --models) printf "* %-55s %5.2f GB\n  %-55s %5.2f GB\n  %-55s %5.2f GB\n  %-55s %5.2f GB\n" A-hauhau.gguf 2.7 B-qwen.gguf 2.4 Ministral-3B.gguf 2.0 mmproj-x.mmproj 0.5;;
  --model) case "$2" in Ministral*) exit 1;; esac; echo "start $2 busy=$(head -1 "$HOME/.cache/seeker-ai/busy") parent=$PPID" >> "$CALLS";;
  --stop) echo stop >> "$CALLS";;
esac'
w "$T/d/tests/eval_tools.py" 'import os, sys, json
b = os.path.expanduser("~/.cache/seeker-ai/busy")
out = sys.argv[sys.argv.index("--out") + 1]
os.makedirs(os.path.dirname(out), exist_ok=True); open(out, "w").write("{}")
open(os.environ["CALLS"], "a").write("eval %s busy=%s parent=%d timeout=%s\n" % (os.path.basename(out), open(b).read().split()[0], os.getppid(), sys.argv[sys.argv.index("--timeout") + 1]))'
sed -i '' '1s|^#!/bin/bash$|#!/usr/bin/env python3|' "$T/d/tests/eval_tools.py"
run() { HOME=$T/home PATH="$T/bin:$PATH" CALLS=$T/calls CHAIN_DIR=$T/d CHAIN_NAP=0 "$TO" 120 bash "$T/d/tests/termux-eval-tools-chain.sh" "$@"; }
run
python3 - "$T/calls" "$T/d" <<'P'
import sys
calls, d = open(sys.argv[1]).read(), sys.argv[2]
summary, log = open(d + "/eval-tools-summary.txt").read(), open(d + "/eval-tools-chain.log").read()
ev = [l for l in calls.splitlines() if l.startswith(("start", "eval"))]
assert [l.split()[1] for l in ev] == ["A-hauhau.gguf", "evaltools-A-hauhau.json", "B-qwen.gguf", "evaltools-B-qwen.json"], ev  # mmproj not listed, Ministral never started
for l in ev:  # every start and eval is a child of the one process named in OPERATOR's busy file: the chain
    f = dict(x.split("=", 1) for x in l.split() if x.startswith(("busy=", "parent=")))
    assert f["busy"] == f["parent"], l
assert len({l.split("busy=")[1].split()[0] for l in ev}) == 1 and "timeout=240" in calls
assert "waiting for 25 %" in log and "cool waiting" in log and "cool: battery 30.0 C" in log, log
assert "evaltools-Ministral-3B: FAILED" in summary and "evaltools-A-hauhau: OK" in summary and "evaltools: 2 measured, 1 failed" in summary, summary
assert calls.count("stop") >= 3 and "[cmd notification post -S bigtext -t 'ZION ZERO' zion_eval_tools 'Mesures des appels d'\\''outils finies (2 modèles, 1 en échec)." in calls, calls
assert "arrêtées avant la fin" not in calls and "Mesures des appels d outils" not in calls
import os
assert os.path.exists(d + "/results/evaltools-A-hauhau.json") and os.path.exists(d + "/chain-done/evaltools-all")
print("eval-tools chain dry run: OK")
P
[ ! -e "$T/home/.cache/seeker-ai/busy" ] || { echo "busy file left after the chain ended"; exit 1; }
before=$(grep -c '^eval' "$T/calls"); run B-qwen.gguf Ministral-3B.gguf; after=$(grep -c '^eval' "$T/calls")
[ "$before" = "$after" ] || { echo "re-run measured a finished model again"; exit 1; }
# a live job already holding the memory: nothing starts
mkdir -p "$T/home/.cache/seeker-ai"; sleep 30 & P=$!; printf '%s\nbusy\n' "$P" > "$T/home/.cache/seeker-ai/busy"
if run A-hauhau.gguf 2>/dev/null; then echo "ran while another job held the memory"; kill $P; exit 1; fi
kill $P
echo "eval-tools chain re-run and busy guard: OK"
