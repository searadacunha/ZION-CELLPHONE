#!/bin/bash
# Mac dry run of tests/termux-chain.sh with fakes: termux-api clients that READ STDIN like the real ones (the 12/11 bug
# class), a rish that runs its command through a real sh -c (quoting), fake cmd/dumpsys/seeker-ai and fake bench scripts.
# Checks: all 5 models measured in order, the battery test postponed then done at the end, notification texts intact,
# a failed download leaves the model MISSING, and a second run skips every finished step.
set -euo pipefail
cd "$(dirname "$0")/.."
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/home/bin" "$T/home/models" "$T/d/tests" "$T/d/ai"
cp tests/termux-chain.sh "$T/d/tests/"
w() { printf '#!/bin/bash\n%s\n' "$2" > "$1"; chmod +x "$1"; }
w "$T/bin/termux-battery-status" 'cat >/dev/null; echo "{\"percentage\": 80, \"plugged\": \"PLUGGED_AC\"}"'
w "$T/bin/termux-wake-lock" 'cat >/dev/null; exit 0'; cp "$T/bin/termux-wake-lock" "$T/bin/termux-wake-unlock"
w "$T/bin/seeker-ai" 'cat >/dev/null; echo "seeker-ai $*" >> "$CALLS"'
w "$T/bin/cmd" 'for a in "$@"; do printf "[%s]" "$a"; done >> "$CALLS"; echo >> "$CALLS"'
w "$T/bin/dumpsys" 'echo "Thermal Status: 0"; echo "Temperature{mValue=40.0, mType=0, mName=CPU, mStatus=0}"'
w "$T/home/bin/rish" 'cat >/dev/null; [ "$1" = -c ] && exec sh -c "$2"'
w "$T/d/tests/termux-p6-sweep.sh" 'echo "sweep" >> "$CALLS"'
w "$T/d/ai/install-model.sh" 'case $2 in Ministral*) exit 1;; esac; touch "$HOME/models/$2"; echo "install $2" >> "$CALLS"'
w "$T/d/tests/eval_fr.py" 'import sys; open(__import__("os").environ["CALLS"], "a").write("eval " + sys.argv[2] + "\n")'
w "$T/d/tests/bench_agent.py" 'import sys; open(__import__("os").environ["CALLS"], "a").write("bench " + sys.argv[3] + "\n")'
# bench_power: nobody unplugs the first time (exit 3), measured the second time
w "$T/d/tests/bench_power.py" 'import os, sys
f = os.environ["CALLS"] + ".bp"; n = int(open(f).read()) + 1 if os.path.exists(f) else 1; open(f, "w").write(str(n))
open(os.environ["CALLS"], "a").write("bench_power " + " ".join(sys.argv[1:]) + "\n"); sys.exit(3 if n == 1 else 0)'
for f in "$T"/d/tests/*.py; do sed -i '' '1s|^#!/bin/bash$|#!/usr/bin/env python3|' "$f"; done
run() { HOME=$T/home PATH="$T/bin:$PATH" CALLS=$T/calls CHAIN_DIR=$T/d CHAIN_NAP=0 CHAIN_RETRY_S=0 \
  timeout 120 bash "$T/d/tests/termux-chain.sh"; }
run
C=$T/calls
python3 - "$C" "$T/d/chain-summary.txt" <<'P'
import sys
calls = open(sys.argv[1]).read(); summary = open(sys.argv[2]).read()
evals = [l.split()[1] for l in calls.splitlines() if l.startswith("eval ")]
assert evals == ["hauhau-q4km", "qwen35-q40", "qwen3-2507-q40", "granite4micro-q40"], evals  # Ministral: download failed
benches = [l.split()[1] for l in calls.splitlines() if l.startswith("bench ")]
assert benches == [e + "-v4" for e in evals], benches
assert calls.count("bench_power ") == 2 and "--wait-h 2" in calls and "--wait-h 10" in calls, calls
assert calls.index("bench_power") < calls.index("sweep") < calls.index("eval "), "order: battery, sweep, models"
assert "[Test batterie : débranche le téléphone et éteins l'écran (environ 75 min). Une autre notification dira quand le rebrancher.]" in calls, calls
assert "rebrancher le téléphone au Mac.]" in calls and "(4 modèles sur 5, test batterie : fait)" in calls, calls
assert "model-ministral3-q40: MISSING" in summary and "battery: nobody unplugged within 2 h" in summary, summary
assert "arrêtées avant la fin" not in calls, "normal end must not say stopped"
print("chain dry run: OK")
P
before=$(grep -c -E '^(eval|bench|sweep)' "$C")
run
after=$(grep -c -E '^(eval|bench|sweep)' "$C")
[ "$before" = "$after" ] && [ "$(grep -c '^bench_power' "$C")" = 2 ] || { echo "re-run did not skip finished steps"; exit 1; }
echo "chain re-run skips finished steps: OK"
