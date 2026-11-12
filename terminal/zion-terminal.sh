#!/data/data/com.termux/files/usr/bin/bash
# Explicit shell mode for ZION launcher: keeps ordinary shell setup, skips AI auto-start.
# Invoked by Termux RUN_COMMAND in a new foreground session.
set -e
export ZION_TERMINAL_MODE=1
exec "${SHELL:-/data/data/com.termux/files/usr/bin/bash}" -i
