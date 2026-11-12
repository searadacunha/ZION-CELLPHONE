#!/bin/bash
# Dry run of tests/bench_agent.py on the Mac: fake llama-server, fake rish replaying a probe copied from the Seeker.
# Checks that the harness runs end to end and that the sampler reads temperatures, power and network correctly.
set -eu
cd "$(dirname "$0")/.."
S=$(mktemp -d); mkdir -p "$S/bin" "$S/home"
trap 'pkill -f fake_llama_server.py 2>/dev/null || true; rm -rf "$S" tests/__pycache__ ai/__pycache__' EXIT
ln -s "$PWD/ai/seeker-ai" "$S/bin/seeker-ai"
printf '#!/bin/sh\nexec python3 %s "$@"\n' "$PWD/tests/fake_llama_server.py" > "$S/bin/fake-llama-server"
# uid 501 = the Mac user here: one external connection of "Termux", one of another app, one listening socket open to the network
cat > "$S/bin/rish" <<RISH
#!/bin/sh
cat <<'OUT'
Thermal Status: 2
Cached temperatures:
	Temperature{mValue=99.9, mType=0, mName=CPU, mStatus=0}
Current temperatures from HAL:
	Temperature{mValue=61.5, mType=0, mName=CPU, mStatus=0}
	Temperature{mValue=40.25, mType=3, mName=SKIN, mStatus=0}
Current cooling devices from HAL:
@@
1800000
2500000
@@
-411400
4417000
2946000
97
@@
  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1F9B 00000000:0000 0A 00000000:00000000 00:00000000 00000000 $(id -u) 0 1 1
   1: 00000000:1F9C 00000000:0000 0A 00000000:00000000 00:00000000 00000000 $(id -u) 0 2 1
   2: 2601A8C0:C350 04B8FA8E:01BB 01 00000000:00000000 00:00000000 00000000 $(id -u) 0 3 1
   3: 2601A8C0:C351 04B8FA8E:01BB 01 00000000:00000000 00:00000000 00000000 10113 0 4 1
   4: 0100007F:C352 0100007F:1F9B 01 00000000:00000000 00:00000000 00000000 $(id -u) 0 5 1
OUT
RISH
chmod +x "$S/bin/fake-llama-server" "$S/bin/rish"
echo "{\"workdir\": \"$S/home/seeker-work\"}" > "$S/conf.json"
echo "not a model" > "$S/model.gguf"
HOME="$S/home" PATH="$S/bin:$PATH" SEEKER_AI_CONFIG="$S/conf.json" SEEKER_AI_DATA="$S/data" BENCH_OUT_DIR="$S" BENCH_SAMPLE_S=1 \
  python3 tests/bench_agent.py "$S/model.gguf" --label dry --server fake-llama-server --sweep > "$S/out.txt" 2>&1 || { cat "$S/out.txt"; exit 1; }
python3 - "$S/bench-dry.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1])); s = r["summary"]
assert s["errors"] is None and s["request_errors"] == 0, s
assert s["cpu_temp_c_max"] == 61.5 and s["skin_temp_c_max"] == 40.25 and s["thermal_status_max"] == 2, s   # live block, not the cached 99.9
assert s["big_core_mhz_busy_min_max"] == [2500, 2500] and s["battery_mw_idle"] == 1817.0 == s["battery_mw_busy_mean"], s
assert s["battery_pct_start_end"] == [97, 97] and r["samples"]["charge_uah"][0] == 2946000, s
assert s["termux_external_connections_max"] == 1 and s["all_external_connections_max"] == 2 and s["termux_open_listen_max"] == 1, s
# what the fake server can answer: the battery call (2 seeds), one Python function (2 seeds), the fib task
assert s["tool_calls_pass"] == "2/30" and s["tool_calls_valid_json"] == "2/2" and s["python_pass"] == "2/12" and s["convo_turns_ok"] == 12, s
assert r["agent"]["write_and_run"]["pass"] and not r["agent"]["git_commit"]["pass"] and r["convo"][0]["ctx_tokens"] == 333, r["agent"]
assert len(r["ctx_sweep"]) == 4 and len(r["timeline"]) > 60 and s["probe_tps_start_end"] == [6.0, 6.0], s
assert len(r["samples"]["t"]) == len(r["samples"]["cpu_pct"]) == len(r["samples"]["skin_c"]) == len(r["samples"]["mem_available_mb"]), "samples must stay aligned"
assert r["samples"]["skin_c"][1] is None and "mem_available_mb_min" in s and r["server_args"] == ["--cache-ram", "0", "--load-mode", "none"], s   # Shizuku every 3rd sample
print("bench_agent dry run: OK")
PY
HOME="$S/home" PATH="$S/bin:$PATH" SEEKER_AI_CONFIG="$S/conf.json" SEEKER_AI_DATA="$S/data" BENCH_OUT_DIR="$S" BENCH_SAMPLE_S=1 \
  python3 tests/bench_agent.py "$S/model.gguf" --label dry --server fake-llama-server --sweep-only > "$S/out2.txt" 2>&1 || { cat "$S/out2.txt"; exit 1; }
python3 - "$S/bench-dry-sweep.json" "$S/bench-dry.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
assert [x["args"] for x in r["ctx_sweep"]] == [[], [], [], ["--load-mode", "none"]] and not any("error" in x for x in r["ctx_sweep"]), r["ctx_sweep"]
assert "tools" not in r and json.load(open(sys.argv[2]))["tools"], "sweep-only must not run nor overwrite the main benchmark"
print("bench_agent --sweep-only dry run: OK")
PY
