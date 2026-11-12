#!/usr/bin/env bash
# Inside Termux, round 3: why is prompt processing slow? (1) pin threads on the 4 Cortex-A78 cores, (2) build llama.cpp
# natively (dotprod) from the official release tag. Then point seeker-ai at the fastest setup and rerun the AI test.
# Report: /sdcard/Download/seeker-zero/round3.log
exec > >(tee /sdcard/Download/seeker-zero/round3.log) 2>&1
set -u
TAG=b12284
B=/sdcard/Download/seeker-zero
install -m 755 $B/ai/seeker-ai $PREFIX/bin/seeker-ai
cp $B/tests/termux-ai-test.sh ~/
echo "== shizuku"; ~/bin/rish -c id 2>&1 | head -2
pkill -f llama-server; sleep 2
M3=~/models/Qwen3-4B-Instruct-2507-Q4_0.gguf
M35=~/models/Qwen3.5-4B-Q4_0.gguf
bench() { "$@" -p 512 -n 64 -r 1 -o md 2>&1 | grep -E '\| *(pp|tg)[0-9]|error|invalid|unknown'; }
echo "== big cores: $(for c in /sys/devices/system/cpu/cpu[0-7]; do echo -n "$(basename $c):$(cat $c/cpufreq/cpuinfo_max_freq 2>/dev/null) "; done)"
echo "== packaged build, pinned on cpu4-7"
bench llama-bench -m $M3 -t 4 --cpu-mask 0xF0 --cpu-strict 1

echo "== native build of llama.cpp $TAG"
pkg install -y ninja >/dev/null 2>&1
cd ~ && { [ -d llama.cpp ] || git clone -q --depth 1 --branch $TAG https://github.com/ggml-org/llama.cpp; }
cd ~/llama.cpp && git log -1 --format='commit %h %cd'
t0=$SECONDS
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF >/dev/null &&
  cmake --build build -j 8 --target llama-server llama-bench 2>&1 | tail -2
echo "build time: $((SECONDS - t0))s"
N=~/llama.cpp/build/bin
$N/llama-bench --help >/dev/null 2>&1 && echo "native build OK" || echo "NATIVE BUILD FAILED"
echo "== native, 4 threads"; bench $N/llama-bench -m $M3 -t 4
echo "== native, pinned cpu4-7"; bench $N/llama-bench -m $M3 -t 4 --cpu-mask 0xF0 --cpu-strict 1
echo "== native, qwen3.5, pinned"; bench $N/llama-bench -m $M35 -t 4 --cpu-mask 0xF0 --cpu-strict 1
echo "== round3 benches done"
