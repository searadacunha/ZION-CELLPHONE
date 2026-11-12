#!/usr/bin/env bash
# Inside Termux, round 5 (final): CPU-only packaged llama.cpp (the Vulkan backend installed for the GPU test was slower),
# CPU features actually used, one static native build attempt, Qwen3.5-4B as default, short final AI check.
# Report: /sdcard/Download/seeker-zero/round5.log
exec > >(tee /sdcard/Download/seeker-zero/round5.log) 2>&1
set -u
B=/sdcard/Download/seeker-zero
install -m 755 $B/ai/seeker-ai $PREFIX/bin/seeker-ai
pkill -f llama-server; sleep 2
M35=~/models/Qwen3.5-4B-Q4_0.gguf
bench() { "$@" -p 512 -n 64 -r 1 -o md 2>&1 | grep -E '\| *(pp|tg)[0-9]|error|failed'; }
echo "== remove the Vulkan backend (installed only for the GPU test)"; pkg uninstall -y llama-cpp-backend-vulkan 2>&1 | tail -1
echo "== CPU features used by the packaged llama.cpp"
timeout 150 llama-server -m $M35 -c 512 --host 127.0.0.1 --port 8099 2>&1 | grep -m1 -E "system_info"; pkill -f "port 8099"; sleep 2
echo "== packaged, CPU only, qwen3.5-4b"; bench llama-bench -m $M35 -t 4 | tee $TMPDIR/p35
echo "== static native build attempt (no shared libraries in ~)"
cd ~/llama.cpp && cmake -B build-static -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DGGML_OPENMP=OFF \
  -DBUILD_SHARED_LIBS=OFF -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF >/dev/null && t0=$SECONDS &&
  cmake --build build-static -j 8 --target llama-bench llama-server 2>&1 | tail -1 && echo "build $((SECONDS - t0))s"
S=~/llama.cpp/build-static/bin
if $S/llama-bench --help >/dev/null 2>&1; then
  echo "static native build OK"; bench $S/llama-bench -m $M35 -t 4 | tee $TMPDIR/s35
else
  echo "STATIC NATIVE BUILD FAILED"; $S/llama-bench --help 2>&1 | head -3
fi
echo "== final configuration"
python - "$TMPDIR" "$S/llama-server" <<'PY'
import json, pathlib, re, sys
tmp, static = pathlib.Path(sys.argv[1]), sys.argv[2]
def speeds(f):
    t = f.read_text() if f.exists() else ""
    v = {k: float(m.group(1)) for k in ("pp512", "tg64") for m in [re.search(rf"{k} \| +([\d.]+)", t)] if m}
    return v if len(v) == 2 else None
cost = lambda s: 60 / s["pp512"] + 60 / s["tg64"]
p, s = speeds(tmp / "p35"), speeds(tmp / "s35")
use_static = bool(p and s and cost(s) < 0.9 * cost(p))
c = pathlib.Path.home() / ".config/seeker-ai/config.json"
conf = json.loads(c.read_text())
conf.update(model="~/models/Qwen3.5-4B-Q4_0.gguf", llama_server=static if use_static else "llama-server", server_args=[])
c.write_text(json.dumps(conf, indent=2, ensure_ascii=False))
print("packaged:", p, "static native:", s, "-> server:", conf["llama_server"], "model:", conf["model"])
PY
echo "== final AI check (approval-gated tools answered no)"
export SEEKER_AI_CONFIRM=no
D=~/.local/share/seeker-ai; mark=$(wc -l < $D/perf.jsonl)
t0=$SECONDS; seeker-ai "Réponds seulement: prêt."; echo "cold start incl. model load and prompt cache: $((SECONDS - t0))s"
for q in "Quelle est la capitale du Portugal ? Un mot." \
         "Écris en Python une fonction qui inverse une chaîne, montre seulement le code." \
         "Envoie-moi une notification sur le téléphone avec le texte : SEEKER ZERO opérationnel." \
         "Quel est le niveau de batterie du téléphone ?"; do
  echo; echo "### $q"; t0=$SECONDS; seeker-ai "$q"; echo "(${SECONDS}s)"
done
for pid in $(pgrep -f llama-server); do grep VmRSS /proc/$pid/status | sed "s/^/llama-server /"; done
tail -n +$((mark + 1)) $D/perf.jsonl | python -c '
import json, sys
rows = [json.loads(l) for l in sys.stdin if l.strip()]
g = [r["predicted_per_second"] for r in rows]; p = [r["prompt_per_second"] for r in rows]
print("generation mean %.1f tok/s (min %.1f, max %.1f), prompt mean %.1f tok/s, %d calls" % (sum(g)/len(g), min(g), max(g), sum(p)/len(p), len(rows)))'
seeker-dash --once 2>&1 | sed -n '1,6p'
echo "== round5 done"
