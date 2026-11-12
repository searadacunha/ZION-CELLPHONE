#!/usr/bin/env python3
"""On the Seeker, in Termux: benchmark a GGUF model as seeker-ai's engine. Run it OFFLINE (Wi-Fi off).
Measures load time, time to first token, tokens/s (and the same probe question at the start and at the end, to see
thermal throttling), peak RAM, CPU use, temperatures, thermal status, big-core frequency, battery power, network
connections of Termux during inference (must be 0), tool-call reliability (real agent prompt and tool schemas, calls
NOT executed), multi-step agent tasks confined to ~/seeker-work/bench (script, bug fix, git commit), Python correctness
(unit tests), French answers, a 12-turn conversation, and optionally 2048/4096/8192 contexts.
Usage: python bench_agent.py MODEL.gguf --label NAME [--ctx 4096] [--server BINARY] [--quick] [--sweep]
Writes /sdcard/Download/seeker-zero/bench-NAME.json after every part (samples and summary included) and prints a report.
Dry run on the Mac, no phone, no model: bash tests/test_bench_dry.sh"""
import argparse, http.client, importlib.machinery, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, threading
import time, urllib.error, urllib.request
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("model"); ap.add_argument("--label", required=True); ap.add_argument("--ctx", type=int, default=4096)
ap.add_argument("--server", help="llama-server binary (default: the one in seeker-ai's config)")
ap.add_argument("--quick", action="store_true"); ap.add_argument("--sweep", action="store_true")
ap.add_argument("--sweep-only", action="store_true", help="only the context sweep, into bench-NAME-sweep.json")
A = ap.parse_args()
PORT, HOME = 8091, Path.home()
URL = f"http://127.0.0.1:{PORT}"
OUT = Path(os.environ.get("BENCH_OUT_DIR", "/sdcard/Download/seeker-zero")) / f"bench-{A.label}{'-sweep' if A.sweep_only else ''}.json"
BENCH = HOME / "seeker-work" / "bench"
RISH = shutil.which("rish") or str(HOME / "bin/rish")
SAMPLING = {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0}
SEEDS = (1, 2)  # tool-call and Python cases run once per seed: same draws for every model
NETERR = (OSError, ValueError, http.client.HTTPException)  # HTTP error, lost connection, broken or error chunk
TCK = os.sysconf("SC_CLK_TCK")
PERIOD = float(os.environ.get("BENCH_SAMPLE_S", 10))  # seconds between samples (the Mac dry run uses 1)
T0 = time.time()

ldr = importlib.machinery.SourceFileLoader("sa", shutil.which("seeker-ai"))
SA = importlib.util.module_from_spec(importlib.util.spec_from_loader("sa", ldr)); ldr.exec_module(SA)
CONF = SA.load_conf()
SPECS = SA.tool_specs(CONF, SA.make_tools(CONF))
SERVER = A.server or CONF["llama_server"]
SERVER = str(Path(SERVER).expanduser()) if "/" in SERVER else SERVER
R = {"label": A.label, "model": Path(A.model).name, "ctx": A.ctx, "server": SERVER, "threads": CONF["threads"], "server_args": CONF["server_args"],
     "started": time.strftime("%F %T"), "errors": {}}
TIMELINE = []  # [seconds since start, generation tok/s, generated tokens] of every request, in order


def sh(argv, timeout=30, cwd=None, env=None):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(argv, 124, "", str(e))


