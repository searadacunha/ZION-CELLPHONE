#!/usr/bin/env bash
# Inside Termux, round 6: deploy seeker-ai v3 and the dashboard (first backups and the config kept), then benchmark
# OFFLINE, as the agent's engine, the HauhauCS Qwen3.5-4B Q4_K_M and the current default Qwen3.5-4B Q4_0.
# Wi-Fi is switched off for the benchmarks and back on at the end, whatever happens. The default model does not change.
# Decision rule, written before any measurement (JOURNAL_AGENTS.md, 12/11): the HauhauCS model becomes the default only
# if it finishes the whole benchmark without server error and stays within these margins of the current default:
# tool calls right >= baseline - 3 (of 30), at most 2 invalid JSON calls, Python >= baseline - 2 (of 12),
# agent tasks >= baseline - 1 (of 3), generation speed >= 80 %, French answers in French.
# Report: /sdcard/Download/seeker-zero/round6.log and bench-*.json
exec > >(tee /sdcard/Download/seeker-zero/round6.log) 2>&1
set -u
B=/sdcard/Download/seeker-zero
D=~/.local/share/seeker-ai
. $B/tests/termux-wifi.sh
echo "== start $(date)"
echo "== deploy seeker-ai v3 and seeker-dash"
mkdir -p $D
[ -e $D/seeker-ai.before-v3 ] || cp $PREFIX/bin/seeker-ai $D/seeker-ai.before-v3
[ -e $D/seeker-dash.before-v3 ] || cp $PREFIX/bin/seeker-dash $D/seeker-dash.before-v3
install -m 755 $B/ai/seeker-ai $PREFIX/bin/seeker-ai
install -m 755 $B/terminal/seeker-dash $PREFIX/bin/seeker-dash
cp $B/tests/bench_agent.py ~/bench_agent.py
seeker-ai --stop; sleep 2
curl -s -m 3 http://127.0.0.1:8080/health >/dev/null && { echo "== ABORT: the old llama-server still answers on port 8080"; exit 1; }
python - <<'PY'
import json, pathlib, shutil, time
c = pathlib.Path.home() / ".config/seeker-ai/config.json"
old = json.loads(c.read_text()) if c.exists() else {}
if c.exists():
    shutil.copy2(c, c.with_name("config.json.bak-" + time.strftime("%Y%m%d-%H%M%S")))
# v2 keys (per-tool overrides, 8192 context, cat/head run without asking) would defeat the v3 levels: only these stay
new = {k: old[k] for k in ("model", "llama_server") if k in old}
c.parent.mkdir(parents=True, exist_ok=True)
c.write_text(json.dumps(new, indent=2))
print("config before:", json.dumps(old)); print("config now:   ", json.dumps(new))
PY
ls ~/.config/seeker-ai/
seeker-ai --models; seeker-ai --status

trap wifi_on EXIT
cool() {  # same thermal start for every run: wait for the skin sensor to be at 31 C or less, 25 minutes at most
  local i t
  for i in $(seq 50); do
    t=$(~/bin/rish -c "dumpsys thermalservice" 2>&1 | sed -n '/Current temperatures from HAL/,$p' | grep -m1 'mName=SKIN' | sed 's/.*mValue=\([0-9.]*\).*/\1/')
    echo "$(date +%T) skin ${t:-?} C"
    awk "BEGIN { exit !(${t:-99} <= 31.0) }" 2>/dev/null && return
    sleep 30
  done
}
echo "== llama-server memory options"; $(python -c 'import json,pathlib; print(json.loads((pathlib.Path.home()/".config/seeker-ai/config.json").read_text())["llama_server"])') --help 2>&1 | grep -E -A1 "cache-ram" | head -3
free -m
wifi_off || exit 1
~/bin/rish -c "ping -c 1 -W 3 1.1.1.1" 2>&1 | tail -1

for run in "hauhau-q4km Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf" "qwen35-q40 Qwen3.5-4B-Q4_0.gguf"; do
  set -- $run
  echo "== cool down before $1"; cool
  echo "== bench $1 $(date +%T)"
  python ~/bench_agent.py ~/models/$2 --label $1 --sweep
  echo "bench $1 exit $? $(date +%T)"
done
seeker-ai --stop
echo "== round6 done $(date)"
