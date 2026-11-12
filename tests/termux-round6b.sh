#!/usr/bin/env bash
# Inside Termux, round 6b: redo the context sweep of round 6 for both models. In round 6 its last variant failed for both
# with "error: invalid argument: --no-mmap" (this llama-server build has --load-mode instead): a defect of the
# benchmark, now fixed. Offline, same order as round 6 and, as there, no cool-down: in round 6 each sweep ran hot,
# right after its benchmark (a first try of this round waited 25 min for the skin to reach 31 C, then was stopped).
# Report: round6b.log and bench-*-sweep.json
exec > >(tee /sdcard/Download/seeker-zero/round6b.log) 2>&1
set -u
B=/sdcard/Download/seeker-zero
. $B/tests/termux-wifi.sh
echo "== start $(date)"
cp $B/tests/bench_agent.py ~/bench_agent.py
trap wifi_on EXIT
wifi_off || exit 1
for run in "hauhau-q4km Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf" "qwen35-q40 Qwen3.5-4B-Q4_0.gguf"; do
  set -- $run
  echo "== skin $(~/bin/rish -c "dumpsys thermalservice" 2>&1 | sed -n '/Current temperatures from HAL/,$p' | grep -m1 'mName=SKIN' | sed 's/.*mValue=\([0-9.]*\).*/\1/') C before $1"
  python ~/bench_agent.py ~/models/$2 --label $1 --sweep-only
  echo "sweep $1 exit $? $(date +%T)"
done
seeker-ai --stop
echo "== round6b done $(date)"
