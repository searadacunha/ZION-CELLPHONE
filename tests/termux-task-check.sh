#!/data/data/com.termux/files/usr/bin/bash
# Inside Termux, with the model: OPERATOR's task mode for real. Each check is judged on what is on the phone afterwards,
# never on what the model says of itself:
#  1. a programming task: write a script, run it, check its output;
#  2. a task across tools: read a value on a screen (Settings), write it to a file;
#  3. a task killed in the middle (kill -9, as when Android closes Termux), then --task-resume to its end.
# Approvals are answered yes for this run only, in a work folder and a data folder of their own. The busy file is
# written: the launcher's "ai" says it is busy meanwhile.
#   bash tests/termux-task-check.sh > /sdcard/Download/seeker-zero/task-check.log 2>&1
set -u
W=$HOME/seeker-work/task-check-$(date +%H%M%S); mkdir -p "$W"
export SEEKER_AI_DATA=$(mktemp -d) SEEKER_AI_CONFIRM=yes SEEKER_AI_CONFIG=$(mktemp)
printf '{"workdir": "%s", "prefix_cache": false, "show_speed": false}' "$W" > "$SEEKER_AI_CONFIG"
B=$HOME/.cache/seeker-ai/busy; printf '%s\nL IA est occupee par une mesure (task-check).' $$ > "$B"; trap 'rm -f "$B"' EXIT
pass=0; total=3
t() { date +%s; }

echo "== 1. programming task"; s=$(t)
seeker-ai --task "Écris dans le fichier fizz.py un programme Python qui affiche les nombres de 1 à 15, un par ligne, en remplaçant les multiples de 3 par Fizz, ceux de 5 par Buzz et ceux de 15 par FizzBuzz. Exécute-le et vérifie que la dernière ligne affichée est FizzBuzz." 2>&1 | tail -25
out=$(python3 "$W/fizz.py" 2>&1)
if [ "$(echo "$out" | wc -l)" -eq 15 ] && [ "$(echo "$out" | tail -1)" = FizzBuzz ] && [ "$(echo "$out" | sed -n 3p)" = Fizz ]; then pass=$((pass+1)); echo "CHECK 1: OK ($(( $(t)-s )) s)"
else echo "CHECK 1: FAILED ($(( $(t)-s )) s): fizz.py prints: $(echo "$out" | tr '\n' ' ' | cut -c1-200)"; fi

echo "== 2. screen then file"; s=$(t)
seeker-ai --task "Ouvre les paramètres du téléphone à la page À propos du téléphone, lis la version d'Android qui y est écrite, puis écris ce numéro de version dans le fichier version.txt." 2>&1 | tail -25
rish -c "input keyevent 3" >/dev/null 2>&1
if grep -q -w 16 "$W/version.txt" 2>/dev/null; then pass=$((pass+1)); echo "CHECK 2: OK ($(( $(t)-s )) s): version.txt holds $(head -c 80 "$W/version.txt")"
else echo "CHECK 2: FAILED ($(( $(t)-s )) s): version.txt holds: $(head -c 120 "$W/version.txt" 2>&1)"; fi

echo "== 3. killed in the middle, then resumed"; s=$(t)
seeker-ai --task "Crée trois fichiers a.txt, b.txt et c.txt, chacun contenant son propre nom de fichier, puis liste le dossier pour vérifier qu'ils existent." > "$W/killed.log" 2>&1 &
pid=$!; sleep 75; kill -9 $pid 2>/dev/null; wait $pid 2>/dev/null
echo "killed after 75 s; saved state:"; seeker-ai --tasks | tail -2
seeker-ai --task-resume 2>&1 | tail -18
if [ -f "$W/a.txt" ] && [ -f "$W/b.txt" ] && [ -f "$W/c.txt" ] && grep -q "a.txt" "$W/a.txt"; then pass=$((pass+1)); echo "CHECK 3: OK ($(( $(t)-s )) s)"
else echo "CHECK 3: FAILED ($(( $(t)-s )) s): $(ls "$W" | tr '\n' ' ')"; fi

echo "== tasks and reports"; seeker-ai --tasks
for r in "$SEEKER_AI_DATA"/tasks/*.md; do echo "---- $r"; head -40 "$r" | cut -c1-260; done
echo "task-check: $pass of $total checks pass"
