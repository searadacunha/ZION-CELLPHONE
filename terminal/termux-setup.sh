#!/data/data/com.termux/files/usr/bin/bash
# Run once inside Termux:  bash /sdcard/Download/seeker-zero/terminal/termux-setup.sh
# Installs the dev environment, seeker-ai, seeker-dash, rish and two models (default ~2.7 GB, fallback ~2.6 GB, sha256
# checked). Safe to re-run. No server is started: to reach Termux from the Mac by SSH, set it up yourself (pkg install
# openssh; add your key; sshd). An older version of this script (before 12/11/2026) started sshd from ~/.bashrc and set
# allow-external-apps in ~/.termux/termux.properties; this one does neither and leaves those lines alone: delete them
# if you do not use them (the ZION ZERO launcher does not need allow-external-apps).
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
bash "$SRC/terminal/seeker-setup-shizuku" || true   # rish works once Shizuku is started
for rc in ~/.bashrc ~/.zshrc; do  # both shells (zsh users got "ai: command not found")
  grep -q 'alias ai=' "$rc" 2>/dev/null || printf 'alias ai=seeker-ai\nalias dash=seeker-dash\n' >> "$rc"
done
bash "$SRC/terminal/zion-shell-setup.sh"   # OPERATOR on new sessions + the launcher's terminal/ai/dashboard scripts
bash "$PREFIX/bin/install-model"                                                  # default model
bash "$PREFIX/bin/install-model" unsloth/Qwen3.5-4B-GGUF Qwen3.5-4B-Q4_0.gguf    # fallback

echo; echo "versions:"; for c in bash zsh python node git ssh clang gcc vim micro tmux llama-server proot-distro; do
  printf '  %-13s %s\n' "$c" "$(command -v $c >/dev/null && ($c --version 2>&1 || $c -V 2>&1) | head -1 || echo MISSING)"; done
echo "ZION ZERO Termux setup done"
