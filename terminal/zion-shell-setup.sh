#!/data/data/com.termux/files/usr/bin/bash
# Inside Termux (termux-setup.sh runs it, safe to re-run). Since 13/11 ("ia c'est réponse humaine, terminal c'est
# termux"), Termux is a plain terminal and the ZION ZERO launcher's "ai" is a screen of its own, answered by OPERATOR in
# the background. This script:
#  - takes out the line that the versions of 12-13/11 added last to ~/.bashrc and ~/.zshrc (OPERATOR opened in every new
#    session): the file comes back byte for byte when nothing else changed in it since, else only that line goes;
#  - puts the launcher's "dashboard" and "ai-start" scripts in ~/.shortcuts;
#  - runs OPERATOR's service (zion-ai-serve = seeker-ai --serve) in the background: at each start of the phone
#    (~/.termux/boot, run by Termux at BOOT_COMPLETED), from Termux's job scheduler every 15 minutes (job 7301; it exits
#    at once while the service runs) and now (job 7302), in place of a service already running (it keeps the code it
#    started with). Started in the background, a job needs Termux exempt from battery optimization (done 11/11 here).
# Undo: add --remove (scripts, service and jobs go; ~/.bashrc and ~/.zshrc stay as they are).
set -euo pipefail
: "${PREFIX:?run this inside Termux}"
SRC=$(cd "$(dirname "$0")" && pwd)
TAG='# ZION ZERO: OPERATOR on new sessions'
remove=; [ "${1:-}" = --remove ] && remove=1

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [ -f "$rc" ] && grep -q -F "$TAG" "$rc" || continue
  tmp=$rc.zion-tmp bak=$rc.zion-backup
  grep -v -F "$TAG" "$rc" > "$tmp" || true
  if [ -f "$bak" ] && ! grep -q -F -e "$TAG" -e '# >>> ZION AI AUTOSTART >>>' "$bak" && grep -v -F "$TAG" "$bak" | cmp -s - "$tmp"; then
    cat "$bak" > "$rc"   # untouched since that setup: back byte for byte (blank lines, last newline)
  elif [ ! -s "$tmp" ] && { [ ! -f "$bak" ] || grep -q -F "$TAG" "$bak"; }; then
    rm -f "$rc"          # only that line was in it: that setup had created the file
  else
    cat "$tmp" > "$rc"   # edited since (aliases...): only that line goes
  fi
  rm -f "$tmp"
done
rm -f "$PREFIX/share/zion/autostart.sh" "$HOME/.config/zion/autostart-off" "$HOME/.shortcuts/operator" "$HOME/.shortcuts/terminal"
rmdir "$PREFIX/share/zion" "$HOME/.config/zion" 2>/dev/null || true

if [ -n "$remove" ]; then
  for j in 7301 7302; do termux-job-scheduler --cancel --job-id "$j" >/dev/null 2>&1 || true; done
  pkill -f 'seeker-ai --serve' || true
  pkill -f 'zion run' || true
  rm -f "$PREFIX/bin/zion-ai-serve" "$PREFIX/bin/operator" "$HOME/.shortcuts/dashboard" "$HOME/.shortcuts/ai-start" \
    "$HOME/.shortcuts/zion-stop" "$HOME/.termux/boot/zion-ai-serve" "$PREFIX/bin/zion" "$PREFIX/bin/zion-stop" "$PREFIX/bin/zion-guard"
  echo "ZION ZERO shell setup removed (kept: ~/.config/zion (policy, approval key), ~/.local/state/zion (journal, queue);"
  echo "backups kept: ~/.bashrc.zion-backup, ~/.zshrc.zion-backup)"
  exit 0
fi
install -d "$HOME/.shortcuts"
for s in dashboard ai-start zion-stop; do install -m 700 "$SRC/shortcuts/$s" "$HOME/.shortcuts/$s"; done
install -m 755 "$SRC/zion-ai-serve" "$PREFIX/bin/zion-ai-serve"
# zion: the supervisor (queue, approvals, journal); zion-stop: the emergency stop; zion-guard: the threat check
install -m 755 "$SRC/../ai/zion" "$PREFIX/bin/zion"
install -m 755 "$SRC/zion-stop" "$PREFIX/bin/zion-stop"
install -m 755 "$SRC/../privacy/zion-guard" "$PREFIX/bin/zion-guard"
install -d -m 700 "$HOME/.config/zion" "$HOME/.local/state/zion"
# the owner's policy for unattended work: no app allowed until he lists them (zion allow PKG, typed in Termux)
[ -f "$HOME/.config/zion/policy.json" ] || printf '{"apps": []}\n' > "$HOME/.config/zion/policy.json"
pkill -f 'zion run' || true  # a running supervisor keeps the code it started with: zion-ai-serve (job 7302) starts this one
install -d "$HOME/.termux/boot"
install -m 700 "$SRC/zion-ai-serve" "$HOME/.termux/boot/zion-ai-serve"
ln -sf seeker-ai "$PREFIX/bin/operator"  # OPERATOR in this terminal: ai, operator or seeker-ai
# no network nor battery condition: the service is local, and must also run offline and on a low battery
job() { termux-job-scheduler --job-id "$1" --script "$PREFIX/bin/zion-ai-serve" --network none --battery-not-low false "${@:2}"; }
pkill -f 'seeker-ai --serve' || true  # a running service keeps the code it started with: job 7302 starts this one
if job 7301 --period-ms 900000 --persisted true && job 7302; then
  echo "ZION ZERO: the launcher's ai is answered in the background (at boot, job 7301 every 15 min, job 7302 now)."
  echo "For restarts after Android stops Termux: Settings > Apps > Termux > Battery > Unrestricted."
else
  echo "JOBS NOT SCHEDULED (termux-job-scheduler failed above): the launcher's ai has no service"
fi
echo "ZION ZERO: Termux opens a plain terminal; type ai there for OPERATOR."
echo "Launcher: the first tap on dashboard or démarrer l'IA shows Termux's script list: tap the same name once."
