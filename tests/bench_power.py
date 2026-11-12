#!/usr/bin/env python3
"""On the phone, in Termux, UNPLUGGED: battery drain at rest and during local inference, energy per token, temperatures,
throttling, for several llama-server settings. Start it while plugged in: it waits until you unplug, then runs alone.
  python3 bench_power.py MODEL.gguf [--idle-min 20] [--run-min 8] [--cool-min 4] [--configs default,big4,eco2]
Rest window: screen off, no model, no wake lock, readings only at its start and end (polling would wake the phone).
Inference windows: wake lock held, back-to-back answers of 256 tokens, a reading every 15 s taken by a thread WHILE
the model generates (battery current and voltage from /sys through Shizuku, thermal HAL temperatures and status, screen
state). Energy per token comes from the battery's charge counter over the whole window (j_per_token_charge); the mean of
the current readings is only a cross-check. Figures are battery-side, so they include the screen if it is on and every
other app: compare windows, not absolute values. A window during which the phone was seen on a charger, or the screen
awake, is flagged. Nothing here changes a thermal or power setting of Android; the configurations only change
llama-server's own threads. Exit code 3: nobody unplugged the phone in time (the JSON says so).
Writes /sdcard/Download/seeker-zero/bench-power-<model>.json after every window."""
import argparse, http.client, json, os, re, shutil, subprocess, sys, threading, time, urllib.request
from pathlib import Path

CONFIGS = {  # name -> llama-server thread options (cores 4-7 are the Cortex-A78, 0-3 the A55: cpuinfo_max_freq, 12/11)
    "default": ["-t", "4"],                                                   # what seeker-ai used until now
    "big4": ["-t", "4", "-C", "0xF0", "--cpu-strict", "1", "--poll", "0"],   # the 4 big cores, no busy-wait
    "eco2": ["-t", "2", "-C", "0x30", "--cpu-strict", "1", "--poll", "0"],   # 2 big cores
    "big3": ["-t", "3", "-C", "0x70", "--cpu-strict", "1", "--poll", "0"],
}
PROMPTS = ["Explique en détail comment fonctionne un moteur à combustion interne.",
           "Raconte une histoire courte sur un phare au bord de l'océan.",
           "Décris les étapes pour planter un potager sur un balcon.",
           "Explique la différence entre une clé publique et une clé privée."]
ap = argparse.ArgumentParser()
ap.add_argument("model"); ap.add_argument("--idle-min", type=float, default=20); ap.add_argument("--run-min", type=float, default=8)
ap.add_argument("--cool-min", type=float, default=4); ap.add_argument("--configs", default="default,big4,eco2")
ap.add_argument("--no-wait", action="store_true", help="do not wait for unplugging (dry runs)")
ap.add_argument("--wait-h", type=float, default=1, help="how long to wait for the unplugging before giving up")
A = ap.parse_args()
OUT = Path(os.environ.get("BENCH_OUT_DIR", "/sdcard/Download/seeker-zero")) / f"bench-power-{Path(A.model).stem}.json"
RISH = shutil.which("rish") or str(Path.home() / "bin/rish")
SETTLE = float(os.environ.get("BENCH_SETTLE_S", 120))  # after unplugging, before the rest window (dry runs: 0)
SAMPLE_S = float(os.environ.get("BENCH_SAMPLE_S", 15))
PORT = 8093
SERVER = os.environ.get("LLAMA_SERVER", str(Path.home() / "llama.cpp/build-static/bin/llama-server"))
R = {"model": Path(A.model).name, "started": time.strftime("%F %T"), "args": vars(A), "windows": []}
PROBE = ("cd /sys/class/power_supply/battery && echo P $(cat current_now voltage_now charge_counter capacity status); "
         "dumpsys thermalservice | grep -m1 'Thermal Status'; "
         "dumpsys thermalservice | sed -n '/Current temperatures from HAL/,/Current cooling/p' | grep -E 'mName=(CPU|SKIN|BATTERY|SOC)'; "
         "dumpsys power | grep -m1 -o 'mWakefulness=[A-Za-z]*'")


def save():
    OUT.write_text(json.dumps(R, indent=1, ensure_ascii=False))


