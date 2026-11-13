#!/data/data/com.termux/files/usr/bin/bash
# Inside Termux, started once from the Mac: the remaining measurements run alone, so the phone may leave the Mac for a
# wall charger. Order (the owner's choice, 12/11: battery test before the model benches):
#   1 battery test (tests/bench_power.py) as soon as the battery is >= 70 %: a notification (and a buzz) asks to unplug,
#     another one to plug back in; if nobody unplugs within 2 h it is tried again at the very end
#   2 speed sweep (llama-bench)   3 model downloads   4 French eval + quick agent bench, every model (cooled down first)
# Heavy steps wait while the battery is under 25 % (CHAIN_MIN_PCT). A finished step leaves $D/chain-done/<step>, so a re-run skips it.
# Everything goes to $D: chain.log, chain-summary.txt and each step's own files.
D=${CHAIN_DIR:-/sdcard/Download/seeker-zero}; LOG=$D/chain.log; RISH=${RISH:-$HOME/bin/rish}
NAP=${CHAIN_NAP:-300}; RETRY=${CHAIN_RETRY_S:-60}  # dry runs (tests/test_chain_dry.sh) set them to 0
# battery floor of the heavy steps: MediaTek's battery-percentage throttling (bp-thl, present on this phone) caps the
# CPU at low charge, usually from 15 %: a model measured there would look slower than one measured earlier
MIN=${CHAIN_MIN_PCT:-25}
mkdir -p "$D/chain-done"
exec >> "$LOG" 2>&1 </dev/null  # termux-api, rish and llama-bench read stdin: nothing here may give them a list to eat
MODELS='hauhau-q4km HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf
qwen35-q40 unsloth/Qwen3.5-4B-GGUF Qwen3.5-4B-Q4_0.gguf
qwen3-2507-q40 unsloth/Qwen3-4B-Instruct-2507-GGUF Qwen3-4B-Instruct-2507-Q4_0.gguf
ministral3-q40 unsloth/Ministral-3-3B-Instruct-2512-GGUF Ministral-3-3B-Instruct-2512-Q4_0.gguf
granite4micro-q40 ibm-granite/granite-4.0-micro-GGUF granite-4.0-micro-Q4_0.gguf'

