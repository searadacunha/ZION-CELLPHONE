#!/data/data/com.termux/files/usr/bin/bash
# Run once inside Termux:  bash /sdcard/Download/seeker-zero/terminal/termux-setup.sh
# Installs the dev environment, seeker-ai, seeker-dash, rish and the model. Safe to re-run. No server is started:
# to reach Termux from the Mac by SSH, set it up yourself (pkg install openssh; add your key; sshd).
set -uo pipefail
SRC=$(cd "$(dirname "$0")/.." && pwd)
PKGS="bash zsh python nodejs-lts git openssh curl wget clang make cmake binutils vim nano micro tmux htop procps psmisc
lsof tree file ripgrep fd jq rsync unzip zip man iproute2 net-tools dnsutils nmap traceroute whois openssl
proot-distro llama-cpp"

yes | pkg update -y && pkg upgrade -y -o Dpkg::Options::=--force-confold
if ! pkg install -y $PKGS; then  # one bad name must not block the rest
  for p in $PKGS; do pkg install -y "$p" >/dev/null 2>&1 || echo "PACKAGE FAILED: $p"; done
fi

# seeker-ai
install -m 755 "$SRC/ai/seeker-ai" "$PREFIX/bin/seeker-ai"
install -m 755 "$SRC/ai/install-model.sh" "$PREFIX/bin/install-model"
install -m 755 "$SRC/terminal/seeker-dash" "$PREFIX/bin/seeker-dash"
install -m 755 "$SRC/terminal/zion-terminal.sh" "$PREFIX/bin/zion-terminal"
bash "$SRC/terminal/seeker-setup-shizuku" || true   # rish works once Shizuku is started
grep -q 'alias ai=' ~/.bashrc 2>/dev/null || printf 'alias ai=seeker-ai\nalias dash=seeker-dash\n' >> ~/.bashrc  # names used by the launcher
# Default Termux launches OPERATOR; explicit launcher "terminal" opens a normal shell.
# Kept as a reversible, opt-out login configuration, never injected into non-interactive shells.
mkdir -p "$HOME/.config/zion" "$HOME/.termux"
touch "$HOME/.config/zion/ai-autostart.enabled"
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  if ! grep -q '^# >>> ZION AI AUTOSTART >>>
bash "$PREFIX/bin/install-model" unsloth/Qwen3.5-4B-GGUF Qwen3.5-4B-Q4_0.gguf    # fallback

echo; echo "versions:"; for c in bash zsh python node git ssh clang gcc vim micro tmux llama-server proot-distro; do
  printf '  %-13s %s\n' "$c" "$(command -v $c >/dev/null && ($c --version 2>&1 || $c -V 2>&1) | head -1 || echo MISSING)"; done
echo "ZION Termux setup done"
 "$rc" 2>/dev/null; then
    cat >> "$rc" <<'ZION_AUTO_START'

# >>> ZION AI AUTOSTART >>>
# Interactive sessions only; skip the dedicated launcher terminal and recursive agents.
if [[ $- == *i* ]] && [[ -f "$HOME/.config/zion/ai-autostart.enabled" ]] \
   && [[ -z "${ZION_TERMINAL_MODE:-}" ]] && [[ -z "${ZION_AUTO_AI_ACTIVE:-}" ]]; then
  export ZION_AUTO_AI_ACTIVE=1
  if command -v seeker-ai >/dev/null 2>&1; then
    seeker-ai
  fi
fi
# <<< ZION AI AUTOSTART <<<
ZION_AUTO_START
  fi
done

# Termux RUN_COMMAND requires this setting AND a separately granted Android permission
# for ZION launcher. Back up the user's settings once; leave other properties untouched.
PROPS="$HOME/.termux/termux.properties"
if [ -f "$PROPS" ] && [ ! -f "$PROPS.zion-backup" ]; then cp "$PROPS" "$PROPS.zion-backup"; fi
if grep -q '^allow-external-apps=' "$PROPS" 2>/dev/null; then
  sed -i 's/^allow-external-apps=.*/allow-external-apps=true/' "$PROPS"
else
  printf '\nallow-external-apps=true\n' >> "$PROPS"
fi
command -v termux-reload-settings >/dev/null 2>&1 && termux-reload-settings || true
echo "ZION: Termux opens OPERATOR by default; launcher terminal opens a shell."
echo "Disable auto-start: rm ~/.config/zion/ai-autostart.enabled"
echo "ZION launcher needs Android permission: Run commands in Termux environment."

bash "$PREFIX/bin/install-model"                                                  # default model
bash "$PREFIX/bin/install-model" unsloth/Qwen3.5-4B-GGUF Qwen3.5-4B-Q4_0.gguf    # fallback

echo; echo "versions:"; for c in bash zsh python node git ssh clang gcc vim micro tmux llama-server proot-distro; do
  printf '  %-13s %s\n' "$c" "$(command -v $c >/dev/null && ($c --version 2>&1 || $c -V 2>&1) | head -1 || echo MISSING)"; done
echo "SEEKER-ZERO termux setup done"
