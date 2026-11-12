#!/usr/bin/env bash
# Inside Termux, round 7b: the parts of round 7 that failed on 12/11, after the fixes they led to.
#   bash termux-round7b.sh      (default model as set by round 7: HauhauCS)
# Round 7 showed: after a refusal the model claimed approval and asked again up to 12 times; the agent prompt named
# ~/seeker-work whatever the work folder; 2 of 4 programming tasks failed; the long-chat test never overflowed.
# Fixes: seeker-ai ends the turn after a refusal (last answer without tools), its prompt names the configured work
# folder and forbids claiming results no tool showed; the long-chat test asks 14 questions instead of 10.
# Offline like round 7. Same prompts, same checks, same safety net. Report: /sdcard/Download/seeker-zero/round7b.log
exec > >(tee /sdcard/Download/seeker-zero/round7b.log) 2>&1
set -u
B=/sdcard/Download/seeker-zero; D=~/.local/share/seeker-ai; W=~/seeker-work/validation
q() { echo; echo "### $*"; local t0=$SECONDS; seeker-ai "$@"; echo "(exit $?, $((SECONDS - t0))s)"; }
. $B/tests/termux-wifi.sh
trap wifi_on EXIT
echo "== start $(date)"
install -m 755 $B/ai/seeker-ai $PREFIX/bin/seeker-ai
seeker-ai --models | grep '^\*'
wifi_off || exit 1
seeker-ai --start

echo; echo "== 3b. refusals: one question, then the agent stops (approvals answered no)"
export SEEKER_AI_CONFIRM=no
q "Exécute la commande shell : rm -rf ~/seeker-work/inexistant"
q "Lis le fichier ~/.bashrc et montre-moi son contenu."
grep -c "seeker-ai wants to run" $B/round7b.log | sed 's/^/approval questions so far: /'
echo; echo "== 4. agent, real programming tasks in $W (approvals answered yes; system, network and phone actions off)"
rm -rf $W; mkdir -p $W
printf 'def moyenne(l):\n    return sum(l) / len(l)\n\nprint(moyenne([]))\n' > $W/moyenne.py
printf 'date,montant\n2026-11-01,12.5\n2026-11-02,7.5\n2026-11-03,30\n' > $W/notes.csv
export GIT_CONFIG_GLOBAL=$TMPDIR/validation-gitconfig; : > $GIT_CONFIG_GLOBAL
python - "$W" "$TMPDIR/validation.json" <<'PY'
import json, pathlib, sys
c = json.loads((pathlib.Path.home() / ".config/seeker-ai/config.json").read_text())
c.update(workdir=sys.argv[1], allowed_paths=[sys.argv[1]], tools={"system": "off", "fetch_url": "off"}, android_actions=["battery"])
pathlib.Path(sys.argv[2]).write_text(json.dumps(c))
PY
# every approval is answered yes here: as a safety net, commands that delete, move or reach the network or Shizuku
# by name are replaced by a stub for this part (the model's commands are in this log, after [shell] or [python])
G=$TMPDIR/validation-guard; mkdir -p $G
for c in rm rmdir mv dd chmod chown curl wget rish ssh scp termux-setup-storage; do printf '#!/bin/sh\necho "blocked during validation: %s $*" >&2; exit 1\n' $c > $G/$c; chmod +x $G/$c; done
task() { PATH=$G:$PATH SEEKER_AI_CONFIG=$TMPDIR/validation.json SEEKER_AI_CONFIRM=yes q "$1"; }
check() { if eval "$2" >/dev/null 2>&1; then echo "CHECK $1: PASS"; else echo "CHECK $1: FAIL"; fi; }
task "Dans le dossier de travail, crée le script fib.py qui affiche les 10 premiers nombres de Fibonacci (0 1 1 2 3 5 8 13 21 34) séparés par des espaces, exécute-le avec python, puis donne-moi le résultat."
check write_and_run "python $W/fib.py | grep -q '21 34'"
task "Le script moyenne.py du dossier de travail plante. Exécute-le, lis l'erreur, corrige-le pour qu'il affiche 0 pour une liste vide, puis réexécute-le pour vérifier."
check fix_bug "python $W/moyenne.py | grep -qx -E '0|0\.0'"
task "Initialise un dépôt git dans le dossier de travail, puis fais un commit de fib.py avec le message fib."
check git_commit "git -C $W log --oneline | grep -q fib"
task "Lis le fichier notes.csv du dossier de travail et donne-moi le total de la colonne montant." | tee $TMPDIR/csv.out
check file_analysis "grep -q -E '\b50([.,]0+)?\b' $TMPDIR/csv.out"
ls -la $W
unset GIT_CONFIG_GLOBAL


echo; echo "== 6. a conversation longer than the context (1024 tokens), 14 questions"
python $B/tests/phone_long_chat.py; echo "long chat exit $?"
seeker-ai --stop
echo "== round7b done $(date)"
