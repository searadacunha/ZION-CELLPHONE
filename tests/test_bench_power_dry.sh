#!/bin/bash
# Mac dry run of tests/bench_power.py: fake Shizuku (battery sysfs + thermal HAL lines), fake termux-* and seeker-ai,
# fake llama-server (tests/fake_llama_server.py). Checks the windows, the energy arithmetic and the JSON it writes.
set -euo pipefail
cd "$(dirname "$0")/.."
T=${KEEP_DIR:-$(mktemp -d)}; [ -n "${KEEP_DIR:-}" ] || trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/out"
cat > "$T/bin/rish" <<'R'
#!/bin/sh
# discharging 500 mA at 3.8 V (current_now is NEGATIVE when discharging on the Seeker), charge counter going down
# 1 mAh per call; thermal status 1; screen off
n=$(cat "$HOME/n" 2>/dev/null || echo 0); n=$((n + 1)); echo $n > "$HOME/n"
echo "P -500000 3800000 $((2000000 - n * 1000)) 80 Discharging"
echo "mWakefulness=Asleep"
echo "Thermal Status: 1"
echo "	Temperature{mValue=61.5, mType=0, mName=CPU, mStatus=0}"
echo "	Temperature{mValue=37.25, mType=3, mName=SKIN, mStatus=0}" >&2
R
printf '#!/bin/sh\necho %s\n' "'{\"plugged\": \"UNPLUGGED\", \"percentage\": 80}'" > "$T/bin/termux-battery-status"
printf '#!/bin/sh\nexit 0\n' > "$T/bin/seeker-ai"; cp "$T/bin/seeker-ai" "$T/bin/termux-wake-lock"; cp "$T/bin/seeker-ai" "$T/bin/termux-wake-unlock"
printf '#!/bin/sh\nexec python3 %s "$@"\n' "$PWD/tests/fake_llama_server.py" > "$T/bin/llama-server"
chmod +x "$T"/bin/*
HOME=$T PATH="$T/bin:$PATH" BENCH_OUT_DIR=$T/out BENCH_SETTLE_S=0 BENCH_SAMPLE_S=1 LLAMA_SERVER=$T/bin/llama-server \
  python3 tests/bench_power.py "$T/model.gguf" --idle-min 0.05 --run-min 0.08 --cool-min 0.01 --configs default,eco2 > "$T/log" 2>&1 \
  || { cat "$T/log"; exit 1; }
python3 - "$T/out/bench-power-model.json" <<'P'
import json, sys
d = json.load(open(sys.argv[1]))
w = {x["name"]: x for x in d["windows"]}
assert set(w) >= {"rest", "default", "eco2", "cool-after-default"} and d.get("done"), list(w)
assert w["rest"]["drain_ma_from_charge"] > 0 and w["rest"]["power_w_from_charge"] > 0, w["rest"]
for name in ("default", "eco2"):
    x = w[name]
    assert x["tokens"] > 0 and x["power_w_mean"] == 1.9 and x["j_per_token_charge"] > 0 and x["tps_mean"] == 6.0, {k: x.get(k) for k in ("tokens", "power_w_mean", "j_per_token_charge", "tps_mean")}
    assert len(x["samples"]) >= 2 and not x["plugged_seen"] and not x["screen_awake_seen"] and x["n_errors"] == 0, x
    assert x["cpu_c_max"] == 61.5 and x["skin_c_max"] == 37.25 and x["thermal_status_max"] == 1, x
assert w["eco2"]["opts"][:2] == ["-t", "2"]
print("bench_power dry run: OK")
P
# nobody unplugs: exit code 3 and the JSON says why
printf '#!/bin/sh\necho %s\n' "'{\"plugged\": \"PLUGGED_AC\", \"percentage\": 80}'" > "$T/bin/termux-battery-status"
rc=0; HOME=$T PATH="$T/bin:$PATH" BENCH_OUT_DIR=$T/out python3 tests/bench_power.py "$T/plugged.gguf" --wait-h 0.0005 > "$T/log2" 2>&1 || rc=$?
[ $rc = 3 ] && grep -q '"aborted": "still plugged' "$T/out/bench-power-plugged.json" || { cat "$T/log2"; echo "abort path: FAIL rc=$rc"; exit 1; }
echo "bench_power abort path: OK"
