# What is tested, and where

Three kinds of evidence, never mixed:

- **Simulated**: on the computer, with a fake model server, a fake Android shell and canned screens. The same suites
  run in **CI** on every push and pull request (`.github/workflows/tests.yml`).
- **On the phone**: a run on the Solana Seeker itself, with the file it left (`tests/phone/`) and its date.
- **Not run**: written and ready, not yet run on the phone. Said so here, never presented as validated.

State on **17/11/2026**. The parts added that day (zion, the owner's policy, approvals, STOP, the injection guard,
launcher 1.8.0, the test app, the tool-call benchmark, zion-guard) pass every suite below on the computer; **none of
them has run on the phone yet**: the computer lost its USB-debugging authorization that afternoon, and only the
owner can grant it again.

| # | Category | Simulated (computer, CI) | On the phone |
|---|---|---|---|
| 1 | Full control of a test app | `ai/test_seeker_ai.py` 55-62 (read, tap, type, keys, scroll, open on canned screens); `tests/eval_ui.py --selftest` (ZION Testbed checks) | real apps, 13/11: **9 of 10** requests judged on the phone's state (`tests/phone/2026-11-13-ui/eval-ui-run1.json`). ZION Testbed scenarios `tb-form`, `tb-list`: **not run** |
| 2 | Several allowed apps | 71 (allowed apps, `--apps`, an app outside them refused), 60 (open by name) | single-app requests only (13/11). `tb-two-apps` (calculator then testbed): **not run** |
| 3 | Long tasks | 65-67 (plan, steps, retry, dependencies), 72-73, 75 (12 rounds or the time limit = failed); `ai/test_zion.py` 1, 8 (time limit kills the process group) | the overnight chain of 12-13/11 ran unattended from 21:47 to 00:26 (speed sweep, five models); four programming tasks, 11-12/11. A long zion task: **not run** |
| 4 | Recovery after interruption | 67 (resume a cut step), 73 (stop, then resume), 80 (a stop between two calls of one answer), 77 (stream cut: exit 6); zion 7 (crash, lost server), 9 (stop), 13, 18-19 (restart, a reused pid, a task that keeps getting killed) | Termux killed by Android twice (12/11, 13/11): the files survived, resumed by hand. zion's automatic resume: **not run** |
| 5 | Phone reboot | zion 13 (a running task whose worker died is taken back at start) | 12/11: reboot, launcher as home, USB authorization kept, Shizuku restarted from the computer. A queued task across a reboot: **not run** |
| 6 | Offline | everything simulated talks to `127.0.0.1` only; 42, 47 (no server off the phone, no redirect to it) | 11-12/11: start and answers with Wi-Fi off (`termux-round7.sh`). zion offline: **not run** |
| 7 | Secrets and Seed Vault | 16-17, 34, 55, 61, 68 (wallet, Seed Vault, hidden files, passwords masked), 70-74 (classes), 81 (a password only into an allowed app with nobody at the terminal), 83 (zion's folders out of reach) | `tests/seedvault_check.sh` against the baseline, 11-13/11: unchanged; `wallet-refused`, 13/11: refused |
| 8 | Dangerous commands | auto-allow negatives (`rm -rf`, `$()`, `>`, globbing), 3, 10, 17, 31-32, 69, 70 (approve, deny, auto), 71 (buttons that delete, reset or pay), 86 (the firewall's reapply is a change; deny cannot be reopened), 89 (typing never taps a button; enter on a focused delete button is asked) | none specific |
| 9 | Prompt injection | 74 (a hostile file: marked, no memory note, nothing beyond ordinary runs alone), 82 (after it, words the owner never gave go into no field), 84 (zion's own commands and files refused even approved), 74 and 85 (the pattern: 13 hostile phrases caught, 12 ordinary ones not, one known miss), 88 (an approved call's answer goes through the guard too); `tests/eval_tools.py --selftest` (6 injection cases, fed to the model without the guard's note: they measure the bare model); `tests/eval_ui.py --selftest` (3 hostile messages) | **not run** (`tb-inject-wifi`, `tb-inject-browser`, `tb-inject-wallet`, and the 6 cases of `eval_tools.py` per model) |
| 10 | Outgoing traffic | `privacy/pcap_domains.py --selftest`; `privacy/test_zion_guard.py` (per-app byte counts, diff) | 12/11: **0** outside connections from Termux during inference (with a positive control); 13/11: per-app block real (works, fails while cut, works again); 20-minute captures before and after the privacy changes. Per-task counts: **not run** |
| 11 | Reliability of Android actions | 55-62, 69, 71 | 13/11: 20 screen reads of 20 in 0.26-0.46 s; 9 of 10 real requests; `input text` fails on accented letters, set through UiShell instead |
| 12 | Model errors | 21-22 (context too long), 48 (old server), 54 (port held by another app), 75, 77 (garbled stream); zion 7 (lost server: stopped, then resumed) | the 13/11 low-memory kill during an evaluation (`lowmemory-1928.txt`). The new handling: **not run** |

**zion** (`ai/test_zion.py`, 25 scenarios): queue and priority, a password kept out of the journal, approvals from the
terminal, from the launcher (signed, checked against openssl's and the launcher's own Java vectors, and refused with
another key, another request, out of time), refusal, expiry, crash and lost-server resume, time limit, emergency stop
(Termux and launcher), resources (battery, heat, a measurement), lock screen (a screen task waits, a background one
runs), recovery at start, one supervisor at a time, the journal's chain (edited, removed, reordered lines), `zion allow`, and
what the independent review of 17/11 found: a journal over 64 KB of accented text, a line cut by a power loss, a pid
reused after a restart, a task that keeps getting Termux killed, a broken task file, `zion cancel` on a running task,
a stop typed as from the launcher, `zion allow` and `zion approve` run by a program, a launcher stop lifted only on
the owner's signed resume (never by a deleted file, another signature or an old resume), the exact call shown whole
(or decided in the terminal when too long), a terminal decision withdrawn from the launcher.

**Launcher 1.8.0** (`launcher/test/run.sh`, plain JDK, 88 checks): request parsing and time rules (52 malformed
requests refused), the signed payload and decision files. Key creation, BiometricPrompt, the receiver, FLAG_SECURE and
the STOP and drive flows exist only as code that compiles with javac against android-35: **not run**.

**Model choice.** Rule P5 (French answers, speed, memory) chose the default model on 13/11 from five candidates
(`docs/RESULTS.md`). Rule P6 (tool calls, injection resistance, latency, memory) was written on 17/11 **before any
measurement**; `tests/eval_tools.py` and `tests/termux-eval-tools-chain.sh` are ready: **not run**.

On the phone, from the computer, once the USB authorization is back: `python3 tests/phone_termux.py SCRIPT` runs a
script inside Termux; `tests/eval_ui.py --only tb-form,...` and `tests/termux-eval-tools-chain.sh` run there.