def probe():
    """One reading. On this phone current_now is in microamps and POSITIVE WHILE CHARGING (12/11 20:01, on the Mac's USB:
    +206 to +319 mA while charge_counter rose 29.5 mAh in 9 min), so the current drawn is its opposite. current_ma and
    power_w below are drawn from the battery: positive = drain. A failed reading is kept as an error, never raised."""
    r = {"t": round(time.time(), 1)}
    try:
        out = subprocess.run([RISH, "-c", PROBE], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        r["error"] = f"{type(e).__name__}: {e}"[:120]
        return r
    text = out.stdout + out.stderr  # rish spreads its output over both at random (tests/phone/rish-probe.log)
    m = re.search(r"P (-?\d+) (\d+) (\d+) (\d+) (\w+)", text)
    if m:
        cur, volt, charge, pct, st = m.groups()
        drawn = -int(cur)
        r.update(current_ma=drawn / 1000, volt=int(volt) / 1e6, charge_mah=int(charge) / 1000, pct=int(pct), status=st,
                 power_w=round(drawn / 1e6 * int(volt) / 1e6, 3))
    m = re.search(r"Thermal Status: (\d)", text)
    r["thermal_status"] = int(m.group(1)) if m else None
    for value, sensor in re.findall(r"mValue=([\d.]+), mType=\d+, mName=(\w+)", text):
        r[f"{sensor.lower()}_c"] = float(value)  # one sensor per name on this phone (dumpsys thermalservice, 12/11)
    m = re.search(r"mWakefulness=(\w+)", text)
    r["screen"] = m.group(1) if m else None
    return r


def plugged():
    try:
        return json.loads(subprocess.run(["termux-battery-status"], capture_output=True, text=True, timeout=30,
                                         stdin=subprocess.DEVNULL).stdout)["plugged"] != "UNPLUGGED"
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return probe().get("status") != "Discharging"  # unreadable counts as plugged: never measure on a charger


def wake_lock(on):
    if shutil.which("termux-wake-lock"):
        subprocess.run(["termux-wake-lock" if on else "termux-wake-unlock"], capture_output=True, timeout=30)


def start_server(opts):
    subprocess.run(["seeker-ai", "--stop"], capture_output=True, stdin=subprocess.DEVNULL, timeout=120)
    (Path.home() / ".cache").mkdir(parents=True, exist_ok=True)
    log = open(Path.home() / f".cache/bench-power-{int(time.time())}.log", "w")
    p = subprocess.Popen([SERVER, "-m", A.model, "-c", "4096", "--jinja", "--host", "127.0.0.1", "--port", str(PORT),
                          "--cache-ram", "0", "--load-mode", "none", *opts], stdout=log, stderr=subprocess.STDOUT)
    for _ in range(300):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2).read()
            return p
        except OSError:
            if p.poll() is not None:
                raise RuntimeError(f"llama-server exited, see {log.name}")
            time.sleep(1)
    p.kill()  # never leave a 3.5 GB orphan that the next window would mistake for its own server
    raise RuntimeError("llama-server did not start")