step() { echo; echo "== $(date '+%F %T') $*"; }
note() { echo "$(date '+%F %T') $*" | tee -a "$D/chain-summary.txt"; }
mark() { touch "$D/chain-done/$1"; note "$1: OK"; }
done_() { [ -f "$D/chain-done/$1" ]; }
pct() { timeout 30 termux-battery-status | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["percentage"], d["plugged"])' 2>/dev/null; }
notify() {  # the text goes inside single quotes for rish's shell: escape the apostrophes ("l'écran")
  local m=${1//\'/\'\\\'\'} buzz="" h=$((10#$(date +%H)))
  [ "$h" -ge 8 ] && [ "$h" -lt 23 ] && buzz="; cmd vibrator_manager synced oneshot 800"  # no buzz at night
  timeout 30 "$RISH" -c "cmd notification post -S bigtext -t 'ZION ZERO' zion_chain '$m'$buzz" >/dev/null 2>&1
  echo "$(date +%T) notify rc=$?: $1"; }
guard() {  # until the battery is >= $1 % (heavy work draws ~2.6 W, more than the Mac's USB gives), at most $2 min
  local t0=$SECONDS p plug
  while :; do
    read -r p plug <<<"$(pct)"
    [ -n "$p" ] && [ "$p" -ge "$1" ] && return 0
    [ $(( (SECONDS - t0) / 60 )) -ge "${2:-240}" ] && { echo "$(date +%T) battery ${p:-unreadable}% ($plug) after ${2:-240} min: going on"; return 1; }
    echo "$(date +%T) battery ${p:-unreadable}% ($plug): waiting for $1 %"; seeker-ai --stop >/dev/null 2>&1; sleep "$NAP"
  done; }
wait_plugged() {  # at most $1 min
  local t0=$SECONDS p plug
  while read -r p plug <<<"$(pct)"; [ "${plug:-UNPLUGGED}" = UNPLUGGED ] && [ $(( (SECONDS - t0) / 60 )) -lt "$1" ]; do sleep 60; done
  echo "$(date +%T) battery ${p:-?}% ($plug)"; }
cool() {  # thermal status 0 and CPU under 55 C, at most $1 s: each model starts as cool as the one before
  local i s st c
  for ((i = 0; i < $1; i += 10)); do
    s=$(timeout 30 "$RISH" -c "dumpsys thermalservice | grep -m1 'Thermal Status'; dumpsys thermalservice | grep -o 'mValue=[0-9.]*, mType=[0-9]*, mName=CPU'" 2>&1)
    st=$(grep -o 'Thermal Status: [0-9]' <<<"$s" | grep -o '[0-9]$'); c=$(grep -o 'mValue=[0-9]*' <<<"$s" | head -1 | grep -o '[0-9]*$')
    [ "${st:-9}" = 0 ] && [ "${c:-99}" -lt 55 ] && break; sleep 10
  done
  echo "$(date +%T) cool: status=${st:-?} cpu=${c:-?}C after ${i}s"; }
battery_test() {  # $1: minutes to wait for 70 %, $2: hours to wait for the unplugging
  done_ battery || done_ battery-failed && return 0
  step "battery test: waiting for 70 % (at most $1 min)"
  guard 70 "$1" || { note "battery: postponed (under 70 %)"; return 1; }
  seeker-ai --stop >/dev/null 2>&1
  notify "Test batterie : débranche le téléphone et éteins l'écran (environ 75 min). Une autre notification dira quand le rebrancher."
  termux-wake-unlock  # the rest window must be a real rest: bench_power holds its own wake lock only while generating
  python3 "$D/tests/bench_power.py" "$HOME/models/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf" --configs default,big4,eco2 --wait-h "$2"
  local rc=$?; termux-wake-lock
  [ $rc = 3 ] && { note "battery: nobody unplugged within $2 h"; return 1; }
  [ $rc = 0 ] && mark battery || { touch "$D/chain-done/battery-failed"; note "battery: FAILED rc=$rc (see chain.log)"; }
  notify "Test batterie fini : rebranche le téléphone au chargeur."
  wait_plugged 60; }

# OPERATOR loads no model while this file names a live chain (12/11 21:08: a 2nd model got Termux closed, the chain with it)
BUSY=${SEEKER_AI_BUSY:-$HOME/.cache/seeker-ai/busy}
mkdir -p "${BUSY%/*}" && printf '%s\n%s\n' "$$" "Mesures ZION ZERO en cours : l'IA est en pause jusqu'à la notification « Mesures ZION ZERO finies ». Deux modèles ne tiennent pas en mémoire, Android fermerait Termux et arrêterait les mesures." > "$BUSY"
trap 'rm -f "$BUSY"; termux-wake-unlock; [ -f "$D/chain-done/all" ] || notify "Mesures ZION ZERO arrêtées avant la fin : voir chain.log."' EXIT
termux-wake-lock
step "start, battery $(pct)"
battery_test "${CHAIN_BATTERY_WAIT_MIN:-120}" 2  # 0: do not wait for 70 % now, keep the test for the end

step "speed sweep"
if ! done_ sweep; then guard "$MIN"; cool 300; bash "$D/tests/termux-p6-sweep.sh" && mark sweep || note "sweep: FAILED rc=$?"; fi

step "model downloads"
while read -r -u 3 label repo file; do
  for try in 1 2 3; do bash "$D/ai/install-model.sh" "$repo" "$file" && break; echo "install $file failed (try $try)"; sleep "$RETRY"; done
done 3<<<"$MODELS"

while read -r -u 3 label repo file; do
  done_ "model-$label" && continue
  [ -f "$HOME/models/$file" ] || { note "model-$label: MISSING $file"; continue; }
  ok=1
  guard "$MIN"; cool 600; step "$label: eval_fr, battery $(pct)"
  if seeker-ai --model "$file" --start >/dev/null 2>&1; then python3 "$D/tests/eval_fr.py" --label "$label" || ok=0; else ok=0; fi
  seeker-ai --stop >/dev/null 2>&1
  guard "$MIN"; cool 600; step "$label: bench_agent --quick, battery $(pct)"
  python3 "$D/tests/bench_agent.py" "$HOME/models/$file" --label "$label-v4" --quick > "$D/bench-$label-v4.out" 2>&1 || ok=0
  tail -25 "$D/bench-$label-v4.out"
  [ $ok = 1 ] && mark "model-$label" || note "model-$label: FAILED (see chain.log and bench-$label-v4.out)"
done 3<<<"$MODELS"

battery_test 600 10  # second chance when nobody unplugged the first time
bt="non fait"; done_ battery && bt=fait; done_ battery-failed && bt="échoué"; note "battery: $bt"
step "done"
touch "$D/chain-done/all"
n=$(ls "$D/chain-done" | grep -c '^model-')
notify "Mesures ZION ZERO finies ($n modèles sur 5, test batterie : $bt). Tu peux rebrancher le téléphone au Mac."
