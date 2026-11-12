#!/usr/bin/env python3
"""Mac/Linux self-check of terminal/zion-shell-setup.sh and terminal/zion-autostart.sh, with real interactive bash and
zsh in a pseudo-terminal and a fake seeker-ai that only logs that it ran. Run: python3 terminal/test_zion_shell.py"""
import os, pty, select, shutil, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAG = "# ZION ZERO: OPERATOR on new sessions"
OLD_GITHUB_BLOCK = '# >>> ZION AI AUTOSTART >>>\nif true; then seeker-ai; fi\n# <<< ZION AI AUTOSTART <<<\n'


def interactive(argv, env, typed, wait=6.0):
    """Run argv on a pty, type each line of `typed` once the shell is up, return all it printed."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(argv[0], argv, env)
    out, sent, t0 = b"", False, time.time()
    while time.time() - t0 < wait:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
        elif not sent and time.time() - t0 > 1.0:
            os.write(fd, typed.encode())
            sent = True
    try:
        os.kill(pid, 9)
    except ProcessLookupError:
        pass
    os.waitpid(pid, 0)
    return out.decode(errors="replace")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="zion-shell-test-"))
    home, prefix = tmp / "home", tmp / "usr"
    (prefix / "bin").mkdir(parents=True)
    home.mkdir()
    fake = prefix / "bin/seeker-ai"
    fake.write_text('#!/bin/sh\necho "ran terminal=${ZION_TERMINAL_MODE:-} active=${ZION_AUTO_AI_ACTIVE:-}" >> "$HOME/ran.log"\n'
                    'echo FAKE-OPERATOR-SAYS-HI\n')
    fake.chmod(0o755)
    (home / ".bashrc").write_text("export MY_SETTING=1\n" + OLD_GITHUB_BLOCK + "alias ll='ls -l'\n")
    base = {"HOME": str(home), "PREFIX": str(prefix), "PATH": f"{prefix}/bin:/usr/bin:/bin", "TERM": "dumb", "LANG": "C"}
    setup = lambda *a: subprocess.run(["bash", str(HERE / "zion-shell-setup.sh"), *a], env=base, capture_output=True, text=True)
    ran = lambda: (home / "ran.log").read_text().splitlines() if (home / "ran.log").exists() else []

    def reset():
        (home / "ran.log").unlink(missing_ok=True)

    r = setup()
    assert r.returncode == 0, r.stderr
    bashrc = (home / ".bashrc").read_text()
    assert bashrc.rstrip("\n").endswith(TAG) and bashrc.count(TAG) == 1, bashrc
    assert "ZION AI AUTOSTART" not in bashrc and "export MY_SETTING=1" in bashrc and "alias ll=" in bashrc, bashrc
    assert (home / ".bashrc.zion-backup").read_text().startswith("export MY_SETTING=1\n# >>> ZION AI AUTOSTART"), "backup"
    assert (home / ".zshrc").read_text().count(TAG) == 1 and not (home / ".zshrc.zion-backup").exists()
    for s in ("terminal", "operator", "dashboard"):
        assert oct((home / ".shortcuts" / s).stat().st_mode & 0o777) == "0o700", s
    assert (prefix / "share/zion/autostart.sh").exists() and os.readlink(prefix / "bin/operator") == "seeker-ai"
    (home / ".bashrc").write_text((home / ".bashrc").read_text() + "export AFTER=1\n")  # something appended later
    assert setup().returncode == 0
    bashrc = (home / ".bashrc").read_text()
    assert bashrc.count(TAG) == 1 and bashrc.rstrip("\n").endswith(TAG) and "export AFTER=1" in bashrc, "re-run"
    assert "MY_SETTING" in (home / ".bashrc.zion-backup").read_text() and "AFTER" not in (home / ".bashrc.zion-backup").read_text()
    print("setup: line added last and once, old GitHub block removed, backup kept, idempotent: OK")

    shells = [("bash", ["bash", "-i"])] + ([("zsh", ["zsh", "-i"])] if shutil.which("zsh") else [])
    for name, argv in shells:
        reset()
        out = interactive(argv, base, "echo ALIVE-$((40+2))\nbash -i -c 'echo NESTED-$((1+1))'\nexit\n")
        assert ran() == ["ran terminal= active=1"], (name, ran(), out)
        assert "FAKE-OPERATOR-SAYS-HI" in out and "ALIVE-42" in out and "NESTED-2" in out, (name, out)
        print(f"{name}: new interactive session opens OPERATOR once, shell usable after, nested shell does not loop: OK")

        reset()
        interactive(argv, {**base, "ZION_TERMINAL_MODE": "1"}, "exit\n")
        assert ran() == [], (name, "terminal mode", ran())
        reset()
        interactive(argv, {**base, "SSH_CONNECTION": "10.0.0.2 5555 10.0.0.1 8022"}, "exit\n")
        assert ran() == [], (name, "ssh", ran())
        (home / ".config/zion/autostart-off").touch()
        reset()
        interactive(argv, base, "exit\n")
        assert ran() == [], (name, "autostart off", ran())
        reset()
        interactive(argv, {**base, "ZION_OPEN_OPERATOR": "1"}, "exit\n")
        assert len(ran()) == 1, (name, "launcher ai with autostart off", ran())
        (home / ".config/zion/autostart-off").unlink()
        print(f"{name}: skipped for launcher terminal, SSH, autostart off; launcher ai still opens it: OK")

    reset()
    rc = ".bashrc"
    subprocess.run(["bash", "-c", f'. "$HOME/{rc}"; true'], env=base, check=True)                       # script that sources it
    subprocess.run(["bash", "-c", 'echo "case \\$- in *i*) ;; esac" > /dev/null'], env=base, check=True)
    subprocess.run(["bash", "-i"], env=base, input="exit\n", text=True, capture_output=True)            # stdin not a terminal
    if shutil.which("zsh"):
        subprocess.run(["zsh", "-c", 'true'], env=base, check=True)
    assert ran() == [], ran()
    print("non-interactive shells, scripts and piped input never open OPERATOR: OK")

    r = setup("--remove")
    assert r.returncode == 0, r.stderr
    assert TAG not in (home / ".bashrc").read_text() and not (home / ".zshrc").exists()  # setup had created it
    assert "export MY_SETTING=1" in (home / ".bashrc").read_text() and (home / ".bashrc.zion-backup").exists()
    assert not (home / ".shortcuts/terminal").exists() and not (prefix / "bin/operator").exists()
    reset()
    interactive(["bash", "-i"], base, "exit\n")
    assert ran() == [], ran()
    print("--remove: line, scripts and command removed, backups kept, nothing opens: OK")
    # setup then --remove gives an untouched rc back byte for byte; a start marker without its end keeps the rest
    for original, after in (("export A=1\n\n\n", None), ("export B=2", None), ("", None),
                            ("export C=3\n" + OLD_GITHUB_BLOCK, "export C=3\n")):  # the old block never comes back
        (home / ".bashrc").write_text(original); (home / ".bashrc.zion-backup").unlink(missing_ok=True)
        assert setup().returncode == 0 and setup().returncode == 0 and setup("--remove").returncode == 0
        assert (home / ".bashrc").read_text() == (after or original), (original, (home / ".bashrc").read_text())
    (home / ".bashrc").write_text("export A=1\n# >>> ZION AI AUTOSTART >>>\nexport KEEP=1\n"); (home / ".bashrc.zion-backup").unlink()
    assert setup().returncode == 0
    bashrc = (home / ".bashrc").read_text()
    assert "export KEEP=1" in bashrc and bashrc.count(TAG) == 1, bashrc
    print("--remove gives an untouched rc back exactly; an unterminated old block is kept: OK")
    shutil.rmtree(tmp)
    print("test_zion_shell: all OK")


if __name__ == "__main__":
    sys.exit(main())
