#!/usr/bin/env python3
"""Inside Termux (python3 tests/termux-probe-slots.py MODEL.gguf): can OPERATOR's fixed prompt prefix (instructions +
tool schemas, ~1200 tokens, about a minute of prompt processing here) be computed once, saved to disk and restored
after a server restart? Also: what --sleep-idle-seconds frees, and what n-gram / MTP speculation does to tokens/s.
Writes /sdcard/Download/seeker-zero/probe-slots.json as it goes. Network is not used (127.0.0.1 only)."""
import importlib.machinery, importlib.util, json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

MODEL = sys.argv[1]
OUT = Path("/sdcard/Download/seeker-zero/probe-slots.json")
PORT, SLOTS = 8092, Path.home() / ".cache/zion-probe-slots"
URL = f"http://127.0.0.1:{PORT}"
ldr = importlib.machinery.SourceFileLoader("sa", shutil.which("seeker-ai"))
SA = importlib.util.module_from_spec(importlib.util.spec_from_loader("sa", ldr)); ldr.exec_module(SA)
CONF = SA.load_conf()
SERVER = str(Path(CONF["llama_server"]).expanduser()) if "/" in CONF["llama_server"] else CONF["llama_server"]
SYSTEM = SA.system_text(CONF, True)
TOOLS = SA.tool_specs(CONF, SA.make_tools(CONF))
R = {"model": Path(MODEL).name, "started": time.strftime("%F %T")}


def save():
    OUT.write_text(json.dumps(R, indent=1, ensure_ascii=False))


def post(path, body, timeout=900):
    req = urllib.request.Request(URL + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read() or b"{}")
    return out, round(time.time() - t0, 2)


def rss_mb(p):
    try:
        return int(next(l for l in open(f"/proc/{p.pid}/status") if l.startswith("VmRSS")).split()[1]) // 1024
    except (OSError, StopIteration):
        return None


def start(*extra):
    subprocess.run(["seeker-ai", "--stop"], capture_output=True)
    SLOTS.mkdir(parents=True, exist_ok=True)
    log = open(Path.home() / f".cache/zion-probe-{int(time.time())}.log", "w")
    p = subprocess.Popen([SERVER, "-m", MODEL, "-c", "4096", "-t", "4", "--jinja", "--host", "127.0.0.1", "--port", str(PORT),
                          "--metrics", "--cache-ram", "0", "--load-mode", "none", "--slot-save-path", str(SLOTS), *extra],
                         stdout=log, stderr=subprocess.STDOUT)
    t0 = time.time()
    while time.time() - t0 < 300:
        try:
            urllib.request.urlopen(URL + "/health", timeout=2).read()
            return p, round(time.time() - t0, 1), log.name
        except OSError:
            if p.poll() is not None:
                return None, None, log.name
            time.sleep(1)
    p.kill()
    return None, None, log.name


def stop(p):
    if p and p.poll() is None:
        p.terminate(); p.wait(30)


def ask(text, max_tokens=8):
    body = {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}], "tools": TOOLS,
            "max_tokens": max_tokens, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    out, wall = post("/v1/chat/completions", body)
    t = out.get("timings", {})
    return {"wall_s": wall, "prompt_n": t.get("prompt_n"), "cache_n": t.get("cache_n"), "prompt_ms": t.get("prompt_ms"),
            "predicted_per_second": t.get("predicted_per_second")}


def step(name, fn):
    try:
        R[name] = fn()
    except Exception as e:  # keep going: each part answers its own question
        R[name] = {"error": f"{type(e).__name__}: {e}"}
    print(name, json.dumps(R[name], ensure_ascii=False)[:300], flush=True)
    save()


# 1. cold: what a first message costs today, after a server (re)start
p, load_s, log = start()
R["load_s"] = load_s
step("cold_first_message", lambda: ask("Bonjour, réponds juste OK."))
step("warm_second_message", lambda: ask("Salut, réponds juste OK."))

# 2. the prefix alone: rendered by the server's own template, computed once, saved
def make_prefix():
    tpl, _ = post("/apply-template", {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "QQQZION"}],
                                      "tools": TOOLS, "chat_template_kwargs": {"enable_thinking": False}})
    prompt = tpl["prompt"]
    return prompt[:prompt.index("QQQZION")]
stop(p)
p, _, _ = start()
PREFIX = None
def warm():
    global PREFIX
    PREFIX = make_prefix()
    out, wall = post("/completion", {"prompt": PREFIX, "n_predict": 0, "cache_prompt": True})
    sv, sv_wall = post("/slots/0?action=save", {"filename": "prefix.bin"})
    return {"prefix_chars": len(PREFIX), "prefix_tail": PREFIX[-40:], "compute_wall_s": wall, "tokens": (out.get("timings") or {}).get("prompt_n"),
            "save": sv, "save_wall_s": sv_wall, "file_mb": round((SLOTS / "prefix.bin").stat().st_size / 1e6, 1)}
step("prefix_warmup_and_save", warm)
step("first_message_after_warmup_same_server", lambda: ask("Bonjour, réponds juste OK."))

# 3. restart, restore, first message
stop(p)
p, _, _ = start()
step("restore", lambda: dict(zip(("result", "wall_s"), post("/slots/0?action=restore", {"filename": "prefix.bin"}))))
step("first_message_after_restore", lambda: ask("Bonjour, réponds juste OK."))
step("second_message_after_restore", lambda: ask("Et maintenant, réponds juste NON."))

# 4. generation speed with and without speculation (same prompt, 128 tokens, temperature 0)
def gen(label):
    body = {"messages": [{"role": "user", "content": "Écris une fonction Python qui renvoie la liste des nombres premiers jusqu'à n, avec un exemple d'appel."}],
            "max_tokens": 128, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    out, wall = post("/v1/chat/completions", body)
    t = out.get("timings", {})
    return {"label": label, "predicted_n": t.get("predicted_n"), "predicted_per_second": t.get("predicted_per_second"),
            "draft_n": t.get("draft_n"), "draft_n_accepted": t.get("draft_n_accepted"), "wall_s": wall}
step("gen_baseline", lambda: gen("baseline"))
for spec in ("ngram-mod", "draft-mtp"):
    stop(p)
    p, load, log = start("--spec-type", spec)
    if p is None:
        R[f"gen_{spec}"] = {"error": "server did not start", "log_tail": open(log).read()[-600:]}
        save(); print(spec, "did not start", flush=True)
        continue
    step(f"gen_{spec}", lambda: gen(spec))

# 5. sleeping after idle: memory freed? next request?
stop(p)
p, _, _ = start("--sleep-idle-seconds", "20")
R["sleep_rss_before_mb"] = rss_mb(p)
ask("Bonjour, réponds juste OK.")
time.sleep(35)
R["sleep_rss_after_idle_mb"] = rss_mb(p)
step("first_message_after_sleep", lambda: ask("Bonjour, réponds juste OK."))
R["sleep_rss_after_wake_mb"] = rss_mb(p)
stop(p)
shutil.rmtree(SLOTS, ignore_errors=True)
R["done"] = time.strftime("%F %T")
save()
print("done", flush=True)
