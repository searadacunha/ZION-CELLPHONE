#!/usr/bin/env python3
"""Apply the decision rule written before any measurement (JOURNAL_AGENTS.md, 12/11; tests/termux-round6.sh header):
the candidate becomes the default model only if it finishes the whole benchmark without error and stays within these
margins of the current default (the baseline):
  tool calls right >= baseline - 3 (of 30), at most 2 tool calls with invalid JSON, Python >= baseline - 2 (of 12),
  agent tasks >= baseline - 1 (of 3), generation speed >= 80 % of the baseline, French answers in French.
Run: python3 tests/bench_decide.py CANDIDATE.json BASELINE.json     (exit 0 = adopt the candidate, 1 = keep the baseline)
A sibling NAME-sweep.json (bench_agent.py --sweep-only, run later for both models) replaces the context sweep of NAME.json.
Self-check: python3 tests/bench_decide.py --test
--p5 DIR applies the later rule of 12/11 19:56 (JOURNAL_AGENTS.md) to the outputs of tests/termux-chain.sh in DIR
(evalfr-LABEL.json, bench-LABEL-v4.json), with the metrics and the tie-break fixed on 12/11 at 20:17-20:21 UTC, before any
candidate ran. The rule above stays as it was: it made the choice of 12/11 13:05."""
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


P5_BASE = "hauhau-q4km"
P5_CANDIDATES = ["qwen35-q40", "qwen3-2507-q40", "ministral3-q40", "granite4micro-q40"]


def p5_checks(c, b, ec, eb):
    """Rule of 12/11 19:56: candidate c (bench_agent --quick JSON, eval_fr JSON ec) against the default b, eb."""
    sc, sb = c["summary"], b["summary"]
    fc, fb = ec["summary"]["pass_and_french"], eb["summary"]["pass_and_french"]
    gc, gb = sc["speed"]["gen_tps"] or 0, sb["speed"]["gen_tps"] or 0
    pc, pb = (c.get("cold_start") or {}).get("prompt_tps") or 0, (b.get("cold_start") or {}).get("prompt_tps") or 0
    mc, mb = sc.get("peak_ram_mb"), sb.get("peak_ram_mb")
    return [
        ("1 eval_fr right and French >= default + 2", fc >= fb + 2, f"{fc}/24 vs {fb}/24"),
        ("2 tool calls right >= default - 1", frac(sc["tool_calls_pass"])[0] >= frac(sb["tool_calls_pass"])[0] - 1,
         f"{sc['tool_calls_pass']} vs {sb['tool_calls_pass']}"),
        ("2 Python >= default - 1", frac(sc["python_pass"])[0] >= frac(sb["python_pass"])[0] - 1, f"{sc['python_pass']} vs {sb['python_pass']}"),
        ("2 no server error", sc.get("request_errors") == 0 and not c.get("errors"),
         f"request errors {sc.get('request_errors')}, errors {c.get('errors') or None}"),
        ("3 generation >= 90 % of default", gc >= round(0.9 * gb, 6), f"{gc} vs {gb} tokens/s"),  # round: float noise only
        ("3 prompt read (cold start) >= 90 % of default", pc >= round(0.9 * pb, 6), f"{pc} vs {pb} tokens/s"),
        ("4 server peak memory <= default + 300 MB", mc is not None and mb is not None and mc <= mb + 300, f"{mc} vs {mb} MB"),
    ]


def p5_complete(bench, ev):
    """A run the rule can use: every case asked and answered (30 tool calls, 12 Python tasks, 24 French questions)."""
    s = bench.get("summary") or {}
    return (s.get("tool_calls_pass", "").endswith("/30") and s.get("python_pass", "").endswith("/12")
            and (ev.get("summary") or {}).get("n") == 24)


def p5_verdict(rows):
    """ADOPT: every check passes. OPTION: (1) passes, not the rest (seeker-ai --use, not the default). KEEP otherwise."""
    return "ADOPT" if all(ok for _, ok, _ in rows) else "OPTION" if rows[0][1] else "KEEP"


def p5_rank(c, ec):
    """Tie-break when several candidates ADOPT (fixed before any run): French score, then tool calls, then speed."""
    return (ec["summary"]["pass_and_french"], frac(c["summary"]["tool_calls_pass"])[0], c["summary"]["speed"]["gen_tps"] or 0)


def p5(d):
    load = lambda name: json.load(open(d / name)) if (d / name).exists() else None
    b, eb = load(f"bench-{P5_BASE}-v4.json"), load(f"evalfr-{P5_BASE}.json")
    if not (b and eb and p5_complete(b, eb)):
        print(f"default {P5_BASE}: run missing or incomplete, the rule cannot be applied"); return 2
    if b["summary"].get("request_errors") or b.get("errors"):
        print(f"WARNING: the default's own run has errors: {b['summary'].get('request_errors')} {b.get('errors')}")
    adopt = []
    for label in P5_CANDIDATES:
        c, ec = load(f"bench-{label}-v4.json"), load(f"evalfr-{label}.json")
        if not (c and ec and p5_complete(c, ec)):
            print(f"\n{label}: run missing or incomplete: NO DATA"); continue
        rows = p5_checks(c, b, ec, eb); v = p5_verdict(rows)
        print(f"\n{label} ({c['model']}) vs {P5_BASE} ({b['model']}): {v}")
        for name, ok, detail in rows:
            print(f"  {'PASS' if ok else 'FAIL'}  {name:46} {detail}")
        if v == "ADOPT":
            adopt.append((p5_rank(c, ec), label))
    best = max(adopt)[1] if adopt else None
    print("\ndecision:", f"ADOPT {best} as the default model" if best else f"KEEP {P5_BASE} as the default model")
    return 0


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
    # rule of 12/11 19:56 (--p5)
    def p5run(tools="30/30", py="12/12", gen=5.5, prompt=26.0, mem=3600, err=0, fr=18, n=24):
        return ({"summary": {"tool_calls_pass": tools, "python_pass": py, "request_errors": err, "peak_ram_mb": mem,
                             "speed": {"gen_tps": gen}}, "cold_start": {"prompt_tps": prompt}, "errors": {}},
                {"summary": {"pass_and_french": fr, "n": n}})
    b5, eb5 = p5run()
    v = lambda **kw: p5_verdict(p5_checks(*p5run(**kw)[:1], b5, p5run(**kw)[1], eb5))
    assert v(fr=20, tools="29/30", py="11/12", gen=4.95, prompt=23.4, mem=3900) == "ADOPT"   # every margin exactly reached
    assert v(fr=19) == "KEEP"                                                                 # French + 1 only
    assert v(fr=20, gen=4.9) == "OPTION"                                                      # French ok, too slow
    assert v(fr=20, prompt=23.3) == "OPTION" and v(fr=20, mem=3901) == "OPTION" and v(fr=20, err=1) == "OPTION"
    assert v(fr=20, tools="28/30") == "OPTION" and v(fr=20, py="10/12") == "OPTION"
    assert not p5_complete(*p5run(tools="20/24")) and not p5_complete(*p5run(n=23)) and p5_complete(*p5run())
    assert max([(p5_rank(*p5run(fr=21, gen=5.0)), "a"), (p5_rank(*p5run(fr=21, gen=5.2)), "b")])[1] == "b"
    print("bench_decide self-check: OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        selftest()
        sys.exit(0)
    if sys.argv[1:2] == ["--p5"]:
        sys.exit(p5(Path(sys.argv[2])))
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
