#!/usr/bin/env python3
"""Self-test of seeker-ai against a fake llama-server and fake termux-*/rish commands (no model, no phone).
Run: python3 ai/test_seeker_ai.py"""
import contextlib, importlib.machinery, importlib.util, io, json, os, pty, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader("seeker_ai", str(HERE / "seeker-ai"))
sa = importlib.util.module_from_spec(importlib.util.spec_from_loader("seeker_ai", loader))
loader.exec_module(sa)

allow = sa.DEFAULT["shell_auto_allow"]
assert sa.is_auto_cmd("ls -la ~/models", allow)
for bad in ("ls; rm -rf ~", "ls $(echo x)", "rm -rf ~/models", "ls > out.txt", "cat ~/.ssh/id_ed25519"):
    assert not sa.is_auto_cmd(bad, allow), bad

requests = []
# what the Seeker's llama-server (b1-9e9619d) answers when a request is larger than the context, copied on 11/11/2026
OVERFLOW = (b'{"error":{"code":400,"message":"request (12012 tokens) exceeds the available context size (8192 tokens), '
            b'try increasing it","type":"exceed_context_size_error","n_prompt_tokens":12012,"n_ctx":8192}}')

class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"ok"}')
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests.append(body)
        last = body["messages"][-1]
        if "ERR500" in last["content"] or "TOOBIG" in last["content"] or (len(body["messages"]) > 4 and "OVERFLOW" in str(body["messages"])):
            err = (500, b'{"error":{"code":500,"message":"boom"}}') if "ERR500" in last["content"] else (400, OVERFLOW)
            self.send_response(err[0]); self.end_headers(); self.wfile.write(err[1])
            return
        if last["role"] == "user" and "CALL " in last["content"]:  # "CALL <tool> <json>" -> that tool call, in 2 chunks
            _, name, args = last["content"][last["content"].index("CALL "):].split(" ", 2)
            chunks = [{"tool_calls": [{"index": 0, "id": "c1", "function": {"name": name, "arguments": args[:5]}}]},
                      {"tool_calls": [{"index": 0, "function": {"arguments": args[5:]}}]}]
        elif last["role"] == "user":
            chunks = [{"content": "plain answer"}]
        else:
            chunks = [{"content": "TOOL SAID: "}, {"content": last["content"][:80]}]
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for c in chunks:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': c}]})}\n\n".encode())
        timings = {"prompt_n": 50, "prompt_per_second": 40.0, "predicted_n": 7, "predicted_per_second": 9.5,
                   "cache_n": 900 if "FILL" in last["content"] else 0}
        self.wfile.write(f"data: {json.dumps({'choices': [], 'timings': timings})}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

srv = HTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
tmp = Path(tempfile.mkdtemp()).resolve()
work, data, fakebin, mdir = tmp / "work", tmp / "data", tmp / "bin", tmp / "models"
for d in (work, data, fakebin, mdir): d.mkdir()
(work / "note.txt").write_text("seeker-marker-42")
(tmp / "outside.txt").write_text("secret")
(fakebin / "termux-battery-status").write_text('#!/bin/sh\necho \'{"percentage": 77}\'\n')
(fakebin / "termux-sms-send").write_text(f'#!/bin/sh\necho "$@" > {tmp}/sms_sent\n')
for f in fakebin.iterdir(): f.chmod(0o755)
for m in ("Alpha-Q4_0.gguf", "Beta-Uncensored-Q4_K_M.gguf", "mmproj-Beta-BF16.gguf"): (mdir / m).write_text("x")
conf = tmp / "config.json"

def setconf(**extra):
    base = {"server": f"http://127.0.0.1:{srv.server_port}", "allowed_paths": [str(work)], "workdir": str(work),
            "models_dir": str(mdir), "model": str(mdir / "Alpha-Q4_0.gguf")}
    conf.write_text(json.dumps({**base, **extra}))

def run(prompt, confirm="no", *extra):
    env = dict(os.environ, SEEKER_AI_CONFIG=str(conf), SEEKER_AI_DATA=str(data), SEEKER_AI_CONFIRM=confirm,
               PATH=f"{fakebin}:{os.environ['PATH']}")
    args = [sys.executable, str(HERE / "seeker-ai"), *extra] + ([prompt] if prompt else [])
    return subprocess.run(args, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=30)

def last_tool():
    return requests[-1]["messages"][-1]["content"]

def names(req):
    return [t["function"]["name"] for t in req.get("tools", [])]

setconf()
# 1. read level is auto inside the allowed folder; result reaches the model; speed, first token, sampling sent/logged
r = run(f'CALL read_file {{"path": "{work}/note.txt"}}')
assert "TOOL SAID: seeker-marker-42" in r.stdout, r.stdout + r.stderr
assert requests[-1]["chat_template_kwargs"] == {"enable_thinking": False}
assert requests[-1]["temperature"] == 0.7 and requests[-1]["top_k"] == 20
row = json.loads((data / "perf.jsonl").read_text().splitlines()[-1])
assert row["predicted_per_second"] == 9.5 and row["ttft_s"] is not None and row["model"] == "Alpha-Q4_0.gguf", row
# 2. outside the allowed folders, through a symlink, or in a denied folder: refused
run(f'CALL read_file {{"path": "{tmp}/outside.txt"}}')
assert "outside the allowed folders" in last_tool()
(work / "link").symlink_to(tmp / "outside.txt")
run(f'CALL read_file {{"path": "{work}/link"}}')
assert "outside the allowed folders" in last_tool()
(work / "secret").mkdir(); (work / "secret" / "key.txt").write_text("k")
setconf(denied_paths=[str(work / "secret")])
run(f'CALL read_file {{"path": "{work}/secret/key.txt"}}')
assert "protected folder" in last_tool(), last_tool()
setconf()
# 3. exec level asks: refused leaves the file, approved runs, in workdir
victim = work / "keep.txt"; victim.write_text("x")
run('CALL shell {"command": "rm keep.txt"}', "no")
assert victim.exists() and last_tool().startswith("denied by the user")
run('CALL shell {"command": "rm keep.txt"}', "yes")
assert not victim.exists() and last_tool().startswith("exit 0")
run('CALL shell {"command": "pwd"}')  # read-only, auto-allowed, runs in workdir
assert str(work) in last_tool(), last_tool()
run('CALL read_file {"path": "note.txt"}')  # relative paths start in workdir
assert last_tool() == "seeker-marker-42"
# 4. write level is auto for a new file, but overwriting always asks
(work / "w.txt").write_text("old")
run(f'CALL write_file {{"path": "{work}/w.txt", "content": "new"}}')
assert (work / "w.txt").read_text() == "old"
run(f'CALL write_file {{"path": "{work}/fresh.txt", "content": "new"}}')
assert (work / "fresh.txt").read_text() == "new"
# 5. levels and per-tool overrides: off = neither offered nor callable; read=ask asks
setconf(tools={"python": "off"})
run('CALL python {"code": "print(1)"}', "yes")
assert "not available" in last_tool() and "python" not in names(requests[-2])
setconf(levels={"exec": "off"})
run('CALL shell {"command": "ls"}', "yes")
assert "not available" in last_tool() and {"shell", "python"}.isdisjoint(names(requests[-2]))
setconf(levels={"read": "ask"})
run(f'CALL read_file {{"path": "{work}/note.txt"}}', "no")
assert last_tool().startswith("denied by the user")
# 6. android: read action runs, sensitive action asks; actions outside the list are neither offered nor callable
setconf(android_actions=["battery", "sms_send"])
run('CALL android {"action": "battery"}')
assert '"percentage": 77' in last_tool(), last_tool()
run('CALL android {"action": "sms_send", "number": "+351000", "text": "hi"}', "no")
assert last_tool().startswith("denied by the user") and not (tmp / "sms_sent").exists()
run('CALL android {"action": "sms_send", "number": "+351000", "text": "hi"}', "yes")
assert (tmp / "sms_sent").read_text().strip() == "-n +351000 hi"
setconf(android_policy={"battery": "off"})
run('CALL android {"action": "battery"}')
assert "not available" in last_tool()
setconf()
run('CALL android {"action": "sms_send", "number": "+351000", "text": "hi"}', "yes")
enum = next(t for t in requests[-2]["tools"] if t["function"]["name"] == "android")["function"]["parameters"]["properties"]["action"]["enum"]
assert "not available" in last_tool() and enum == sa.DEFAULT["android_actions"] and "sms_send" not in enum, (last_tool(), enum)
# 7. system without Shizuku: clear error, nothing runs
run('CALL system {"command": "id"}', "yes")
assert "Shizuku is not set up" in last_tool(), last_tool()
# 8. memory: remember writes the note once; the next run carries it in the first user message, not the system prompt
run('CALL remember {"note": "my editor is micro"}')
run('CALL remember {"note": "my editor is micro"}')
assert last_tool() == "already noted" and (data / "memory.md").read_text().count("micro") == 1
run(f'CALL list_dir {{"path": "{work}"}}')
first_user = requests[-1]["messages"][1]
assert first_user["role"] == "user" and "my editor is micro" in first_user["content"] and requests[-1]["messages"][2]["content"] == sa.NOTES_ACK
assert requests[-1]["messages"][3]["content"].startswith("CALL list_dir")  # the request stands alone: the notes do not set its language
assert "micro" not in requests[-1]["messages"][0]["content"]  # system prompt stays fixed, so its cache survives
# 9. Shizuku-backed actions go through `rish -c` with quoted arguments; install_apk is confined and asks
(fakebin / "rish").write_text(f'#!/bin/sh\nprintf "%s\\n" "$2" >> {tmp}/rish_log\necho ok\n'); (fakebin / "rish").chmod(0o755)
rlog = lambda: (tmp / "rish_log").read_text().splitlines()[-1]
run('CALL android {"action": "notify", "text": "hello; rm -rf ~"}')
assert rlog() == "cmd notification post -S bigtext -t seeker-ai seeker_ai 'hello; rm -rf ~'"
run('CALL android {"action": "notify", "title": "SEEKER ZERO ok"}')
assert rlog() == "cmd notification post -S bigtext -t seeker-ai seeker_ai 'SEEKER ZERO ok'"
run(f'CALL android {{"action": "install_apk", "path": "{tmp}/evil.apk"}}', "yes")
assert "outside the allowed folders" in last_tool()
(work / "app.apk").write_text("x")
run(f'CALL android {{"action": "install_apk", "path": "{work}/app.apk"}}', "no")
assert last_tool().startswith("denied by the user")
run(f'CALL android {{"action": "install_apk", "path": "{work}/app.apk"}}', "yes")
assert rlog() == f"pm install -r {work}/app.apk"
run('CALL android {"action": "open_url", "text": "file:///etc/passwd"}', "yes")
assert "needs an http(s) URL" in last_tool()
# 10. system: read-only commands auto, others ask, Seed Vault packages refused even when approved
run('CALL system {"command": "id"}', "no")
assert rlog() == "id"
run('CALL system {"command": "pm disable-user com.solanamobile.seedvaultimpl"}', "yes")
assert last_tool().startswith("refused") and "seedvaultimpl" not in (tmp / "rish_log").read_text()
run('CALL system {"command": "pm disable-user com.solana\\\"\\\"mobile.seed\\\\vaultimpl"}', "yes")
assert last_tool().startswith("refused"), last_tool()
run('CALL system {"command": "settings put global foo 1"}', "no")
assert last_tool().startswith("denied by the user")
# 11. chat mode: no tools offered, conversation instructions
r = run("bonjour", "no", "--chat")
assert "tools" not in requests[-1] and requests[-1]["messages"][0]["content"] == sa.SYSTEM_CHAT and "plain answer" in r.stdout
# 12. a custom instructions file wins over the default
(tmp / "system.md").write_text("Tu es un pirate.")
run("bonjour")
assert requests[-1]["messages"][0]["content"] == "Tu es un pirate."
(tmp / "system.md").unlink()
# 13. history of tasks
h = json.loads((data / "history.jsonl").read_text().splitlines()[-1])
assert h["prompt"] == "bonjour" and h["mode"] == "agent" and h["tools"] == []
run('CALL android {"action": "battery"}')
assert json.loads((data / "history.jsonl").read_text().splitlines()[-1])["tools"] == ["android:battery"]
# 14. models: list (no mmproj, * on the default), --use keeps a backup, ambiguous names refused
r = run("", "no", "--models")
assert "* Alpha-Q4_0.gguf" in r.stdout and "Beta-Uncensored-Q4_K_M.gguf" in r.stdout and "mmproj" not in r.stdout, r.stdout
r = run("", "no", "--use", "uncensored")
assert json.loads(conf.read_text())["model"].endswith("Beta-Uncensored-Q4_K_M.gguf") and list(tmp.glob("config.json.bak-*")), r.stdout + r.stderr
r = run("", "no", "--use", "q4")
assert r.returncode != 0 and "ambiguous" in r.stderr
# 15. status
r = run("", "no", "--status")
assert "online" in r.stdout and "permissions  read=auto, write=auto, exec=ask, sensitive=ask" in r.stdout, r.stdout
# 16. hidden files and folders are protected from the file tools, even inside an allowed folder
(work / ".env").write_text("TOKEN=1"); (work / ".git" / "hooks").mkdir(parents=True)
run(f'CALL read_file {{"path": "{work}/.env"}}')
assert "hidden file or folder" in last_tool(), last_tool()
run(f'CALL write_file {{"path": "{work}/.git/hooks/pre-commit", "content": "#!/bin/sh"}}', "yes")
assert "hidden file or folder" in last_tool() and not (work / ".git/hooks/pre-commit").exists()
# 17. the Seed Vault lock also covers shell and python, even approved
for call in ('CALL shell {"command": "rish -c \'pm uninstall com.solanamobile.seedvaultimpl\'"}',
             'CALL python {"code": "import os; os.system(\'pm disable-user com.solanamobile.wallet\')"}'):
    run(call, "yes")
    assert last_tool().startswith("refused"), last_tool()
# 18. arguments that are not strings do not crash; vibration is capped at 3 s
run('CALL android {"action": "vibrate", "value": 999999}')
assert rlog() == "cmd vibrator_manager synced -f oneshot 3000", rlog()
r = run('CALL shell {"command": ["ls"]}', "no")
assert r.returncode == 0 and last_tool().startswith("denied by the user"), r.stderr
# 19. the approval question shows the whole command, with escape sequences and bidi overrides made visible
long_cmd = "echo " + "a" * 700 + " ; touch END_MARK \u202e \u001b[2J"
r = run("CALL shell " + json.dumps({"command": long_cmd}), "no")
assert "touch END_MARK \\u202e \\u001b[2J" in r.stderr and "\u202e" not in r.stderr and "\x1b[2J" not in r.stderr, r.stderr[-300:]
# 20. escape sequences in a tool result are not replayed on the terminal
(work / "esc.txt").write_text("before \x1b[2J after")
r = run(f'CALL read_file {{"path": "{work}/esc.txt"}}')
assert "before \\u001b[2J after" in r.stderr and "\x1b[2J" not in r.stderr + r.stdout, r.stderr
# 21. long conversations: context nearly full or request too large -> the older half is forgotten, the chat goes on
c = json.loads(json.dumps(sa.DEFAULT)); c.update(server=f"http://127.0.0.1:{srv.server_port}", ctx=1000); sa.DATA = data
msgs = [{"role": "system", "content": "S"}] + sa.notes_pair(c)
for i in range(4):
    msgs += [{"role": "user", "content": f"q{i} OVERFLOW"}, {"role": "assistant", "content": f"a{i}"}]
msgs.append({"role": "user", "content": "last question"})
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    sa.turn(c, msgs, [], {})   # 400 exceed_context_size_error until the old exchanges are gone
assert [m["content"] for m in msgs[2:]] == [sa.NOTES_ACK, "last question", "plain answer"], msgs  # the fake refuses while > 4 messages
assert msgs[1]["content"].startswith("Notes kept") and "micro" in msgs[1]["content"]  # the notes survive the cut
msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "q0"}, {"role": "assistant", "content": "a0"},
        {"role": "user", "content": "q1 FILL"}]
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    sa.turn(c, msgs, [], {})   # the server reports 957 tokens used out of 1000
    msgs.append({"role": "user", "content": "q2"})
    sa.turn(c, msgs, [], {})
