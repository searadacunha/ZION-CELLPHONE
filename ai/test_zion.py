#!/usr/bin/env python3
"""Self-test of zion, the supervisor, with a fake seeker-ai, a fake rish, fake `am` and termux-battery-status (no phone,
no model). The approval signature is checked against a vector made with openssl (RSA 2048, SHA256withRSA, 17/11/2026)
and, when present, the launcher's own Java vector (tests/approval_vectors.json). Run: python3 ai/test_zion.py"""
import base64, fcntl, hashlib, importlib.machinery, importlib.util, io, json, os, sys, tempfile, time
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
tmp = Path(tempfile.mkdtemp()).resolve()
fake, fd, data = tmp / "bin", tmp / "fd", tmp / "data"
for d in (fake, fd, data / "tasks"):
    d.mkdir(parents=True)
os.environ.update({"ZION_STATE": str(tmp / "zion"), "ZION_PIN": str(tmp / "pin.pub"), "SEEKER_AI_DATA": str(data),
                   "SEEKER_AI_BUSY": str(tmp / "busy"), "ZION_OPERATOR": str(fake / "seeker-ai"), "ZION_RISH": str(fake / "rish"),
                   "FAKE_DIR": str(fd), "PATH": f"{fake}:{os.environ['PATH']}"})
(fake / "seeker-ai").write_text(f"""#!{sys.executable}
import json, os, sys, time
from pathlib import Path
a, T = sys.argv[1:], Path(os.environ["FAKE_DIR"])
with open(T / "calls.log", "a") as f:
    f.write(json.dumps({{"argv": a, "approved": os.environ.get("ZION_APPROVED", ""), "denied": os.environ.get("ZION_DENIED", ""),
                        "unattended": os.environ.get("ZION_UNATTENDED")}}) + "\\n")
if "--policy" in a:
    print((T / "policy.json").read_text() if (T / "policy.json").exists() else
          json.dumps({{"apps": [], "limits": {{"task_minutes": 45, "battery_min": 25, "temp_max_c": 42, "mem_min_mb": 0}}}}))
    sys.exit(0)
if "--stop" in a:
    sys.exit(0)
tasks = Path(os.environ["SEEKER_AI_DATA"]) / "tasks"
if "--task-resume" in a:
    tid = a[a.index("--task-resume") + 1]
    t = json.loads((tasks / f"{{tid}}.json").read_text())
    t.update(status="done", steps=[{{"status": "done"}}])
    (tasks / f"{{tid}}.json").write_text(json.dumps(t))
    sys.exit(0)
tid, goal = a[a.index("--task-id") + 1], a[a.index("--") + 1]
def write(status, **kw):
    (tasks / f"{{tid}}.json").write_text(json.dumps({{"id": tid, "status": status, **kw,
                                                    "steps": [{{"status": "done" if status == "done" else "doing"}}]}}))
if "SLEEP" in goal:
    write("running"); time.sleep(30); write("done"); sys.exit(0)
if "PARK" in goal:
    cmd = ("ls /sdcard/Download/" + "x" * 175 + " ; touch MARKER" if "PARKLONG" in goal else
           "echo " + "y" * 2000 if "PARKHUGE" in goal else "rm keep.txt")
    write("waiting", pending={{"class": "exec", "what": "shell " + json.dumps({{"command": cmd}}), "digest": "d" * 64,
                              "step": 1, "call": {{"name": "shell", "args": {{"command": cmd}}}}}})
    sys.exit(4)
if "CRASH" in goal:
    write("running"); sys.exit(1)
if "SERVER" in goal:
    write("running"); sys.exit(6)
write("done", report="r.md"); sys.exit(0)
""")
(fake / "rish").write_text(f"""#!/bin/sh
T={fd}
printf '%s\\n' "$2" >> $T/rish.log
case "$2" in
  *ZIONEND*) cat $T/launcher_STOP 2>/dev/null; echo ZIONSEP; cat $T/launcher_RESUME 2>/dev/null; echo ZIONEND ;;
  *ZIONSEP*) cat $T/launcher_ok 2>/dev/null; echo ZIONSEP; cat $T/launcher_no 2>/dev/null ;;
  *approval.pub*) cat $T/launcher_pub 2>/dev/null ;;
  *isKeyguardShowing*) cat $T/keyguard 2>/dev/null || echo isKeyguardShowing=false ;;
esac
exit 0
""")
(fake / "am").write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> {fd}/am.log\n')
(fake / "termux-battery-status").write_text(f'#!/bin/sh\ncat {fd}/battery 2>/dev/null || echo \'{{"percentage": 80, "plugged": "UNPLUGGED", "temperature": 30}}\'\n')
for f in fake.iterdir():
    f.chmod(0o755)

