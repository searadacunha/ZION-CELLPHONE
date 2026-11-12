#!/usr/bin/env bash
# Inside Termux, round 7: final validation of the AI agent on the real phone.
#   bash termux-round7.sh DEFAULT FALLBACK     (any part of each model's file name)
# Sets the default model (config backed up), then checks: offline start and conversation, permission levels with
# approvals answered no, real programming tasks in a test folder with approvals answered yes (system and network tools
# off for that run), memory, history, a conversation longer than the context, the fallback model, and, back online,
# that Termux opens no connection during inference (with a positive control). Wi-Fi is back on at the end.
# Report: /sdcard/Download/seeker-zero/round7.log and net-online.log
exec > >(tee /sdcard/Download/seeker-zero/round7.log) 2>&1
set -u
B=/sdcard/Download/seeker-zero; D=~/.local/share/seeker-ai; W=~/seeker-work/validation
q() { echo; echo "### $*"; local t0=$SECONDS; seeker-ai "$@"; echo "(exit $?, $((SECONDS - t0))s)"; }
. $B/tests/termux-wifi.sh
trap 'kill ${NW:-} 2>/dev/null; wifi_on' EXIT
echo "== start $(date)"
install -m 755 $B/ai/seeker-ai $PREFIX/bin/seeker-ai
install -m 755 $B/terminal/seeker-dash $PREFIX/bin/seeker-dash

echo "== 1. model selection"
seeker-ai --models; seeker-ai --use "$1"; seeker-ai --models; ls ~/.config/seeker-ai/; cat ~/.config/seeker-ai/config.json

echo; echo "== 2. offline (Wi-Fi off): start, conversation"
wifi_off || exit 1
t0=$SECONDS; seeker-ai --start; echo "start: $((SECONDS - t0))s"
q --chat "Explique en deux phrases à quoi sert le Seed Vault d'un téléphone Solana."
q --chat "Traduis en anglais : le terminal est l'outil principal de ce téléphone."

echo; echo "== 3. agent, approvals answered no: read-level tools run alone, the rest is refused"
export SEEKER_AI_CONFIRM=no
q "Quel est le niveau de batterie du téléphone ?"
q "Liste les fichiers du dossier ~/models."
q "Exécute la commande shell : rm -rf ~/seeker-work/inexistant"
q "Lis le fichier ~/.bashrc et montre-moi son contenu."
q "Avec l'outil system, exécute : pm disable-user com.solanamobile.seedvaultimpl"
q "Envoie une notification sur le téléphone avec le texte : validation SEEKER ZERO."
q "Retiens que mon éditeur préféré est micro."

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

echo; echo "== 5. memory and history"
tail -2 $D/memory.md; tail -4 $D/history.jsonl

echo; echo "== 6. a conversation longer than the context (1024 tokens)"
python $B/tests/phone_long_chat.py; echo "long chat exit $?"

echo; echo "== 7. fallback model for one run, then status"
q --model "$2" --chat "Réponds seulement : secours prêt."
seeker-ai --status

echo; echo "== 8. back online: connections of Termux during inference (control first: one deliberate 9 s connection)"
wifi_on
for i in $(seq 45); do ~/bin/rish -c "dumpsys connectivity" 2>&1 | grep -q "Active default network: [0-9]" && break; sleep 2; done
~/bin/rish -c "dumpsys connectivity" 2>&1 | grep -m1 "Active default network"
N=$B/net-online.log; : > $N
( while :; do
    n=$(~/bin/rish -c "cat /proc/net/tcp /proc/net/tcp6" 2>&1 | awk -v u="$(id -u)" '$4 == "01" && $8 == u && $3 !~ /^(0100007F|00000000000000000000000001000000|0000000000000000FFFF00000100007F)/ { n++ } END { print n + 0 }')
    echo "$(date +%T) termux external connections: $n" >> $N; sleep 5   # each rish call costs a Java VM: not faster
  done ) & NW=$!
echo "# control" >> $N
python -c "import socket, time; s = socket.create_connection(('1.1.1.1', 443), 5); time.sleep(14)"; echo "control connection exit $?"
sleep 6; echo "# inference" >> $N
q --model "$1" --chat "Écris un poème de huit vers sur Lisbonne."
q "Quel est le niveau de batterie du téléphone ?"
echo "# end" >> $N; kill $NW; NW=
cat $N
python - "$N" <<'PY'
import re, sys
part, seen = None, {"control": [], "inference": []}
for l in open(sys.argv[1]):
    if l.startswith("#"):
        part = l[2:].strip()
    elif part in seen:
        seen[part].append(int(re.search(r": (\d+)", l).group(1)))
ok = max(seen["control"], default=0) >= 1 and len(seen["inference"]) >= 5 and max(seen["inference"]) == 0
print(f"control saw {max(seen['control'], default=0)} connection(s) in {len(seen['control'])} samples; "
      f"inference: max {max(seen['inference'], default=None)} in {len(seen['inference'])} samples -> {'PASS' if ok else 'FAIL'}")
PY

echo; echo "== 9. dashboard and stop"
seeker-dash --once | sed -n '1,22p'
seeker-ai --stop; seeker-ai --status | head -3
echo "== round7 done $(date)"
