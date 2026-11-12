#!/usr/bin/env python3
"""Compare the files written on the phone by bench_agent.py, as Markdown tables, with the failed cases listed.
Run: python3 tests/bench_report.py tests/phone/bench-hauhau-q4km.json tests/phone/bench-qwen35-q40.json"""
import json, sys

runs = [json.load(open(p)) for p in sys.argv[1:]]
S = lambda r: r.get("summary", {})
ROWS = [
    ("model file", lambda r: r["model"]),
    ("skin temperature at start (C)", lambda r: (r["idle"]["skin_c"] or [None])[-1]),
    ("reading the model file, then loading it (s)", lambda r: f"{r.get('file_read_s')} / {round(r['load_s'], 1)}"),
    ("RAM after load / peak at this context / peak over the contexts below (MB)",
     lambda r: f"{r.get('rss_after_load_mb')} / {S(r)['peak_ram_mb']} / {S(r)['peak_ram_mb_sweep_max']}"),
    ("free memory of the phone before loading (MB)", lambda r: r["idle"]["mem_available_mb"]),
    ("lowest free memory during the run / most swap used (MB)", lambda r: f"{S(r).get('mem_available_mb_min')} / {S(r).get('swap_used_mb_max')}"),
    ("llama-server options", lambda r: " ".join(r.get("server_args", []))),
    ("agent prompt with tools (tokens)", lambda r: r["cold_start"]["prompt_n"]),
    ("first token, cold agent prompt (s)", lambda r: round(r["cold_start"]["ttft"], 1)),
    ("first token, warm, median (s)", lambda r: S(r)["speed"]["ttft_s_median"]),
    ("prompt processing (tokens/s)", lambda r: S(r)["speed"]["prompt_tps"]),
    ("generation, mean (tokens/s)", lambda r: S(r)["speed"]["gen_tps"]),
    ("same question at the start, then at the end (tokens/s)", lambda r: [round(x, 2) if isinstance(x, float) else x for x in S(r)["probe_tps_start_end"]]),
    ("CPU of llama-server while busy (% of one core)", lambda r: S(r)["cpu_pct_mean_busy"]),
    ("CPU / skin temperature, max (C)", lambda r: f"{S(r)['cpu_temp_c_max']} / {S(r)['skin_temp_c_max']}"),
    ("thermal status, max (0 none, 1 light, 2 moderate, 3 severe)", lambda r: S(r)["thermal_status_max"]),
    ("big cores while busy, min and max frequency (MHz)", lambda r: S(r)["big_core_mhz_busy_min_max"]),
    ("power taken from the battery, idle then busy (mW, net of USB)", lambda r: f"{S(r)['battery_mw_idle']} -> {S(r)['battery_mw_busy_mean']}"),
    ("battery level, start then end (%)", lambda r: S(r)["battery_pct_start_end"]),
    ("power source", lambda r: " ".join(f"{k}={v}" for k, v in r.get("power_start", []) if k != "level")),
    ("tool calls right / valid JSON among the calls made", lambda r: f"{S(r)['tool_calls_pass']} / {S(r)['tool_calls_valid_json']}"),
    ("Python functions passing their tests", lambda r: S(r)["python_pass"]),
    ("agent tasks done", lambda r: S(r)["agent_tasks_pass"]),
    ("conversation turns answered (of 12)", lambda r: S(r)["convo_turns_ok"]),
    ("context used after 12 turns (tokens)", lambda r: (r.get("convo") or [{}])[-1].get("ctx_tokens")),
    ("Chinese/Japanese characters in French answers", lambda r: sum(x["cjk_chars"] for x in r.get("french", []))),
    ("network during the run", lambda r: r.get("network")),
    ("external connections of Termux / of the phone, max", lambda r: f"{S(r)['termux_external_connections_max']} / {S(r)['all_external_connections_max']}"),
    ("listening sockets of Termux open to the network, max", lambda r: S(r)["termux_open_listen_max"]),
    ("duration (min)", lambda r: S(r)["minutes"]),
    ("requests in error / other errors", lambda r: f"{S(r)['request_errors']} / {S(r).get('errors')}"),
]


def cell(f, r):
    try:
        return str(f(r))
    except (KeyError, TypeError, IndexError):
        return "?"


print("| | " + " | ".join(r["label"] for r in runs) + " |\n|---|" + "---|" * len(runs))
for name, f in ROWS:
    print(f"| {name} | " + " | ".join(cell(f, r) for r in runs) + " |")
print("\n| context | " + " | ".join(f"{r['label']}: load s, peak RAM MB, tokens/s" for r in runs) + " |\n|---|" + "---|" * len(runs))
for i in range(max(len(r.get("ctx_sweep", [])) for r in runs)):
    sw = [(r.get("ctx_sweep") or [])[i] if i < len(r.get("ctx_sweep") or []) else {} for r in runs]
    name = next((f"{x['ctx']} {' '.join(x.get('args', []))}".strip() for x in sw if x), "?")
    print(f"| {name} | " + " | ".join(x.get("error") or f"{x.get('load_s')}, {x.get('peak_ram_mb')}, {round(x.get('gen_tps') or 0, 2)}" for x in sw) + " |")
for r in runs:
    print(f"\n### {r['label']}: what failed")
    for x in r.get("tools", []):
        if not x["pass"]:
            print(f"- tool call, seed {x['seed']}: {x['prompt'][:60]!r} -> {x['tool']} {json.dumps(x['args'], ensure_ascii=False)[:90]}"
                  + (f" | said: {x['text'][:80]!r}" if x.get("text") else "") + (f" | {x['request_error']}" if x.get("request_error") else ""))
    for x in r.get("python", []):
        if not x["pass"]:
            why = x.get("request_error") or (x.get("error") or "").strip().splitlines()[-1:] or "no error text"
            print(f"- python, seed {x['seed']}: {x['task']}: {why if isinstance(why, str) else why[0]}")
    for k, v in (r.get("agent") or {}).items():
        print(f"- agent {k}: {'PASS' if v['pass'] else 'FAIL'} in {len(v['steps'])} steps: " + " > ".join(s["tool"] for s in v["steps"])
              + (f" | {v['error'][:120]}" if v.get("error") else ""))
