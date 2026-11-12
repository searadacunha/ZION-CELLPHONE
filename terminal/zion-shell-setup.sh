#!/data/data/com.termux/files/usr/bin/bash
# Inside Termux (termux-setup.sh runs it, safe to re-run): new interactive sessions open OPERATOR, and the ZION ZERO
# launcher's "terminal", "ai" and "dashboard" entries get their scripts in ~/.shortcuts. Undo: add --remove.
# Your ~/.bashrc and ~/.zshrc are copied once to *.zion-backup before the first change; only one line is added, last.
set -euo pipefail
: "${PREFIX:?run this inside Termux}"
SRC=$(cd "$(dirname "$0")" && pwd)
TAG='# ZION ZERO: OPERATOR on new sessions'
LINE='if [ -r "$PREFIX/share/zion/autostart.sh" ]; then . "$PREFIX/share/zion/autostart.sh"; fi  '"$TAG"
remove=; [ "${1:-}" = --remove ] && remove=1

drop_old_block() {  # the block an untested GitHub version appended (12/11); a start marker without its end is kept
  awk '/^# >>> ZION AI AUTOSTART >>>$/ { held = $0 ORS; inblock = 1; next }
       inblock { held = held $0 ORS; if ($0 ~ /^# <<< ZION AI AUTOSTART <<<$/) { inblock = 0; held = "" }; next }
       { print }
       END { if (inblock) printf "%s", held }' "$1"; }

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  tmp=$rc.zion-tmp bak=$rc.zion-backup
  if [ -n "$remove" ]; then
    [ -f "$rc" ] || continue
    grep -v -F "$TAG" "$rc" > "$tmp" || true
    if [ -f "$bak" ] && ! grep -q -F -e "$TAG" -e '# >>> ZION AI AUTOSTART >>>' "$bak" && grep -v -F "$TAG" "$bak" | cmp -s - "$tmp"; then
      cat "$bak" > "$rc"   # untouched since the setup: back byte for byte (blank lines, last newline)
    elif [ ! -s "$tmp" ] && { [ ! -f "$bak" ] || grep -q -F "$TAG" "$bak"; }; then
      rm -f "$rc"          # only our line was in it: the setup had created it
    else
      cat "$tmp" > "$rc"   # edited since, or it held the old GitHub block (which stays gone): only our line goes
    fi
    rm -f "$tmp"; continue
  fi
  if [ -f "$rc" ]; then
    [ -e "$bak" ] || grep -q -F "$TAG" "$rc" || cp -p "$rc" "$bak"  # the user's own file, never one we already changed
    grep -v -F "$TAG" "$rc" | drop_old_block /dev/stdin > "$tmp" || true
  else
    : > "$tmp"
  fi
  # our line goes last: it must run after everything else the file sets up (PATH, aliases), since OPERATOR holds the
  # shell while it runs
  printf '%s\n' "$LINE" >> "$tmp" && cat "$tmp" > "$rc" && rm "$tmp"  # cat keeps a symlinked rc
done

if [ -n "$remove" ]; then
  rm -f "$PREFIX/share/zion/autostart.sh" "$PREFIX/bin/operator"
  for s in terminal operator dashboard; do rm -f "$HOME/.shortcuts/$s"; done
  echo "ZION ZERO shell setup removed (backups kept: ~/.bashrc.zion-backup, ~/.zshrc.zion-backup)"
  exit 0
fi
install -d "$PREFIX/share/zion" "$HOME/.shortcuts" "$HOME/.config/zion"
install -m 644 "$SRC/zion-autostart.sh" "$PREFIX/share/zion/autostart.sh"
for s in terminal operator dashboard; do install -m 700 "$SRC/shortcuts/$s" "$HOME/.shortcuts/$s"; done
ln -sf seeker-ai "$PREFIX/bin/operator"
echo "ZION ZERO: new Termux sessions open OPERATOR (off: touch ~/.config/zion/autostart-off)."
echo "Launcher: the first tap on terminal, ai or dashboard shows Termux's script list: tap the same name once."
