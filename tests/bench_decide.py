#!/usr/bin/env python3
"""Apply the decision rule written before any measurement (JOURNAL_AGENTS.md, 12/11; tests/termux-round6.sh header):
the candidate becomes the default model only if it finishes the whole benchmark without error and stays within these
margins of the current default (the baseline):
  tool calls right >= baseline - 3 (of 30), at most 2 tool calls with invalid JSON, Python >= baseline - 2 (of 12),
  agent tasks >= baseline - 1 (of 3), generation speed >= 80 % of the baseline, French answers in French.
Run: python3 tests/bench_decide.py CANDIDATE.json BASELINE.json     (exit 0 = adopt the candidate, 1 = keep the baseline)
A sibling NAME-sweep.json (bench_agent.py --sweep-only, run later for both models) replaces the context sweep of NAME.json.
Self-check: python3 tests/bench_decide.py --test"""
import json, sys
from pathlib import Path


def frac(s):
    n, d = s.split("/")
    return int(n), int(d)


def checks(c, b):
    sc, sb = c["summary"], b["summary"]
    calls = [x for x in c.get("tools", []) if x.get("valid_json") is not None]
    fr = c.get("french", [])
    return [
        ("whole run without error", not sc.get("errors") and sc.get("request_errors") == 0 and sc.get("convo_turns_ok") == 12
         and not any("error" in x for x in c.get("ctx_sweep", [])), f"errors {sc.get('errors')}, request errors {sc.get('request_errors')}, "
         f"conversation {sc.get('convo_turns_ok')}/12, context sweep errors {sum('error' in x for x in c.get('ctx_sweep', []))}"),
        ("tool calls right >= baseline - 3", frac(sc["tool_calls_pass"])[0] >= frac(sb["tool_calls_pass"])[0] - 3,
         f"{sc['tool_calls_pass']} vs {sb['tool_calls_pass']}"),
        ("at most 2 invalid JSON calls", sum(x["valid_json"] is False for x in calls) <= 2, f"{sum(x['valid_json'] is False for x in calls)} invalid of {len(calls)} calls"),
        ("Python >= baseline - 2", frac(sc["python_pass"])[0] >= frac(sb["python_pass"])[0] - 2, f"{sc['python_pass']} vs {sb['python_pass']}"),
        ("agent tasks >= baseline - 1", sc.get("agent_tasks_pass") is not None and sb.get("agent_tasks_pass") is not None
         and frac(sc["agent_tasks_pass"])[0] >= frac(sb["agent_tasks_pass"])[0] - 1, f"{sc.get('agent_tasks_pass')} vs {sb.get('agent_tasks_pass')}"),
        ("generation >= 80 % of baseline", (sc["speed"]["gen_tps"] or 0) >= 0.8 * (sb["speed"]["gen_tps"] or 0),
         f"{sc['speed']['gen_tps']} vs {sb['speed']['gen_tps']} tokens/s"),
        ("French answers in French", len(fr) == 3 and all(x.get("answer") and not x.get("cjk_chars") and "error" not in x for x in fr),
         f"{sum(bool(x.get('answer')) for x in fr)}/3 answered, {sum(x.get('cjk_chars') or 0 for x in fr)} CJK characters"),
    ]


def decide(c, b):
    rows = checks(c, b)
    return all(ok for _, ok, _ in rows), rows


def selftest():
    def run(**kw):
        s = {"errors": None, "request_errors": 0, "convo_turns_ok": 12, "tool_calls_pass": "27/30", "python_pass": "10/12",
             "agent_tasks_pass": "2/3", "speed": {"gen_tps": 5.0}}
        s.update(kw)
        return {"summary": s, "tools": [{"valid_json": True}] * 20, "french": [{"answer": "Bonjour", "cjk_chars": 0}] * 3, "ctx_sweep": [{}]}
    base = run(tool_calls_pass="30/30", python_pass="12/12", agent_tasks_pass="3/3", speed={"gen_tps": 6.0})
    assert decide(run(), base)[0]                                            # every margin exactly reached
    assert not decide(run(tool_calls_pass="26/30"), base)[0]                 # one call too many wrong
    assert not decide(run(speed={"gen_tps": 4.7}), base)[0]                  # below 80 % of 6.0
    assert not decide(run(convo_turns_ok=6), base)[0]                        # killed during the conversation
    bad = run(); bad["tools"] = [{"valid_json": False}] * 3
    assert not decide(bad, base)[0]
    cjk = run(); cjk["french"] = [{"answer": "你好", "cjk_chars": 2}] * 3
    assert not decide(cjk, base)[0]
    print("bench_decide self-check: OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        selftest()
        sys.exit(0)
    cand, base = (json.load(open(p)) for p in sys.argv[1:3])
    for run, path in ((cand, sys.argv[1]), (base, sys.argv[2])):
        later = Path(path[:-5] + "-sweep.json")
        if later.exists():
            run["ctx_sweep"] = json.load(open(later))["ctx_sweep"]
            print(f"context sweep of {run['label']} taken from {later.name}")
    ok, rows = decide(cand, base)
    print(f"candidate {cand['label']} ({cand['model']}) vs baseline {base['label']} ({base['model']})")
    for name, passed, detail in rows:
        print(f"  {'PASS' if passed else 'FAIL'}  {name:34} {detail}")
    print("decision:", "ADOPT the candidate as default" if ok else "KEEP the baseline as default")
    sys.exit(0 if ok else 1)