assert msgs[1]["content"].endswith("q1 FILL") and [m["content"] for m in msgs[2:]] == ["plain answer", "q2", "plain answer"], msgs
try:
    sa.turn(c, [{"role": "system", "content": "S"}, {"role": "user", "content": "ERR500"}], [], {})
    raise SystemExit("a server error must be raised")
except sa.ServerError as e:
    assert "500" in str(e)
# 22. interactive chat: a request that fails is forgotten, the chat stays alive and the next one works
master, slave = pty.openpty()
env = dict(os.environ, SEEKER_AI_CONFIG=str(conf), SEEKER_AI_DATA=str(data), SEEKER_AI_CONFIRM="no", PATH=f"{fakebin}:{os.environ['PATH']}")
chat = subprocess.Popen([sys.executable, str(HERE / "seeker-ai")], stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True)
for line in ("premier", "ERR500", "second", "TOOBIG", "troisieme", "/exit"):  # TOOBIG: larger than the context by itself
    os.write(master, (line + "\n").encode()); time.sleep(0.7)
out = chat.communicate(timeout=30)[0]
sent = [m["content"] for m in requests[-1]["messages"][1:] if not m["content"].startswith(sa.NOTES) and m["content"] != sa.NOTES_ACK]
assert chat.returncode == 0 and "this request is forgotten" in out, out
assert len(sent) == 5 and sent[0].endswith("premier") and sent[2] == "second" and sent[4] == "troisieme", sent
assert "ERR500" not in str(sent) and "TOOBIG" not in str(sent) and out.count("this request is forgotten") == 2, out
# 23. -f: read from the current directory, before the model loads; a file that may not be read stops with a clear message
run("question", "no", "-f", str(work / "note.txt"))
assert '<file path="' in requests[-1]["messages"][-1]["content"] and "seeker-marker-42" in requests[-1]["messages"][-1]["content"]
r = run("question", "no", "-f", str(work / ".env"))
assert r.returncode != 0 and "cannot read" in r.stderr and "Traceback" not in r.stderr, r.stderr
# 24. the whole android tool on "ask" tightens the listed actions and never reopens the others
setconf(tools={"android": "ask"}, android_policy={"battery": "off"})
run('CALL android {"action": "battery"}', "yes")
assert "not available" in last_tool(), last_tool()
run('CALL android {"action": "sms_send", "number": "+351000", "text": "again"}', "yes")
assert "not available" in last_tool() and "again" not in (tmp / "sms_sent").read_text()
run('CALL android {"action": "notify", "text": "x"}', "no")
assert last_tool().startswith("denied by the user")
# 25. a hidden folder opens only when the config names it, wherever it is in the list
(work / ".git" / "info.txt").write_text("visible-on-request")
setconf(allowed_paths=[str(work), str(work / ".git")])
run(f'CALL read_file {{"path": "{work}/.git/info.txt"}}')
assert last_tool() == "visible-on-request", last_tool()
setconf()
# 26. llama-server is recognised by its command line (copied from the Seeker: the process itself is named linker64)
L = b"/data/data/com.termux/files/home/llama.cpp/build-static/bin/llama-server"
assert sa.is_llama_server(L + b"\0" + L + b"\0-m\0x.gguf\0") and sa.is_llama_server(b"llama-server\0-m\0x.gguf\0")
assert not sa.is_llama_server(b"python\0/usr/bin/python\0bench_agent.py\0x.gguf\0--server\0" + L + b"\0")
# 27. a command that prints on stdout and stderr (rish does, at random) comes back whole and in order
(fakebin / "rish").write_text("#!/bin/sh\necho one\necho two >&2\necho three\n")
run('CALL system {"command": "id"}')
assert last_tool() == "exit 0\none\ntwo\nthree\n", last_tool()
# 28. after a refusal the turn ends with an answer offered no tools: the model cannot ask again
before = len(requests)
run('CALL shell {"command": "rm keep2.txt"}', "no")
assert len(requests) == before + 2 and "tools" in requests[-2] and "tools" not in requests[-1], [r.get("tools") is None for r in requests[before:]]
assert last_tool().startswith("denied by the user: NOT done"), last_tool()
# 29. the agent prompt names the configured work folder
run("bonjour")
assert f"Your work folder is {work}" in requests[-1]["messages"][0]["content"], requests[-1]["messages"][0]["content"][:300]
# 30. the shell's auto-allowed commands run alone only on folders the file tools may see
run('CALL shell {"command": "ls /"}', "no")
assert last_tool().startswith("denied by the user"), last_tool()
run('CALL shell {"command": "ls -a ."}', "no")
assert "note.txt" in last_tool(), last_tool()
print("seeker-ai self-test: OK (30 scenarios)")
