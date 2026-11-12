#!/data/data/com.termux/files/usr/bin/bash
# Inside Termux, plugged in: llama-bench speed (prompt 512, generation 128, 2 runs) for thread layouts, after cooling down
# each time (thermal status 0 and CPU under 55 C, or 3 min). Cores 4-7 = Cortex-A78, 0-3 = A55.
# stdin of rish and llama-bench is /dev/null: they read it, and ate the loop's list after the first line (12/11).
OUT=/sdcard/Download/seeker-zero/p6-sweep.jsonl; LOG=/sdcard/Download/seeker-zero/p6-sweep.log
exec > "$LOG" 2>&1; : > "$OUT"
seeker-ai --stop </dev/null
B=~/llama.cpp/build-static/bin/llama-bench
cool() { for i in $(seq 1 36); do s=$(timeout 30 ~/bin/rish </dev/null -c "dumpsys thermalservice | grep -m1 'Thermal Status'; dumpsys thermalservice | sed -n '/Current temperatures from HAL/,/Current cooling/p' | grep 'mName=CPU'" 2>&1)
  st=$(grep -o 'Thermal Status: [0-9]' <<<"$s" | grep -o '[0-9]$'); c=$(grep -o 'mValue=[0-9]*' <<<"$s" | head -1 | grep -o '[0-9]*$')
  [ "${st:-9}" = 0 ] && [ "${c:-99}" -lt 55 ] && break; sleep 5; done; echo "cool: status=$st cpu=${c}C after $((i*5))s"; }
for m in Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf Qwen3.5-4B-Q4_0.gguf; do
  while read -r name opts; do
    cool; echo "== $(date +%T) $m $name: $opts"
    $B -m ~/models/$m -p 512 -n 128 -r 2 -o jsonl $opts </dev/null 2>>"$LOG.err" | sed "s/^{/{\"cfg\":\"$name\",/" | tee -a "$OUT"
    echo "llama-bench exit ${PIPESTATUS[0]}"  # a config that fails leaves this line, not silence
  done <<'CFG'
t4-default -t 4
t4-big-poll0 -t 4 -C 0xF0 --cpu-strict 1 --poll 0
t4-big-poll50 -t 4 -C 0xF0 --cpu-strict 1 --poll 50
t3-big-poll0 -t 3 -C 0x70 --cpu-strict 1 --poll 0
t2-big-poll0 -t 2 -C 0x30 --cpu-strict 1 --poll 0
t8-all -t 8
CFG
done
echo "== done $(date +%T)"
