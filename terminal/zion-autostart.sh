# ZION ZERO, sourced by the last line of ~/.bashrc and ~/.zshrc (installed by terminal/zion-shell-setup.sh).
# A new interactive Termux session opens OPERATOR (seeker-ai, the local AI); leaving it (/exit or Ctrl+D) gives this
# shell back. Never opened when: the launcher's "terminal" started the session (ZION_TERMINAL_MODE), OPERATOR already
# ran in this shell or in a parent one (ZION_AUTO_AI_ACTIVE: no loop through bash, tmux, exec), the login came by SSH,
# or input or output is not a terminal (scripts, pipes, bash -c). Plain sh syntax: bash and zsh both read it.
# Off: touch ~/.config/zion/autostart-off   (the launcher's "ai" entry still opens OPERATOR)   On again: rm that file.
case $- in
  *i*)
    if [ -z "${ZION_TERMINAL_MODE:-}${ZION_AUTO_AI_ACTIVE:-}${SSH_CONNECTION:-}" ] && [ -t 0 ] && [ -t 1 ] &&
       { [ -n "${ZION_OPEN_OPERATOR:-}" ] || [ ! -e "$HOME/.config/zion/autostart-off" ]; } &&
       command -v seeker-ai >/dev/null 2>&1; then
      export ZION_AUTO_AI_ACTIVE=1
      seeker-ai
    fi ;;
esac