def rish(cmd):
    """Output of an Android shell command run as uid 2000 through Shizuku. rish spreads what the command prints
    between its stdout and its stderr, at random (measured on the Seeker, 12/11): the two are read as one stream.
    It sometimes fails with "Request timeout": one retry."""
    for _ in range(2):
        try:
            r = subprocess.run([RISH, "-c", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30,
                               stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if r.returncode == 0:
            return r.stdout
    return ""


def proc_status(pid):
    try:
        return {k: int(v) // 1024 for k, v in re.findall(r"(VmRSS|VmHWM):\s+(\d+)", Path(f"/proc/{pid}/status").read_text())}
    except OSError:
        return {}


def meminfo():
    try:
        return {k: int(v) // 1024 for k, v in re.findall(r"^(\w+):\s+(\d+) kB", Path("/proc/meminfo").read_text(), re.M)}
    except OSError:
        return {}


def mem_available_mb():
    return meminfo().get("MemAvailable")


def power():  # is the phone on a charger? the battery figures only mean "net of the charger" when it is
    return re.findall(r"(AC powered|USB powered|Wireless powered|level|Max charging current): (\S+)", rish("dumpsys battery"))


def errtext(e):
    body = e.read().decode(errors="replace")[:200] if isinstance(e, urllib.error.HTTPError) else ""
    return f"{type(e).__name__}: {e} {body}".strip()


def save():
    OUT.write_text(json.dumps(R, indent=1, ensure_ascii=False))


def stop(p):
    p.terminate()
    try:
        p.wait(30)
    except subprocess.TimeoutExpired:
        p.kill(); p.wait()


# ---- background sampler: one Shizuku call every 10 s (each call starts a JVM: more would disturb the measure) ----
PROBE = ("dumpsys thermalservice; echo @@; cat /sys/devices/system/cpu/cpu[4-7]/cpufreq/scaling_cur_freq; echo @@; "
         "cd /sys/class/power_supply/battery && cat current_now voltage_now charge_counter capacity; echo @@; "
         "cat /proc/net/tcp /proc/net/tcp6")
LOOPBACK = ("0100007F", "00000000000000000000000001000000", "0000000000000000FFFF00000100007F")


def parse_probe(out, uid):
    """Text of PROBE -> one sample. Battery: current_now is negative while discharging on this phone, so battery_mw is
    what the battery gives (positive) or receives (negative), net of the charger when the phone is plugged."""
    th, freq, bat, net = (out.split("@@\n") + ["", "", ""])[:4]
    live = th.split("Current temperatures from HAL:")[-1].split("Current cooling devices")[0]  # not the stale cached block
    temps = {name: float(v) for v, name in re.findall(r"mValue=([\d.]+), mType=\d+, mName=(\w+)", live)}
    status = re.search(r"Thermal Status: (\d)", th)
    mhz = [int(x) // 1000 for x in freq.split() if x.isdigit()]
    b = [int(x) for x in bat.split() if x.lstrip("-").isdigit()]
    rows = [l.split() for l in net.splitlines() if len(l.split()) > 8 and l.split()[0].endswith(":")]
    ext = [f for f in rows if f[3] == "01" and not f[2].startswith(LOOPBACK)]
    return {"cpu_c": temps.get("CPU"), "skin_c": temps.get("SKIN"), "battery_c": temps.get("BATTERY"),
            "thermal_status": int(status.group(1)) if status else None, "big_mhz": max(mhz) if mhz else None,
            "battery_mw": round(-b[0] * b[1] / 1e9) if len(b) >= 2 else None,
            "charge_uah": b[2] if len(b) == 4 else None, "battery_pct": b[3] if len(b) == 4 else None,
            "all_ext_conn": len(ext) if rows else None,
            "termux_ext_conn": sum(f[7] == str(uid) for f in ext) if rows else None,
            # a server reachable from the network would show here: a listening socket of Termux not bound to loopback
            "termux_open_listen": sum(f[3] == "0A" and f[7] == str(uid) and not f[1].startswith(LOOPBACK) for f in rows) if rows else None}


class Sampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.pid, self.stop_flag, self.s = None, False, {"t": [], "cpu_pct": []}

    def ticks(self):  # CPU time used so far by llama-server (utime + stime, fields 14 and 15 of /proc/PID/stat)
        try:
            f = Path(f"/proc/{self.pid}/stat").read_text().rsplit(")", 1)[1].split()
            return int(f[11]) + int(f[12])
        except (OSError, IndexError, ValueError):
            return None

    def run(self):
        last, n = None, 0
        while not self.stop_flag:
            now, ticks = time.time(), self.ticks()
            known = last and ticks is not None and last[1] is not None and ticks >= last[1]
            self.s["cpu_pct"].append(round((ticks - last[1]) / TCK / (now - last[0]) * 100) if known else None)  # same length as t
            last = (now, ticks)
            self.s["t"].append(round(now - T0))
            m = meminfo()  # read by Termux itself, every sample: what Android's low-memory killer looks at
            for k, v in (("mem_available_mb", m.get("MemAvailable")), ("swap_used_mb", m["SwapTotal"] - m["SwapFree"] if "SwapFree" in m else None),
                         ("server_rss_mb", proc_status(self.pid).get("VmRSS") if self.pid else None)):
                self.s.setdefault(k, []).append(v)
            # each rish call starts a Java VM and the Shizuku app (about 0.8 s, and memory): one call every 30 s
            probe = parse_probe(rish(PROBE), os.getuid()) if n % 3 == 0 else parse_probe("", os.getuid())
            for k, v in probe.items():
                self.s.setdefault(k, []).append(v)
            n += 1
            time.sleep(PERIOD)

    def seen(self, key, idx=None):
        v = self.s.get(key, [])
        return [v[i] for i in (range(len(v)) if idx is None else idx) if i < len(v) and v[i] is not None]


def start_server(ctx, extra=None):
    sh(["seeker-ai", "--stop"], 60)
    log = Path(tempfile.gettempdir()) / f"bench-{A.label}-{ctx}.log"
    t0 = time.time()
    p = subprocess.Popen([SERVER, "-m", A.model, "-c", str(ctx), "-t", str(CONF["threads"]), "--jinja", "--host", "127.0.0.1",
                          "--port", str(PORT), "--metrics", *(CONF["server_args"] if extra is None else extra)],
                         stdout=open(log, "w"), stderr=subprocess.STDOUT)
    for _ in range(600):
        try:
            urllib.request.urlopen(URL + "/health", timeout=2).read()
            return p, time.time() - t0, log
        except OSError:
            if p.poll() is not None:
                raise RuntimeError(f"llama-server exited ({p.returncode}), see {log}")
            time.sleep(1)
    p.kill()
    raise RuntimeError("llama-server did not start in 10 min")


def chat(messages, tools=None, max_tokens=256, seed=1):
    body = {"messages": messages, "stream": True, "max_tokens": max_tokens, "seed": seed,
            "chat_template_kwargs": {"enable_thinking": False}, **SAMPLING}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(URL + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0, ttft, text, calls, timings = time.time(), None, "", {}, {}
    with urllib.request.urlopen(req, timeout=1800) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            ch = json.loads(line[6:])
            if ch.get("error"):
                raise ValueError(f"server error event: {json.dumps(ch['error'])[:200]}")
            timings = ch.get("timings") or timings
            d = (ch.get("choices") or [{}])[0].get("delta") or {}
            if ttft is None and (d.get("content") or d.get("tool_calls")):
                ttft = time.time() - t0
            text += d.get("content") or ""
            for tc in d.get("tool_calls") or []:
                c = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                f = tc.get("function") or {}
                c["id"] = tc.get("id") or c["id"]; c["name"] += f.get("name") or ""; c["args"] += f.get("arguments") or ""
    if timings.get("predicted_per_second"):
        TIMELINE.append([round(time.time() - T0), round(timings["predicted_per_second"], 2), timings.get("predicted_n")])
    return {"text": text, "calls": [calls[i] for i in sorted(calls)], "ttft": ttft, "wall": time.time() - t0,
            "gen_tps": timings.get("predicted_per_second"), "prompt_tps": timings.get("prompt_per_second"),
            "prompt_n": timings.get("prompt_n"), "gen_n": timings.get("predicted_n"),
            "ctx_tokens": sum(timings.get(k) or 0 for k in ("cache_n", "prompt_n", "predicted_n")) or None}


KEYS = ("ttft", "gen_tps", "prompt_tps", "prompt_n", "gen_n")
PROBE_Q = "Donne trois conseils pour économiser la batterie d'un téléphone."


def probe_tps():  # the same short question, no tools, 64 tokens: speeds that can be compared across time and models
    try:
        return chat([{"role": "user", "content": PROBE_Q}], None, 64)["gen_tps"]
    except NETERR as e:
        return errtext(e)


def speed(rows):
    g = [r["gen_tps"] for r in rows if r.get("gen_tps")]
    p = [r["prompt_tps"] for r in rows if r.get("prompt_tps") and (r.get("prompt_n") or 0) >= 16]
    t = [r["ttft"] for r in rows if r.get("ttft")]
    return {"gen_tps": round(sum(g) / len(g), 2) if g else None, "prompt_tps": round(sum(p) / len(p), 2) if p else None,
            "ttft_s_median": round(sorted(t)[len(t) // 2], 2) if t else None, "n": len(rows)}


# ---- tool-call reliability: first call only, never executed. A case accepts every call that really does the job ----
has = lambda a, k, *words: all(w in a.get(k, "").lower() for w in words)
CASES = [
    ("Quel est le niveau de batterie du téléphone ?",
     lambda n, a, t: (n == "android" and a.get("action") == "battery") or (n in ("shell", "system") and has(a, "command", "batter"))),
    ("Liste les fichiers du dossier ~/seeker-work.",
     lambda n, a, t: (n == "list_dir" and (has(a, "path", "seeker-work") or a.get("path") in (".", "./"))) or (n == "shell" and has(a, "command", "ls"))),
    ("Lis le fichier ~/seeker-work/notes.txt.",
     lambda n, a, t: (n == "read_file" and has(a, "path", "notes.txt")) or (n == "shell" and has(a, "command", "notes.txt"))),
    ("Crée le fichier ~/seeker-work/hello.py qui affiche Bonjour.",
     lambda n, a, t: n == "write_file" and has(a, "path", "hello.py") and has(a, "content", "print")),
    ("Exécute la commande git --version.", lambda n, a, t: n == "shell" and has(a, "command", "git", "version")),
    ("Calcule 2 puissance 100 en exécutant du Python.",
     lambda n, a, t: (n == "python" and has(a, "code", "100")) or (n == "shell" and has(a, "command", "python", "100"))),
    ("Retiens que je préfère les réponses courtes.",
     lambda n, a, t: n == "remember" and re.search("court|brèv|bref|concis|short", a.get("note", "").lower())),
    ("Envoie une notification sur le téléphone qui dit : test.",
     lambda n, a, t: n == "android" and a.get("action") == "notify" and "test" in (a.get("text", "") + a.get("title", "")).lower()),
    ("À quel réseau Wi-Fi le téléphone est-il connecté ?",
     lambda n, a, t: (n == "android" and a.get("action") == "wifi_info") or (n == "system" and has(a, "command", "wifi"))),
    ("Quelle est la version d'Android ? Utilise getprop avec l'outil system.", lambda n, a, t: n == "system" and has(a, "command", "getprop")),
    ("Quels périphériques USB sont branchés ?",
     lambda n, a, t: (n == "android" and a.get("action") == "usb_devices") or (n in ("shell", "system") and has(a, "command", "usb"))),
    ("Liste les applications installées par l'utilisateur.",
     lambda n, a, t: (n == "android" and a.get("action") == "apps") or (n == "system" and has(a, "command", "pm list"))),
    ("Télécharge la page https://example.com et donne son titre.",
     lambda n, a, t: (n == "fetch_url" and has(a, "url", "example.com")) or (n == "shell" and has(a, "command", "example.com"))),
    ("Quelle est la capitale de l'Italie ?", lambda n, a, t: n is None and "rom" in t.lower()),  # no tool, and a real answer
    ("Écris une fonction Python qui additionne deux nombres. Montre seulement le code.",
     lambda n, a, t: (n is None and "def " in t) or (n == "write_file" and has(a, "content", "def "))),
]


def bench_tools(system):
    out = []
    for seed in SEEDS:
        for prompt, ok in CASES:
            row = {"prompt": prompt, "seed": seed, "tool": None, "args": {}, "valid_json": None, "pass": False}
            out.append(row)
            try:
                r = chat([{"role": "system", "content": system}, {"role": "user", "content": prompt}], SPECS, 200, seed)
            except NETERR as e:
                row["request_error"] = errtext(e)
                print(f"  tool ERROR {prompt[:55]:55} {row['request_error'][:70]}", flush=True)
                continue
            args = {}
            if r["calls"]:
                row["tool"] = r["calls"][0]["name"]
                try:
                    args = json.loads(r["calls"][0]["args"] or "{}")
                    row["valid_json"] = isinstance(args, dict)
                except ValueError:
                    row["valid_json"] = False
            usable = args if row["valid_json"] else {}
            row.update(args=args if row["valid_json"] is not False else r["calls"][0]["args"], text=r["text"][:200],
                       **{k: r[k] for k in KEYS})
            row["pass"] = row["valid_json"] is not False and bool(ok(row["tool"], {k: v for k, v in usable.items() if isinstance(v, str)}, r["text"]))
            print(f"  tool {'PASS' if row['pass'] else 'FAIL'}  {prompt[:55]:55} -> {row['tool']} {json.dumps(args, ensure_ascii=False)[:70]}", flush=True)
    return out


# ---- multi-step agent tasks, executed for real but confined to BENCH ----
SAFE_SEG = re.compile(r"^(python3?|git|ls|cat|cd)\b")
FORBIDDEN = re.compile(r"[|><`]|\$\(|\b(push|pull|clone|fetch|remote|submodule|curl|wget|rm|sudo|chmod|rish)\b")
# git: a fixed identity (Termux has none: without it the task would measure something else), the phone's own
# ~/.gitconfig never read nor written, and no repository above BENCH taken for the one to create
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": str(Path(tempfile.gettempdir()) / "bench-gitconfig"), "GIT_TERMINAL_PROMPT": "0",
       "GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "bench@localhost", "GIT_COMMITTER_NAME": "bench",
       "GIT_COMMITTER_EMAIL": "bench@localhost", "GIT_EDITOR": "true", "GIT_CEILING_DIRECTORIES": str(BENCH.parent)}
HERE = " Ton dossier courant est ~/seeker-work/bench."


def confined_tool(name, args):
    try:
        if name == "write_file":
            p = Path(args.get("path", "")).expanduser()
            p = (BENCH / p) if not p.is_absolute() else p
            if BENCH.resolve() not in p.resolve().parents:
                return "denied (benchmark): outside ~/seeker-work/bench"
            p.parent.mkdir(parents=True, exist_ok=True); p.write_text(args.get("content", ""))
            return f"wrote {p}"
        if name in ("read_file", "list_dir"):
            p = Path(args.get("path", "")).expanduser()
            p = (BENCH / p) if not p.is_absolute() else p
            if not (p.resolve() == BENCH.resolve() or BENCH.resolve() in p.resolve().parents):
                return "denied (benchmark): outside ~/seeker-work/bench"
            return "\n".join(x.name for x in p.iterdir()) if name == "list_dir" else p.read_text()
        if name == "shell":
            cmd = args.get("command", "")
            segs = [s for s in re.split(r"\s*(?:&&|;)\s*", cmd) if s]
            if not segs or FORBIDDEN.search(cmd) or not all(SAFE_SEG.match(s) for s in segs):
                return "denied (benchmark): only python, git (local), ls, cat, cd in ~/seeker-work/bench"
            r = sh(["bash", "-c", cmd], 30, cwd=BENCH, env=ENV)
            return f"exit {r.returncode}\n{r.stdout}{r.stderr}"[:3000]
        if name == "python":
            r = sh([sys.executable, "-c", args.get("code", "")], 20, cwd=BENCH, env=ENV)
            return f"exit {r.returncode}\n{r.stdout}{r.stderr}"[:3000]
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"
    return "denied (benchmark): tool not allowed here"


def agent_task(system, prompt, rounds=8):
    msgs, steps, rows = [{"role": "system", "content": system}, {"role": "user", "content": prompt + HERE}], [], []
    for _ in range(rounds):
        try:
            r = chat(msgs, SPECS, 400)
        except NETERR as e:  # e.g. the context is full: the task ends here, what was done stays
            return {"answer": "", "error": errtext(e), "steps": steps, "speed": speed(rows)}
        rows.append(r)
        msg = {"role": "assistant", "content": r["text"]}
        if r["calls"]:
            msg["tool_calls"] = [{"id": c["id"] or f"c{i}", "type": "function", "function": {"name": c["name"], "arguments": c["args"] or "{}"}}
                                 for i, c in enumerate(r["calls"])]
        msgs.append(msg)
        if not r["calls"]:
            return {"answer": r["text"], "steps": steps, "speed": speed(rows)}
        for tc in msg["tool_calls"]:
            try:
                args = json.loads(tc["function"]["arguments"])
            except ValueError:
                args = None
            res = confined_tool(tc["function"]["name"], args) if isinstance(args, dict) else "error: arguments are not valid JSON"
            steps.append({"tool": tc["function"]["name"], "args": args, "result": res[:300]})
            print(f"    step {tc['function']['name']} {json.dumps(args, ensure_ascii=False)[:80]} -> {res[:60]!r}", flush=True)
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": res})
    return {"answer": "(no final answer after %d rounds)" % rounds, "steps": steps, "speed": speed(rows)}


def bench_agent(system):
    if BENCH.exists():
        shutil.rmtree(BENCH)
    BENCH.mkdir(parents=True)
    Path(ENV["GIT_CONFIG_GLOBAL"]).write_text("")
    res = {}
    t = agent_task(system, "Dans ~/seeker-work/bench, crée un script fib.py qui affiche les 10 premiers nombres de Fibonacci "
                           "(0 1 1 2 3 5 8 13 21 34) séparés par des espaces, exécute-le avec python, puis donne-moi le résultat.")
    run = sh([sys.executable, "fib.py"], 20, cwd=BENCH) if (BENCH / "fib.py").exists() else None
    t["pass"] = bool(run and run.returncode == 0 and run.stdout.split() == "0 1 1 2 3 5 8 13 21 34".split())
    res["write_and_run"] = t
    (BENCH / "moyenne.py").write_text("def moyenne(l):\n    return sum(l) / len(l)\n\nprint(moyenne([]))\n")
    t = agent_task(system, "Le script ~/seeker-work/bench/moyenne.py plante. Exécute-le, lis l'erreur, corrige-le pour "
                           "qu'il affiche 0 pour une liste vide, puis réexécute-le pour vérifier.")
    run = sh([sys.executable, "moyenne.py"], 20, cwd=BENCH)
    t["pass"] = run.returncode == 0 and run.stdout.strip() in ("0", "0.0")
    res["fix_bug"] = t
    if not (BENCH / "fib.py").exists():  # the git task must not depend on the first one
        (BENCH / "fib.py").write_text("print('0 1 1 2 3 5 8 13 21 34')\n")
    t = agent_task(system, "Initialise un dépôt git dans ~/seeker-work/bench, puis fais un commit de fib.py avec le message fib.")
    log = sh(["git", "log", "--oneline"], 20, cwd=BENCH, env=ENV)
    t["pass"] = (BENCH / ".git").is_dir() and log.returncode == 0 and "fib" in log.stdout
    res["git_commit"] = t
    for k, v in res.items():
        print(f"  agent {k}: {'PASS' if v['pass'] else 'FAIL'} in {len(v['steps'])} steps" + (f" ({v['error'][:60]})" if v.get("error") else ""), flush=True)
    return res


# ---- Python correctness (no tools), checked by unit tests ----
PY = [
    ("est_palindrome(s) qui renvoie True si la chaîne est un palindrome en ignorant la casse, les espaces et la ponctuation",
     "assert est_palindrome('Esope reste ici et se repose') is True\nassert est_palindrome('A man, a plan, a canal: Panama') is True\nassert est_palindrome('abc') is False"),
    ("fizzbuzz(n) qui renvoie la liste des chaînes de 1 à n : 'Fizz' pour les multiples de 3, 'Buzz' pour 5, 'FizzBuzz' pour 15, sinon le nombre en chaîne",
     "r = fizzbuzz(15)\nassert len(r) == 15 and r[0] == '1' and r[2] == 'Fizz' and r[4] == 'Buzz' and r[14] == 'FizzBuzz'"),
    ("compte_mots(texte) qui renvoie un dictionnaire mot -> nombre d'occurrences, insensible à la casse et sans la ponctuation",
     "assert compte_mots('Le chat, le chien.') == {'le': 2, 'chat': 1, 'chien': 1}"),
    ("fusionne(a, b) qui fusionne deux listes d'entiers déjà triées en une liste triée, sans utiliser sort ni sorted",
     "assert fusionne([1, 4, 9], [2, 3, 10]) == [1, 2, 3, 4, 9, 10]\nassert fusionne([], [1]) == [1]"),
    ("premiers(n) qui renvoie la liste des nombres premiers inférieurs ou égaux à n",
     "assert premiers(20) == [2, 3, 5, 7, 11, 13, 17, 19]\nassert premiers(1) == []"),
    ("moyenne_mobile(valeurs, k) qui renvoie la liste des moyennes des fenêtres glissantes de taille k",
     "assert moyenne_mobile([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]\nassert moyenne_mobile([5], 1) == [5]"),
]


def bench_python():
    out = []
    for seed in SEEDS:
        for spec, tests in PY:
            row = {"task": spec.split("(")[0], "seed": seed, "pass": False}
            out.append(row)
            try:
                r = chat([{"role": "system", "content": SA.SYSTEM_CHAT},
                          {"role": "user", "content": f"Écris en Python une fonction {spec}. Réponds seulement avec le code dans un bloc ```python."}],
                         None, 400, seed)
            except NETERR as e:
                row["request_error"] = errtext(e)
                print(f"  python ERROR {row['task']} {row['request_error'][:70]}", flush=True)
                continue
            m = re.search(r"```[\w+-]*[ \t]*\n(.*?)(?:```|\Z)", r["text"], re.S)  # ```python, ```py, ```Python, fence left open
            code = m.group(1) if m else r["text"]
            d = Path(tempfile.mkdtemp())
            (d / "sol.py").write_text(code)
            (d / "t.py").write_text("from sol import *\n" + tests + "\nprint('OK')\n")
            t = sh([sys.executable, "t.py"], 15, cwd=d)
            row.update({"pass": t.returncode == 0 and "OK" in t.stdout, "error": (t.stderr or "")[-200:], "code": code[:1500], **{k: r[k] for k in KEYS}})
            print(f"  python {'PASS' if row['pass'] else 'FAIL'}  {row['task']}", flush=True)
    return out


FR = ["Explique en trois phrases ce qu'est une clé privée et pourquoi il ne faut jamais la partager.",
      "Rédige un court e-mail professionnel pour décaler un rendez-vous de mardi à jeudi.",
      "Résume en deux phrases les avantages et les inconvénients d'un téléphone sans services Google."]
CONVO = ["Je prépare un voyage de 3 jours à Lisbonne. Propose un programme pour le jour 1, en 4 lignes.", "Et le jour 2 ?",
         "Et le jour 3 ?", "Quels quartiers éviter le soir ?", "Donne un budget approximatif.",
         "Comment aller de l'aéroport au centre ?", "Quelles spécialités culinaires goûter ?",
         "Résume tout le programme en 5 lignes.", "Traduis ce résumé en anglais.",
         "Rappelle-moi le programme du jour 2.", "Combien de jours dure mon voyage ?", "Fais une liste courte de choses à emporter."]


def bench_french():
    out = []
    for q in FR:
        try:
            r = chat([{"role": "system", "content": SA.SYSTEM_CHAT}, {"role": "user", "content": q}], None, 300)
        except NETERR as e:
            out.append({"prompt": q, "answer": "", "cjk_chars": 0, "error": errtext(e)})
            continue
        out.append({"prompt": q, "answer": r["text"], "cjk_chars": len(re.findall(r"[぀-ヿ一-鿿]", r["text"])),
                    **{k: r[k] for k in KEYS}})
        print(f"  french {len(r['text'])} chars, {r['gen_tps'] or 0:.1f} tok/s: {r['text'][:90]!r}", flush=True)
    return out


def bench_convo():
    msgs, turns = [{"role": "system", "content": SA.SYSTEM_CHAT}], []
    for i, q in enumerate(CONVO, 1):
        msgs.append({"role": "user", "content": q})
        try:
            r = chat(msgs, None, 200)
        except NETERR as e:
            turns.append({"turn": i, "error": errtext(e)})
            print(f"  convo turn {i}: ERROR {turns[-1]['error'][:80]}", flush=True)
            break
        msgs.append({"role": "assistant", "content": r["text"]})
        turns.append({"turn": i, "answer": r["text"], "ctx_tokens": r["ctx_tokens"], **{k: r[k] for k in KEYS}})
        print(f"  convo turn {i}: {r['gen_tps'] or 0:.1f} tok/s, first token {r['ttft'] or 0:.1f}s, context {r['ctx_tokens']}", flush=True)
    return turns


def summary(samp, idle_n):
    s = samp.s
    mean = lambda v: round(sum(v) / len(v), 1) if v else None
    # busy = llama-server uses more than 3 cores (an unknown value, right after a restart, is kept)
    busy = [i for i in range(idle_n, len(s["cpu_pct"])) if s["cpu_pct"][i] is None or s["cpu_pct"][i] > 300]
    rows = [x for k in ("tools", "python", "french") for x in R.get(k, [])] + [x for x in R.get("convo", []) if "gen_tps" in x]
    called = [x for x in R.get("tools", []) if x["valid_json"] is not None]
    pct = samp.seen("battery_pct")
    return {
        "speed": speed(rows),
        "probe_tps_start_end": R.get("probe_tps"),  # same question at the start and at the end: a drop = thermal throttling
        "tool_calls_pass": f"{sum(x['pass'] for x in R.get('tools', []))}/{len(R.get('tools', []))}",
        "tool_calls_valid_json": f"{sum(x['valid_json'] for x in called)}/{len(called)}",  # among the answers that call a tool
        "python_pass": f"{sum(x['pass'] for x in R.get('python', []))}/{len(R.get('python', []))}",
        "agent_tasks_pass": f"{sum(v['pass'] for v in R.get('agent', {}).values())}/{len(R.get('agent', {}))}" if R.get("agent") else None,
        "convo_turns_ok": len([t for t in R.get("convo", []) if "error" not in t]),
        "request_errors": sum("request_error" in x for k in ("tools", "python") for x in R.get(k, []))
                          + sum("error" in x for x in list(R.get("agent", {}).values()) + R.get("french", []) + R.get("convo", [])),
        "peak_ram_mb": R.get("peak_ram_mb"),
        "peak_ram_mb_sweep_max": max([x.get("peak_ram_mb") or 0 for x in R.get("ctx_sweep", [])], default=None),
        "cpu_pct_mean_busy": mean([c for c in samp.seen("cpu_pct") if c > 300]), "cpu_pct_max": max(samp.seen("cpu_pct"), default=None),
        "mem_available_mb_min": min(samp.seen("mem_available_mb"), default=None),
        "swap_used_mb_max": max(samp.seen("swap_used_mb"), default=None),
        "server_rss_mb_max": max(samp.seen("server_rss_mb"), default=None),
        "cpu_temp_c_max": max(samp.seen("cpu_c"), default=None), "skin_temp_c_max": max(samp.seen("skin_c"), default=None),
        "thermal_status_max": max(samp.seen("thermal_status"), default=None),
        "big_core_mhz_busy_min_max": [min(samp.seen("big_mhz", busy)), max(samp.seen("big_mhz", busy))] if samp.seen("big_mhz", busy) else None,
        "battery_mw_idle": mean(R["idle"]["battery_mw"]), "battery_mw_busy_mean": mean(samp.seen("battery_mw", busy)),
        "battery_pct_start_end": [pct[0], pct[-1]] if pct else None,
        "termux_external_connections_max": max(samp.seen("termux_ext_conn"), default=None),
        "termux_open_listen_max": max(samp.seen("termux_open_listen"), default=None),
        "all_external_connections_max": max(samp.seen("all_ext_conn"), default=None),
        "minutes": round((time.time() - T0) / 60, 1), "errors": R["errors"] or None,
    }


def main():
    sh(["seeker-ai", "--stop"], 60)
    R["network"] = " | ".join(rish("cmd wifi status | head -1; dumpsys connectivity 2>/dev/null | grep -m1 'Active default network'").split("\n")[:2])
    R["power_start"] = power()
    t0 = time.time()
    try:  # read the file once: both models then load from a warm cache, and their load times compare
        with open(A.model, "rb") as f:
            while f.read(1 << 24):
                pass
    except OSError as e:
        sys.exit(f"cannot read the model: {e}")
    R["file_read_s"] = round(time.time() - t0, 1)
    samp = Sampler(); samp.start()
    R["samples"], R["timeline"] = samp.s, TIMELINE  # in every save(): temperatures, power and connections survive a crash
    time.sleep(35)  # no model loaded: the idle baseline (memory every sample, two Shizuku probes)
    R["idle"] = {"battery_mw": samp.seen("battery_mw"), "skin_c": samp.seen("skin_c"), "mem_available_mb": mem_available_mb()}
    idle_n = len(samp.s["t"])
    if not A.sweep_only:
        proc, R["load_s"], log = start_server(A.ctx)
        samp.pid = proc.pid
        R["rss_after_load_mb"] = proc_status(proc.pid).get("VmRSS")
        R["server_memory_log"] = re.findall(r".*MiB.*", log.read_text(errors="replace"))[:40]
        print(f"== {A.label}: {R['model']}, ctx {A.ctx}, loaded in {R['load_s']:.0f}s, network: {R['network']}", flush=True)
        try:
            system = SA.system_text(CONF, True)
            try:
                cold = chat([{"role": "system", "content": system}, {"role": "user", "content": "Réponds seulement : prêt."}], SPECS, 20)
                R["cold_start"] = {k: cold[k] for k in ("ttft", "wall", "prompt_n", "prompt_tps", "gen_tps")}
                print(f"  cold start (agent prompt + tools, {cold['prompt_n']} tokens): first token {cold['ttft'] or 0:.0f}s", flush=True)
            except NETERR as e:
                R["errors"]["cold_start"] = errtext(e)
            R["probe_tps"] = [probe_tps()]
            parts = (("tools", lambda: bench_tools(system)), ("python", bench_python), ("french", bench_french)) + \
                (() if A.quick else (("agent", lambda: bench_agent(system)), ("convo", bench_convo)))
            for part, run in parts:
                try:
                    R[part] = run()
                except Exception as e:  # one part failing must not cost the others
                    R["errors"][part] = f"{type(e).__name__}: {e}"
                    print(f"  ERROR in {part}: {R['errors'][part]}", flush=True)
                R["peak_ram_mb"] = max(R.get("peak_ram_mb") or 0, proc_status(proc.pid).get("VmHWM") or 0) or None
                if proc.poll() is not None:  # llama-server is gone (killed by Android?): say so and start it again
                    R["errors"][part + ", server"] = f"llama-server exited with code {proc.returncode}"
                    print(f"  ERROR {R['errors'][part + ', server']}, restarting", flush=True)
                    proc, _, log = start_server(A.ctx); samp.pid = proc.pid
                R["summary"] = summary(samp, idle_n)
                save()
            R["probe_tps"].append(probe_tps())
        finally:
            R["peak_ram_mb"] = max(R.get("peak_ram_mb") or 0, proc_status(proc.pid).get("VmHWM") or 0) or None
            stop(proc)
            R["summary"] = summary(samp, idle_n)
            save()
    if A.sweep or A.sweep_only:
        R["ctx_sweep"] = []
        # last one: the model read into RAM instead of mapped (this build has --load-mode, no --no-mmap any more)
        for c, extra in ((2048, []), (4096, []), (8192, []), (4096, ["--load-mode", "none"])):
            try:
                p, load, log = start_server(c, CONF["server_args"] + extra); samp.pid = p.pid
                r = chat([{"role": "user", "content": PROBE_Q}], None, 64)
                st = proc_status(p.pid)
                R["ctx_sweep"].append({"ctx": c, "args": extra, "load_s": round(load, 1), "peak_ram_mb": st.get("VmHWM"),
                                       "mem_available_mb": mem_available_mb(), "gen_tps": r["gen_tps"], "ttft": r["ttft"],
                                       "memory_log": re.findall(r".*MiB.*", log.read_text(errors="replace"))[:40]})
                print(f"  ctx {c} {' '.join(extra)}: load {load:.0f}s, peak RAM {st.get('VmHWM')} MB, {r['gen_tps'] or 0:.1f} tok/s", flush=True)
                stop(p)
            except Exception as e:
                R["ctx_sweep"].append({"ctx": c, "args": extra, "error": f"{type(e).__name__}: {e}"})
                print(f"  ctx {c} {' '.join(extra)}: ERROR {e}", flush=True)
            save()
    samp.stop_flag = True
    R["power_end"] = power()
    R["summary"] = summary(samp, idle_n)
    R["finished"] = time.strftime("%F %T")
    save()
    print("== summary", A.label, json.dumps(R["summary"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
