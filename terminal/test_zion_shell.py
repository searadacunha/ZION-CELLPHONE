#!/usr/bin/env python3
"""Mac/Linux self-check of terminal/zion-shell-setup.sh since 13/11 (Termux is a plain terminal; the launcher's "ai" is
answered in the background by seeker-ai --serve). From the state the setup of 12-13/11 left, it must take its line out
of ~/.bashrc and ~/.zshrc (byte for byte back when untouched since), drop the autostart, install the launcher's scripts
and the service, and schedule the jobs; then a real interactive bash and zsh open no OPERATOR. --remove undoes it.
A fake seeker-ai and a fake termux-job-scheduler only log. Run: python3 terminal/test_zion_shell.py"""
import os, pty, select, shutil, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAG = "# ZION ZERO: OPERATOR on new sessions"
OLD_LINE = 'if [ -r "$PREFIX/share/zion/autostart.sh" ]; then . "$PREFIX/share/zion/autostart.sh"; fi  ' + TAG + "\n"
ALIASES = "alias ai=seeker-ai\nalias dash=seeker-dash\n"  # termux-setup.sh's, kept: ai opens OPERATOR in the terminal


def interactive(argv, env, typed, wait=5.0):
    """Run argv on a pty, type `typed` once the shell is up, return all it printed."""
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
            try:
                os.write(fd, typed.encode())
            except OSError:
                break
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
    for name, body in (("seeker-ai", 'echo "ran $*" >> "$HOME/ran.log"; echo FAKE-OPERATOR-SAYS-HI'),
                       ("termux-job-scheduler", 'echo "$*" >> "$HOME/jobs.log"')):
        (prefix / "bin" / name).write_text(f"#!/bin/sh\n{body}\n")
        (prefix / "bin" / name).chmod(0o755)
    base = {"HOME": str(home), "PREFIX": str(prefix), "PATH": f"{prefix}/bin:/usr/bin:/bin", "TERM": "dumb", "LANG": "C"}
    setup = lambda *a: subprocess.run(["bash", str(HERE / "zion-shell-setup.sh"), *a], env=base, capture_output=True, text=True)
    lines = lambda f: (home / f).read_text().splitlines() if (home / f).exists() else []
    serve = f"--script {prefix}/bin/zion-ai-serve --network none --battery-not-low false"

    def old_state(bashrc_own):
        """What the setup of 12-13/11 left: its line last in both files (after termux-setup.sh's aliases), the user's
        own ~/.bashrc in its backup, a ~/.zshrc it created, the autostart file, its shortcuts and the "off" switch."""
        (home / ".bashrc").write_text(bashrc_own + ("\n" if bashrc_own and not bashrc_own.endswith("\n") else "") + ALIASES + OLD_LINE)
        (home / ".bashrc.zion-backup").write_text(bashrc_own)
        (home / ".zshrc").write_text(ALIASES + OLD_LINE)
        (home / ".zshrc.zion-backup").unlink(missing_ok=True)
        (prefix / "share/zion").mkdir(parents=True, exist_ok=True)
        (prefix / "share/zion/autostart.sh").write_text('case $- in *i*) seeker-ai ;; esac\n')
        (home / ".config/zion").mkdir(parents=True, exist_ok=True)
        (home / ".config/zion/autostart-off").touch()
        (home / ".shortcuts").mkdir(exist_ok=True)
        for s in ("terminal", "operator", "dashboard"):
            (home / ".shortcuts" / s).write_text("old\n")

    own = "export MY_SETTING=1\nalias ll='ls -l'\n"
    old_state(own)
    r = setup()
    assert r.returncode == 0, r.stdout + r.stderr
    assert (home / ".bashrc").read_text() == own + ALIASES, (home / ".bashrc").read_text()  # only the line went
    assert (home / ".zshrc").read_text() == ALIASES, (home / ".zshrc").read_text()
    assert (home / ".bashrc.zion-backup").read_text() == own  # kept
    assert not (prefix / "share/zion").exists() and not (home / ".config/zion/autostart-off").exists()
    # 17/11: the owner's policy for unattended work, empty (no app allowed) until he lists apps; never overwritten
    assert (home / ".config/zion/policy.json").read_text() == '{"apps": []}\n'
    assert sorted(p.name for p in (home / ".shortcuts").iterdir()) == ["ai-start", "dashboard", "zion-stop"]
    for s in ("ai-start", "dashboard", "zion-stop"):
        assert oct((home / ".shortcuts" / s).stat().st_mode & 0o777) == "0o700", s
    for b in ("zion-ai-serve", "zion", "zion-stop", "zion-guard"):  # the supervisor, the emergency stop, the threat check
        assert oct((prefix / "bin" / b).stat().st_mode & 0o777) == "0o755", b
    boot = home / ".termux/boot/zion-ai-serve"  # Termux runs it at BOOT_COMPLETED
    assert oct(boot.stat().st_mode & 0o777) == "0o700" and boot.read_text() == (HERE / "zion-ai-serve").read_text()
    assert os.readlink(prefix / "bin/operator") == "seeker-ai"
    assert lines("jobs.log") == [f"--job-id 7301 {serve} --period-ms 900000 --persisted true", f"--job-id 7302 {serve}"], lines("jobs.log")
    # the launcher's "démarrer l'IA" schedules the same job 7302 (Termux's absolute paths: read, not run, here)
    # the launcher's "démarrer l'IA" schedules both jobs the same way (Termux's absolute paths: run with a fake $J here)
    start = (HERE / "shortcuts/ai-start").read_text().replace("J=/data/data/com.termux/files/usr/bin/termux-job-scheduler",
                                                             f"J={prefix}/bin/termux-job-scheduler")
    (home / "jobs.log").unlink()
    subprocess.run(["sh", "-c", start], env=base, check=True)
    t = "/data/data/com.termux/files/usr"
    assert lines("jobs.log") == [l.replace(str(prefix), t) for l in (f"--job-id 7301 {serve} --period-ms 900000 --persisted true",
                                                                     f"--job-id 7302 {serve}")], lines("jobs.log")
    (home / "jobs.log").write_text(f"--job-id 7301 {serve} --period-ms 900000 --persisted true\n--job-id 7302 {serve}\n")
    served = (HERE / "zion-ai-serve").read_text()
    assert served.rstrip().endswith("exec $P/seeker-ai --serve") and "$P/zion run --background" in served
    print("setup: old line out of both rc files (aliases kept), autostart gone, scripts and service in, jobs scheduled: OK")

    (home / ".config/zion/policy.json").write_text('{"apps": ["org.fossify.math"]}\n')  # the owner's own list stays
    assert setup().returncode == 0 and (home / ".bashrc").read_text() == own + ALIASES and len(lines("jobs.log")) == 4
    assert (home / ".config/zion/policy.json").read_text() == '{"apps": ["org.fossify.math"]}\n'
    print("re-run: nothing more changes in the rc files, the jobs are scheduled again (same ids): OK")

    shells = [("bash", ["bash", "-i"])] + ([("zsh", ["zsh", "-i"])] if shutil.which("zsh") else [])
    for name, argv in shells:
        out = interactive(argv, base, "echo ALIVE-$((40+2))\nexit\n")
        assert lines("ran.log") == [] and "ALIVE-42" in out and "FAKE-OPERATOR" not in out, (name, lines("ran.log"), out)
        print(f"{name}: a new interactive session is a plain shell, no OPERATOR: OK")

    # an rc left untouched since that setup comes back byte for byte; one that setup created goes; edits are kept
    for original in ("export A=1\n\n\n", "export B=2", ""):
        old_state(original)
        (home / ".bashrc").write_text(original + ("\n" if original and not original.endswith("\n") else "") + OLD_LINE)
        assert setup().returncode == 0
        assert (home / ".bashrc").read_text() == original, (original, (home / ".bashrc").read_text())
    old_state(own)
    (home / ".zshrc").write_text(OLD_LINE)
    assert setup().returncode == 0 and not (home / ".zshrc").exists()
    print("rc files: untouched ones back exactly, one created by that setup removed: OK")

    r = setup("--remove")
    assert r.returncode == 0, r.stderr
    assert not (home / ".shortcuts/ai-start").exists() and not (home / ".shortcuts/dashboard").exists()
    assert not (prefix / "bin/zion-ai-serve").exists() and not (prefix / "bin/operator").exists() and not boot.exists()
    assert not any((prefix / "bin" / b).exists() for b in ("zion", "zion-stop", "zion-guard")) and not (home / ".shortcuts/zion-stop").exists()
    assert (home / ".config/zion/policy.json").exists()  # the owner's policy and approval key are his: kept
    assert lines("jobs.log")[-2:] == ["--cancel --job-id 7301", "--cancel --job-id 7302"], lines("jobs.log")
    assert (home / ".bashrc").read_text() == own + ALIASES
    print("--remove: scripts, service and command removed, both jobs cancelled, rc files left as they are: OK")
    shutil.rmtree(tmp)
    print("test_zion_shell: all OK")


if __name__ == "__main__":
    sys.exit(main())
