#!/data/data/com.termux/files/usr/bin/bash
# Inside Termux (typed by the Mac): install OPERATOR autostart and the launcher scripts, record what the shell reads.
D=/sdcard/Download/seeker-zero
exec > "$D/p1-setup.log" 2>&1
set -x
install -m 755 "$D/ai/seeker-ai" "$PREFIX/bin/seeker-ai"
install -m 755 "$D/terminal/seeker-dash" "$PREFIX/bin/seeker-dash"
bash "$D/terminal/zion-shell-setup.sh"
set +x
echo "== SHELL=$SHELL shell-file=$(readlink -f ~/.termux/shell 2>/dev/null || echo none) bash=$BASH_VERSION"
echo "== profile reads ~/.bashrc?"; grep -n -i -E "bashrc|bash.bashrc" "$PREFIX/etc/profile" "$PREFIX/etc/bash.bashrc" 2>&1 | head
echo "== ~/.bash_profile ~/.profile ~/.bash_login:"; ls -la ~/.bash_profile ~/.profile ~/.bash_login 2>&1
echo "== tail ~/.bashrc"; tail -4 ~/.bashrc
echo "== ~/.zshrc"; cat ~/.zshrc
echo "== ~/.shortcuts"; ls -la ~/.shortcuts
echo "== login script head"; head -40 "$PREFIX/bin/login"
echo "== env of this session"; env | grep -E "^(PREFIX|HOME|PATH|LD_PRELOAD|SHELL|TERMUX)" | sort
echo "== done $(date +%T)"