loader = importlib.machinery.SourceFileLoader("zion", str(HERE / "zion"))
z = importlib.util.module_from_spec(importlib.util.spec_from_loader("zion", loader))
loader.exec_module(z)
z.SYNC, z.KILL_MARGIN = 0, 0
state = {}


def until(cond, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        z.step(state)
        if cond():
            return True
        time.sleep(0.1)
    raise AssertionError(f"not reached in {timeout} s: {[(t['id'], t['state']) for t in z.tasks()][-3:]} "
                         f"{z.JOURNAL.read_text().splitlines()[-4:]}")


def get(tid):
    return next(t for t in z.tasks() if t["id"] == tid)


def events():
    return [json.loads(l)["event"] for l in z.JOURNAL.read_text().splitlines()]


def calls():
    return [json.loads(l) for l in (fd / "calls.log").read_text().splitlines()]


def policy(**limits):
    (fd / "policy.json").write_text(json.dumps({"apps": [], "limits": {"task_minutes": 45, "battery_min": 25, "temp_max_c": 42,
                                                                       "mem_min_mb": 0, **limits}}))
    z._policy["t"] = 0


policy()
# 1. a queued task runs unattended in a process group of its own, ends done, and every step is in the journal
t = z.add("say DONE")
until(lambda: get(t["id"])["state"] == "done")
c = [x for x in calls() if "--task" in x["argv"]][-1]
assert c["argv"][-2:] == ["--", "say DONE"] and "--unattended" in c["argv"] and c["unattended"] == "1", c
assert events()[-3:] == ["added", "started", "finished"] and get(t["id"])["steps"] == "1/1", events()
assert z.verify_chain()[0] == 0
# 2. the higher priority goes first; a password in a goal never reaches the journal
lo, hi = z.add("say DONE low"), z.add("say DONE high", priority=5)
z.step(state)
assert get(hi["id"])["state"] == "running" and get(lo["id"])["state"] == "queued"
until(lambda: get(lo["id"])["state"] == "done")
z.add("connecte-toi, mdp: hunter2 DONE")
assert "hunter2" not in z.JOURNAL.read_text()
until(lambda: all(t["state"] == "done" for t in z.tasks()))
# 3. parked on an exact call (exit 4): the request goes to the launcher (am broadcast) and to a notification; the
#    owner approves in a terminal; the task goes on with that call's digest, once
z.owner_says_yes = lambda q: True
t = z.add("PARK please")
until(lambda: get(t["id"])["state"] == "waiting")
a = get(t["id"])["approval"]
req = (z.APPROVALS / f"{a['id']}.req").read_bytes()
assert hashlib.sha256(req).hexdigest() == a["req_sha256"] and json.loads(req)["class"] == "exec"
assert "zero.seeker.launcher/.ApprovalAsk -a zero.seeker.launcher.APPROVAL_ASK -f 0x20 --es req" in (fd / "am.log").read_text()
assert "cmd notification post" in (fd / "rish.log").read_text() and req.isascii() and set(json.loads(req)) == {
    "v", "id", "created", "expires", "class", "summary", "detail"}  # the launcher accepts exactly these keys
assert z.visible("a‮b\x07c\nd‍e", "\n") == "abc\nde"  # what the launcher would refuse never reaches it
with redirect_stdout(io.StringIO()):
    z.cmd_approve(t["id"], "approve")
until(lambda: get(t["id"])["state"] == "done")
c = calls()[-1]
assert c["argv"][c["argv"].index("--task-resume") + 1] == t["id"] and c["approved"] == "d" * 64 and not c["denied"], c
assert "approval_granted" in events()
# 4. refused in the launcher (a .no file): the task goes on without that call
t = z.add("PARK again")
until(lambda: get(t["id"])["state"] == "waiting")
(fd / "launcher_no").write_text('{"v":1,"decision":"deny"}')
until(lambda: get(t["id"])["state"] == "done")
(fd / "launcher_no").unlink()
assert calls()[-1]["denied"] == "d" * 64 and not calls()[-1]["approved"], calls()[-1]
# 5. the launcher's signed approval: RSA PKCS#1 v1.5 SHA-256 over the request's exact bytes, checked with the pinned
#    key; a wrong request, key, signature or time is not an approval
V = {"spki_b64": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAo+yxDhkiA7nqYly3jzFPHREWrKuCRLqerC5AYkCYaOzuDGiICp0uVdbugE4z2XtjS7blOtEbVE4eqwUjr6EXasYebuBn87W9TJzISZp41t3eias1+JJ+Tysga3KUrJTs0K+4uTwP3UiaCvZh1oJ+JI8AcfOkzykVaF8QPPVQS/LReLyczB1QEBd1QqJrr5j+iDtUvUstxde4EJZI6uKHJVWh5ToKO3WvnlNmIWzrysM06FscTvL1MSDIOJZz0rFW56E3WpYpBAKoZwqCfJDx8rLCA65okUE5SuTghmomVE612B2Iep7fJMeFyv5ksQlkNFt4M0Jzm4fxMHE4rcb3YQIDAQAB",
     "req": '{"v":1,"id":"20261117-180000-ab12-a1","created":1795000000,"expires":1795043200,"class":"exec","summary":"shell {\\"command\\": \\"rm keep.txt\\"} é","detail":"Tâche : test"}',
     "req_sha256": "634a3a68f89b673865f4aacaf3ca6fbc9cee6a798029a661078e5fe32ce6bd65", "signed_at": 1795000100,
     "sig_b64": "Mr6VeLUdD7iHSxT52qLze/9l3jBZS5IKJZV6DEYB6GyjVDTUEAjj4cbATATxXH/LeN5oyLrlY1+0JOW3XxoAMnM4Ms64ZjjDC30yyIUXRyfR3sx9loAhbbOYS7PR/nTRL1PXN8ObbtuXPYwXIkRUhGFkFFJfq80F0uBTuMLNKAuPNy+NGA6XUx9djgRjxuDKTyaj7Ts6bn3s2W91+ApM9FhaMmcuH2LlCN9ZC7TR3XiXrRzZlo9mzS4s734UdhBbrr5PTiALuHat62r4FG0xLG3CeyDjZZVjzNY1oujY8Ux8V/hQv1I/EQoQOxZtYRDunjyPVozIqDMLn10W/l1c5Q=="}
spki, sig = base64.b64decode(V["spki_b64"]), base64.b64decode(V["sig_b64"])
assert hashlib.sha256(V["req"].encode()).hexdigest() == V["req_sha256"]
aid = json.loads(V["req"])["id"]
assert z.rsa_verify(spki, z.approval_payload(aid, V["req_sha256"], "approve", V["signed_at"]), sig)
assert not z.rsa_verify(spki, z.approval_payload(aid, V["req_sha256"], "approve", V["signed_at"] + 1), sig)
assert not z.rsa_verify(spki, z.approval_payload(aid, V["req_sha256"], "approve", V["signed_at"]), sig[:-1] + bytes([sig[-1] ^ 1]))
try:
    z.rsa_key(b"\x30\x03\x02\x01\x05")
    raise AssertionError("a non-RSA key was accepted")
except ValueError:
    pass
ok = json.dumps({"v": 1, "id": aid, "req_sha256": V["req_sha256"], "decision": "approve", "signed_at": V["signed_at"], "sig": V["sig_b64"]})
(fd / "launcher_ok").write_text(ok)
rec = {"id": aid, "req_sha256": V["req_sha256"], "expires": 1795043200}
assert z.launcher_decision(rec) is None  # no key pinned yet
z.PIN.write_text(V["spki_b64"] + "\n")
assert z.launcher_decision(rec) == "approve"
assert z.launcher_decision({**rec, "req_sha256": "0" * 64}) is None  # another request than the one shown
assert z.launcher_decision({**rec, "expires": 1795000000}) is None  # signed after the request expired
other = bytearray(spki)
other[100] ^= 1  # one bit of the modulus: another key
z.PIN.write_text(base64.b64encode(bytes(other)).decode())
assert z.launcher_decision(rec) is None and "approval_refused_signature" in events()
(fd / "launcher_ok").unlink()
z.PIN.unlink()
java = HERE.parent / "tests" / "approval_vectors.json"  # the launcher's ApprovalFormat, signed in Java (launcher/test)
if java.exists():
    J = json.loads(java.read_text())
    jid = json.loads(J["req"])["id"]
    assert hashlib.sha256(J["req"].encode()).hexdigest() == J["req_sha256"]
    assert z.approval_payload(jid, J["req_sha256"], "approve", json.loads(J["ok_json"])["signed_at"]).decode() == J["payload"]
    assert z.rsa_verify(base64.b64decode(J["spki_b64"]), J["payload"].encode(), base64.b64decode(J["sig_b64"]))
    N = J["negative"]  # a signature made over another request: never an approval of this one
    assert not z.rsa_verify(base64.b64decode(J["spki_b64"]), N["payload"].encode(), base64.b64decode(N["sig_b64"])), N["why"]
# 6. a request nobody answers expires: refused
t = z.add("PARK expire")
until(lambda: get(t["id"])["state"] == "waiting")
w = get(t["id"])
w["approval"]["expires"] = time.time() - 1
z.save(w)
until(lambda: get(t["id"])["state"] == "done")
assert calls()[-1]["denied"] == "d" * 64
# 7. killed by Android or crashed (exit 1): goes on from its step later; a lost llama-server (exit 6): stopped first
t = z.add("CRASH once")
until(lambda: get(t["id"]).get("resumes") == 1)
w = get(t["id"])
assert w["state"] == "queued" and w["resume"] and w["not_before"] > time.time(), w
w["not_before"] = 0
z.save(w)
until(lambda: get(t["id"])["state"] == "done")
t = z.add("SERVER lost")
until(lambda: get(t["id"]).get("resumes") == 1)
assert any(c["argv"] == ["--stop"] for c in calls())
w = get(t["id"]); w["not_before"] = 0; z.save(w)
until(lambda: get(t["id"])["state"] == "done")
# 8. over its time limit: the whole process group is killed, the task ends as timeout
policy(task_minutes=0.01)
t = z.add("SLEEP long")
until(lambda: get(t["id"])["state"] == "timeout", 20)
assert not z.alive(get(t["id"])["pid"]) and "killed" in events()
policy()
# 9. the emergency stop: the running task is killed and waits; nothing starts while it is there; it goes on after
t = z.add("SLEEP stopme")
until(lambda: z.operator_task(t["id"]) is not None)  # OPERATOR has its task file: the stop comes mid-task
pid = get(t["id"])["pid"]
z.stop("zion-stop", "test")
until(lambda: get(t["id"])["state"] == "queued")
assert not z.alive(pid) and get(t["id"])["resume"]
z.step(state)
assert get(t["id"])["state"] == "queued"
z.STOP.unlink()
w = get(t["id"]); w["not_before"] = 0; z.save(w)
until(lambda: get(t["id"])["state"] == "done")
# 10. the launcher's STOP is mirrored here; its "reprendre ZION" leaves RESUME, signed after the fingerprint like an
#     approval (openssl, same test key): only that lifts the stop here; a stop typed in Termux stays
RESUME = json.dumps({"v": 1, "id": "resume-1794890000", "req_sha256": "77499f5698faf42af321f9cdb350edf49d848557b282f3c30f41b6cdd681527e", "decision": "approve", "signed_at": 1794900000, "sig": "I8EdhcLJ0ytWbWz+yKmTVj9nc9sJtqSS6l95NKQZtpIkdZrEm1N9hYUhowhrq61LZEUp1YFogXGfX5SD+QEu5K6ZgV/2BOI9X0tOMwwJRMuW8F0FCh6FIuKFqI8tP5zcYnajA5tyVx2NGyt5D6VzKfDd09ZiQ0xSMAw8IJjrE4zXiaVvTkuv8IZDFUY1yNEqo2adrr20UGP3tluFaOFOE3L8np/y0u1CnXA1i9wz6M8KALGU2SFwMUHlUI6Ae1MczHC3frkiNcxKVW9jp73mHrQPpewSG3oaTOLpZPkIptF9NSWX4VStbM41hTokYdIyoGlqkymG2f5rOBpvC7Opjg=="})
z.PIN.write_text(V["spki_b64"] + "\n")
def launcher_resumed():  # the launcher deleted its STOP and signed RESUME; the stop here is older than the signature
    (fd / "launcher_STOP").unlink(missing_ok=True)
    (fd / "launcher_RESUME").write_text(RESUME)
    os.utime(z.STOP, (1794890000, 1794890000))
(fd / "launcher_STOP").write_text("1794890000")
z.step(state)
assert z.STOP.read_text().startswith("launcher-sync")
launcher_resumed()
z.step(state)
assert not z.STOP.exists() and events()[-1] == "resume"
(fd / "launcher_RESUME").unlink()
z.stop("zion-stop", "typed")
z.step(state)
assert z.STOP.exists()
z.STOP.unlink()
(fd / "launcher_STOP").write_text("1794890000")  # STOP in the launcher, its shortcut ran zion-stop launcher here too
z.stop("launcher", "zion stop")
z.step(state)
launcher_resumed()  # "reprendre ZION" with the fingerprint
z.step(state)
assert not z.STOP.exists()
(fd / "launcher_RESUME").unlink()
# 11. resources: low battery not charging, too hot, a measurement holding the memory: nothing starts, said once
(fd / "battery").write_text('{"percentage": 10, "plugged": "UNPLUGGED", "temperature": 30}')
t = z.add("say DONE later")
z.step(state); z.step(state)
assert get(t["id"])["state"] == "queued" and events().count("waiting") >= 1 and events()[-1] == "waiting"
(fd / "battery").write_text('{"percentage": 10, "plugged": "PLUGGED_USB", "temperature": 30}')
until(lambda: get(t["id"])["state"] == "done")
(fd / "battery").write_text('{"percentage": 90, "plugged": "UNPLUGGED", "temperature": 47}')
assert "°C" in z.resources(z.policy()["limits"])
(fd / "battery").unlink()
(tmp / "busy").write_text(f"{os.getpid()}\nmeasuring")
assert z.resources(z.policy()["limits"]) == "a measurement holds the memory"
(tmp / "busy").unlink()
# 12. a locked phone: a task that drives the screen waits for the owner to unlock it; one that does not runs
(fd / "keyguard").write_text("isKeyguardShowing=true")
t1, t2 = z.add("say DONE on screen"), z.add("say DONE in files", screen=False)
until(lambda: get(t2["id"])["state"] == "done")
assert get(t1["id"])["state"] == "queued"
(fd / "keyguard").unlink()
until(lambda: get(t1["id"])["state"] == "done")
# 13. at its start the supervisor takes back a task whose worker died with the phone or Termux
w = z.add("say DONE")
w.update(state="running", pid=999999999)
z.save(w)
(data / "tasks" / f"{w['id']}.json").write_text(json.dumps({"id": w["id"], "status": "running", "steps": []}))
z.recover()
assert get(w["id"])["state"] == "queued" and get(w["id"])["resume"]
w2 = z.add("say DONE")  # cut before OPERATOR wrote anything: started afresh, not resumed
w2.update(state="running", pid=999999999)
z.save(w2)
z.recover()
assert get(w2["id"])["state"] == "queued" and not get(w2["id"])["resume"]
# 14. one supervisor at a time
hold = open(z.LOCK, "a+")
fcntl.flock(hold, fcntl.LOCK_EX)
n = len(events())
with redirect_stdout(io.StringIO()) as out:
    z.loop(once=True)
assert "already runs" in out.getvalue() and len(events()) == n
hold.close()
# 15. the journal's chain: an edited, removed or reordered line is found
assert z.verify_chain()[0] == 0
lines = z.JOURNAL.read_text().splitlines()
for bad in (lines[:3] + [lines[3].replace('"event": "', '"event": "x')] + lines[4:], lines[:3] + lines[4:], lines[:3] + [lines[4], lines[3]] + lines[5:]):
    z.JOURNAL.write_text("\n".join(bad) + "\n")
    assert z.verify_chain()[0] == 4, z.verify_chain()
z.JOURNAL.write_text("\n".join(lines) + "\n")
assert z.verify_chain()[0] == 0
# 16. zion allow / disallow: the owner's list of apps, kept as valid JSON, journaled; never without his "oui"
os.environ["ZION_POLICY"] = str(tmp / "policy.json")
(tmp / "policy.json").write_text('{"apps": ["org.fossify.math"], "classes": {"exec": "deny"}}')
with redirect_stdout(io.StringIO()):
    z.cmd_allow(["zero.seeker.testbed"], True)
    z.cmd_allow(["org.fossify.math"], False)
p = json.loads((tmp / "policy.json").read_text())
assert p == {"apps": ["zero.seeker.testbed"], "classes": {"exec": "deny"}} and events()[-1] == "policy_apps", p
z.owner_says_yes = lambda q: False
with redirect_stdout(io.StringIO()):
    z.cmd_allow(["com.example.more"], True)
assert json.loads((tmp / "policy.json").read_text())["apps"] == ["zero.seeker.testbed"]
# ---- found by the independent review of 17/11 ----
# 17. a journal over 64 KB full of accents: the tail read may land inside a letter, the journal never wedges; a line cut
#     by a power loss stays visible to verify, and the next events are still written and chained
z.JOURNAL.unlink()
for i in range(400):
    z.journal("note", goal="Tâche é" * (7 + i % 5))
assert z.JOURNAL.stat().st_size > 65536 and z.verify_chain()[0] == 0
z.JOURNAL.write_bytes(z.JOURNAL.read_bytes() + b'{"t": "2026-11-17T20:00:00", "event": "cu')
z.journal("after", n=1)
last = json.loads(z.JOURNAL.read_text().splitlines()[-1])
assert last["event"] == "after" and last["after_cut_line"] and z.verify_chain()[0] == 401, z.verify_chain()
z.JOURNAL.unlink()
# 18. a pid reused after a restart is not the task's worker: never waited for, never signalled
procdir = tmp / "proc"
(procdir / str(os.getpid())).mkdir(parents=True)
(procdir / str(os.getpid()) / "cmdline").write_bytes(b"python3\0/x/other-program\0")
z.PROC = procdir
w = z.add("say DONE")
w.update(state="running", pid=os.getpid())  # alive, but someone else
z.save(w)
(data / "tasks" / f"{w['id']}.json").write_text(json.dumps({"id": w["id"], "status": "running", "steps": []}))
assert not z.owns(get(w["id"]))
z.recover()
assert get(w["id"])["state"] == "queued" and get(w["id"])["resumes"] == 1
(procdir / str(os.getpid()) / "cmdline").write_bytes(b"python3\0seeker-ai\0--task-resume\0" + w["id"].encode() + b"\0")
assert z.owns({**get(w["id"]), "pid": os.getpid()})
z.PROC = tmp / "no-proc"
w = get(w["id"]); w["not_before"] = 0; z.save(w)
until(lambda: get(w["id"])["state"] == "done")
# 19. a task that keeps getting Termux killed is given up after RESUMES interruptions, not looped
w = z.add("say DONE never")
for _ in range(z.RESUMES + 1):
    w = get(w["id"])
    w.update(state="running", pid=999999999)
    z.save(w)
    z.recover()
assert get(w["id"])["state"] == "failed" and "interrupted" in get(w["id"])["why"], get(w["id"])
# 20. one broken task file fails alone; the others still run
bad = z.add("say DONE broken")
raw = json.loads((z.QUEUE / f"{bad['id']}.json").read_text())
del raw["goal"], raw["apps"]
(z.QUEUE / f"{bad['id']}.json").write_text(json.dumps(raw))
good = z.add("say DONE good")
until(lambda: get(good["id"])["state"] == "done")
assert get(bad["id"])["state"] == "failed" and "task_unreadable" in events()
# 21. zion cancel on a running task: the supervisor (the only writer of its state) stops it, and it stays cancelled
t = z.add("SLEEP cancel me")
until(lambda: z.operator_task(t["id"]) is not None)
pid = get(t["id"])["pid"]
(z.QUEUE / f"{t['id']}.cancel").touch()
until(lambda: get(t["id"])["state"] == "cancelled")
assert not z.alive(pid) and not (z.QUEUE / f"{t['id']}.cancel").exists()
z.step(state)
assert get(t["id"])["state"] == "cancelled" and not any(x["state"] == "running" for x in z.tasks())
# 22. a stop typed as "launcher" whose launcher file is not visible yet is not lifted by the sync (only one it saw)
z.stop("launcher", "typed")
z.step(state)
assert z.STOP.exists()
(fd / "launcher_STOP").write_text("1794890000")
z.step(state)
assert z.STOP.read_text().startswith("launcher-sync")
launcher_resumed()
z.step(state)
assert not z.STOP.exists()
(fd / "launcher_RESUME").unlink()
# 23. zion allow and zion approve run by a program (stdin not a terminal, as the AI's shell tool runs them): refused,
#     nothing changes (a pseudo-terminal is OPERATOR's to refuse: ai/test_seeker_ai.py scenario 84)
import subprocess
before = (tmp / "policy.json").read_text()
for argv in (["allow", "com.evil.app"], ["approve", "x"]):
    r = subprocess.run([sys.executable, str(HERE / "zion"), *argv], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       env={**os.environ, "ZION_POLICY": str(tmp / "policy.json")}, timeout=60)
    assert r.returncode != 0 and ("only from a terminal" in r.stderr or "no task waits" in r.stderr), (argv, r.stderr)
assert (tmp / "policy.json").read_text() == before
# 24. a launcher STOP is never lifted without the owner's signed resume: the STOP file deleted by anything else (the
#     shell can), a RESUME with another signature, or one signed before this stop (an old one left there)
z.PIN.write_text(V["spki_b64"] + "\n")
for resume_file, why in ((None, "STOP deleted, no RESUME"), (RESUME.replace('"sig": "I8', '"sig": "J8'), "bad signature"),
                         (RESUME, "signed before this stop")):
    z.stop("launcher", "test")
    (fd / "launcher_STOP").write_text("1794890000")
    z.step(state)
    (fd / "launcher_STOP").unlink()
    (fd / "launcher_RESUME").unlink(missing_ok=True)
    if resume_file:
        (fd / "launcher_RESUME").write_text(resume_file)
    os.utime(z.STOP, (1794990000, 1794990000) if why == "signed before this stop" else (1794890000, 1794890000))
    z.step(state)
    assert z.STOP.exists(), why
    z.STOP.unlink()
(fd / "launcher_RESUME").unlink(missing_ok=True)
z.PIN.unlink()
# 25. the owner sees the exact call he approves, whole: a summary cut at 200 characters keeps its end in the detail
#     (review 17/11: "; touch MARKER" was hidden); a call too long for the launcher's screen goes to the terminal only;
#     a decision taken in the terminal withdraws the launcher's request
(fd / "am.log").unlink()
t = z.add("PARKLONG please")
until(lambda: get(t["id"])["state"] == "waiting")
a = get(t["id"])["approval"]
req = json.loads((z.APPROVALS / f"{a['id']}.req").read_text())
assert req["summary"].endswith("…") and "touch MARKER" in req["detail"] and a["screen"], (req, a)
with redirect_stdout(io.StringIO()) as printed:
    z.owner_says_yes = lambda q: True
    z.cmd_approve(t["id"], "approve")
assert "touch MARKER" in printed.getvalue()
until(lambda: get(t["id"])["state"] == "done")
assert f"--es cancel {a['id']}" in (fd / "am.log").read_text()
t = z.add("PARKHUGE please")
until(lambda: get(t["id"])["state"] == "waiting")
a = get(t["id"])["approval"]
assert not a["screen"] and "--es req" not in (fd / "am.log").read_text().split(f"--es cancel")[-1], (fd / "am.log").read_text()[-300:]
assert "trop longue" in (fd / "rish.log").read_text().splitlines()[-1] or "trop longue" in (fd / "rish.log").read_text()
with redirect_stdout(io.StringIO()):
    z.cmd_approve(t["id"], "deny")
until(lambda: get(t["id"])["state"] == "done")
print("zion self-test: OK (25 scenarios)")