def generate(i):
    body = {"messages": [{"role": "user", "content": PROMPTS[i % len(PROMPTS)]}], "max_tokens": 256, "temperature": 0.7,
            "seed": i, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        t = json.loads(r.read()).get("timings", {})
    return {"t": round(time.time(), 1), "predicted_n": t.get("predicted_n", 0), "tps": t.get("predicted_per_second"),
            "prompt_n": t.get("prompt_n", 0), "prompt_ms": t.get("prompt_ms")}


def sample_every(w, stop):
    while not stop.wait(SAMPLE_S):  # readings while the model generates, not in the gaps between answers
        w["samples"].append(probe())


def summarize(w):
    readings = [x for x in [w.get("start", {}), *w.get("samples", []), w.get("end", {})] if x]
    w["plugged_seen"] = any(x.get("status") not in (None, "Discharging") for x in readings)  # True: window not valid
    w["screen_awake_seen"] = any(x.get("screen") == "Awake" for x in readings)
    w["probe_errors"] = sum("error" in x for x in readings)
    a, b = w.get("start", {}), w.get("end", {})
    if "charge_mah" in a and "charge_mah" in b and b["t"] > a["t"]:
        hours = (b["t"] - a["t"]) / 3600
        w["drain_ma_from_charge"] = round((a["charge_mah"] - b["charge_mah"]) / hours, 1)
        w["power_w_from_charge"] = round(w["drain_ma_from_charge"] / 1000 * (a.get("volt", 3.85) + b.get("volt", 3.85)) / 2, 3)
        w["pct_per_hour"] = round((a["pct"] - b["pct"]) / hours, 2)
        w["minutes"] = round(hours * 60, 1)
    s = [x for x in w.get("samples", []) if "power_w" in x]
    if s:
        w["power_w_mean"] = round(sum(x["power_w"] for x in s) / len(s), 3)
        for k in ("cpu_c", "skin_c", "battery_c", "soc_c", "thermal_status"):
            vals = [x[k] for x in s if x.get(k) is not None]
            if vals:
                w[f"{k}_max"] = max(vals)
    g = w.get("answers", [])
    if g:
        w["tokens"] = sum(x["predicted_n"] for x in g)
        tps = [x["tps"] for x in g if x["tps"]]
        w["tps_mean"] = round(sum(tps) / len(tps), 2) if tps else None
        w["tps_first_last"] = [tps[0], tps[-1]] if tps else None
        secs = b["t"] - a["t"]
        rest = next((x for x in R["windows"] if x["name"] == "rest"), {})
        if w["tokens"] and w.get("power_w_from_charge") is not None:
            w["j_per_token_charge"] = round(w["power_w_from_charge"] * secs / w["tokens"], 3)
            if rest.get("power_w_from_charge") is not None:
                w["j_per_token_charge_above_rest"] = round((w["power_w_from_charge"] - rest["power_w_from_charge"]) * secs / w["tokens"], 3)
        if w["tokens"] and "power_w_mean" in w:
            w["j_per_token_samples"] = round(w["power_w_mean"] * secs / w["tokens"], 3)  # cross-check only
    w["n_errors"] = len(w.get("errors", []))


def main():
    if not A.no_wait:
        print("waiting until the phone is unplugged (then turn the screen off)...", flush=True)
        t0 = time.time()
        while plugged():
            if time.time() - t0 > A.wait_h * 3600:
                R["aborted"] = f"still plugged after {A.wait_h} h: nothing measured"; save()
                print(R["aborted"], flush=True); sys.exit(3)
            time.sleep(min(15, A.wait_h * 3600))
    subprocess.run(["seeker-ai", "--stop"], capture_output=True, stdin=subprocess.DEVNULL, timeout=120)
    print(f"unplugged: {SETTLE:.0f} s to settle", flush=True)
    time.sleep(SETTLE)
    # rest: two readings only
    w = {"name": "rest", "start": probe()}
    R["windows"].append(w); save()
    end = time.time() + A.idle_min * 60
    while time.time() < end:  # if the phone sleeps deeply, this simply ends later: the duration is measured, not assumed
        time.sleep(min(10, max(1, end - time.time())))  # short naps: a suspended phone stretches each one
    w["end"] = probe(); summarize(w); save()
    print("rest", {k: w.get(k) for k in ("minutes", "drain_ma_from_charge", "power_w_from_charge", "pct_per_hour",
                                         "plugged_seen", "screen_awake_seen")}, flush=True)
    for name in A.configs.split(","):
        wake_lock(True)
        try:
            p = start_server(CONFIGS[name])
        except (RuntimeError, OSError) as e:
            R["windows"].append({"name": name, "error": str(e)}); save(); wake_lock(False); continue
        w = {"name": name, "opts": CONFIGS[name], "start": probe(), "samples": [], "answers": []}
        R["windows"].append(w)
        stop = threading.Event()
        sampler = threading.Thread(target=sample_every, args=(w, stop), daemon=True); sampler.start()
        end, i = time.time() + A.run_min * 60, 0
        try:
            while time.time() < end:
                if p.poll() is not None:  # killed (low memory): stop, do not go on measuring an idle phone
                    w["server_died"] = round(time.time(), 1); break
                try:
                    w["answers"].append(generate(i))
                except (OSError, ValueError, http.client.HTTPException) as e:  # one bad answer must not end the hour
                    w.setdefault("errors", []).append(f"{type(e).__name__}: {e}"[:120])
                    time.sleep(2)
                i += 1
                save()
        finally:
            stop.set(); sampler.join(90)
            w["end"] = probe()
            p.terminate()
            try:
                p.wait(60)
            except subprocess.TimeoutExpired:
                p.kill()
            wake_lock(False)
        summarize(w); save()
        print(name, {k: w.get(k) for k in ("tps_mean", "tps_first_last", "power_w_from_charge", "j_per_token_charge",
                                            "j_per_token_charge_above_rest", "power_w_mean", "cpu_c_max", "skin_c_max",
                                            "thermal_status_max", "n_errors", "server_died", "plugged_seen")}, flush=True)
        if w.get("power_w_mean") and w.get("power_w_from_charge") and not 0.5 <= w["power_w_mean"] / w["power_w_from_charge"] <= 2:
            print(f"WARNING {name}: current readings and charge counter disagree", flush=True)
        cool = {"name": f"cool-after-{name}", "start": probe()}
        R["windows"].append(cool); save()
        time.sleep(A.cool_min * 60)
        cool["end"] = probe(); summarize(cool); save()
    R["done"] = time.strftime("%F %T")
    save()
    print("done ->", OUT, flush=True)


if __name__ == "__main__":
    main()
