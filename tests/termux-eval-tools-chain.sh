#!/data/data/com.termux/files/usr/bin/bash
# Inside Termux: measure how reliably each local model makes OPERATOR's tool calls (tests/eval_tools.py, decision rule P6,
# applied afterwards by `python3 tests/bench_decide.py --p6 $D/results`). One model at a time:
#   seeker-ai --model NAME --start (a child of this script, so OPERATOR's busy guard lets it load), eval_tools.py, seeker-ai --stop.
# Usage: bash termux-eval-tools-chain.sh [MODEL.gguf ...]   (default: every model `seeker-ai --models` lists)
# Heavy steps wait while the battery is under 25 % (CHAIN_MIN_PCT) and for the battery to cool to 38 C (CHAIN_COOL_C).
# A finished model leaves $D/chain-done/evaltools-NAME, so a re-run skips it. Everything goes to $D: eval-tools-chain.log,
# eval-tools-summary.txt, results/evaltools-NAME.json.
D=${CHAIN_DIR:-/sdcard/Download/seeker-zero}; LOG=$D/eval-tools-chain.log; RISH=${RISH:-$HOME/bin/rish}
NAP=${CHAIN_NAP:-300}; MIN=${CHAIN_MIN_PCT:-25}; COOL=${CHAIN_COOL_C:-38}; TIMEOUT=${EVAL_TOOLS_TIMEOUT:-240}  # dry runs set the waits to 0
BUSY=${SEEKER_AI_BUSY:-$HOME/.cache/seeker-ai/busy}
mkdir -p "$D/chain-done" "$D/results" "${BUSY%/*}"
# another live chain holds the memory: two models do not fit (12/11: Android closed Termux)
if [ -f "$BUSY" ]; then
  other=$(head -1 "$BUSY"); [ -n "$other" ] && [ "$other" != "$$" ] && kill -0 "$other" 2>/dev/null &&
    { echo "busy: job $other holds the memory ($BUSY), nothing started" >&2; exit 1; }
fi
exec >> "$LOG" 2>&1 </dev/null  # termux-api, rish and seeker-ai read stdin: nothing here may give them a list to eat

step() { echo; echo "== $(date '+%F %T') $*"; }
note() { echo "$(date '+%F %T') $*" | tee -a "$D/eval-tools-summary.txt"; }
done_() { [ -f "$D/chain-done/$1" ]; }
bat() { timeout 30 termux-battery-status | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["percentage"], d["plugged"], d["temperature"])' 2>/dev/null; }
notify() {  # the text goes inside single quotes for rish's shell: escape the apostrophes
  local m=${1//\'/\'\\\'\'}
  timeout 30 "$RISH" -c "cmd notification post -S bigtext -t 'ZION ZERO' zion_eval_tools '$m'" >/dev/null 2>&1
  echo "$(date +%T) notify rc=$?: $1"; }
guard() {  # until the battery is >= $1 %, at most 240 min (heavy work draws more than the Mac's USB gives)
  local t0=$SECONDS p plug t
  while :; do
    read -r p plug t <<<"$(bat)"
    [ -n "$p" ] && [ "$p" -ge "$1" ] && return 0
    [ $(( (SECONDS - t0) / 60 )) -ge 240 ] && { echo "$(date +%T) battery ${p:-unreadable}% ($plug) after 240 min: going on"; return 1; }
    echo "$(date +%T) battery ${p:-unreadable}% ($plug): waiting for $1 %"; seeker-ai --stop >/dev/null 2>&1; sleep "$NAP"
  done; }
cool() {  # battery at or under $COOL C, at most $1 s: each model starts as cool as the one before
  local i p plug t
  for ((i = 0; i < $1; i += 10)); do
    read -r p plug t <<<"$(bat)"
    python3 -c "import sys; sys.exit(0 if float('${t:-99}') <= $COOL else 1)" && break
    echo "$(date +%T) cool waiting: battery ${t:-?} C (> $COOL)"; sleep $((NAP > 0 ? 10 : 0))
  done
  echo "$(date +%T) cool: battery ${t:-?} C after ${i}s"; }

if [ $# -gt 0 ]; then LIST=$(printf '%s\n' "$@")
else LIST=$(seeker-ai --models 2>/dev/null | sed 's/^[* ] //' | awk '$1 ~ /\.gguf$/ {print $1}'); fi
[ -n "$LIST" ] || { note "no model to measure"; exit 1; }

printf '%s\n%s\n' "$$" "Mesures ZION ZERO en cours : l'IA est en pause jusqu'à la notification « Mesures des appels d'outils finies ». Deux modèles ne tiennent pas en mémoire, Android fermerait Termux et arrêterait les mesures." > "$BUSY"
trap 'rm -f "$BUSY"; termux-wake-unlock; [ -f "$D/chain-done/evaltools-all" ] || notify "Mesures des appels d outils arrêtées avant la fin : voir eval-tools-chain.log."' EXIT
rm -f "$D/chain-done/evaltools-all"  # "all" = this run reached its end, failures or not (the exit notification)
termux-wake-lock
step "start, battery $(bat)"
n=0; ko=0
while read -r -u 3 file; do
  name=${file%.gguf}
  done_ "evaltools-$name" && continue
  guard "$MIN"; cool 600; step "$name: eval_tools, battery $(bat)"
  if seeker-ai --model "$file" --start >/dev/null 2>&1 && python3 "$D/tests/eval_tools.py" --out "$D/results/evaltools-$name.json" --timeout "$TIMEOUT"; then
    touch "$D/chain-done/evaltools-$name"; note "evaltools-$name: OK"; n=$((n + 1))
  else
    note "evaltools-$name: FAILED (see eval-tools-chain.log)"; ko=$((ko + 1))
  fi
  seeker-ai --stop >/dev/null 2>&1
done 3<<<"$LIST"

step "done"
touch "$D/chain-done/evaltools-all"
note "evaltools: $n measured, $ko failed"
notify "Mesures des appels d'outils finies ($n modèles, $ko en échec). Résultat : python3 tests/bench_decide.py --p6 $D/results"
