# Matrix Phone

> In the Matrix, the only way out was a landline. They pulled every last one.
> **This is the way out now.**

A Solana Seeker rebuilt into a pocket Linux machine with its own **uncensored AI**. The AI lives on the phone: Wi-Fi off, no account, no API key, no cloud filter between you and the model. It runs your shell, writes and runs code, reads your files and drives Android itself. Google is gagged, the home screen is a terminal, and the hardware wallet stays untouched.

<p align="center">
  <img src="docs/screenshots/home.png" width="23%" alt="Home screen">
  <img src="docs/screenshots/agent.png" width="23%" alt="The AI agent at work in the terminal">
  <img src="docs/screenshots/ai-agent.png" width="23%" alt="AI agent status">
  <img src="docs/screenshots/dashboard.png" width="23%" alt="Live dashboard">
</p>

## What you get

- **An uncensored AI that runs on the phone.** HauhauCS Qwen3.5-4B Uncensored (4-bit) in llama.cpp, compiled on the phone for its own CPU. Measured during inference: **0 outbound connections** from the terminal app.
- **An agent, not a chatbot.** It plans, runs shell commands and Python, edits files, uses git, reads its own errors and fixes them. On the phone it passed 4 of 4 real tasks: write and run a script, fix a crashing script, commit with git, total a CSV.
- **Wired into Android.** Through Shizuku it gets the same rights as ADB (uid 2000, not root): system commands, settings and dumpsys, the app list, notifications, vibration, Wi-Fi status, screenshots, APK installs. Battery, volume and toasts come from Termux.
- **You hold the leash.** Four permission levels: read, write, execute, sensitive. Anything that runs code, goes online or touches the system asks first. Say no once and it stops: no retry, no workaround. Its file tools never see hidden files (`.ssh`, `.env`, `.git`...). The Seed Vault packages are locked even if you say yes.
- **A real terminal.** Termux with bash, zsh, Python 3.13, Node.js 24, git, clang, cmake, OpenSSH, nmap, dig, tmux, ripgrep, jq. Code compiled on the phone runs on the phone.
- **De-Googled, reversibly.** 35 unused Google and factory packages disabled, then 23 Google apps disabled and replaced by open-source apps from F-Droid, 16 Play Services permissions revoked, a Private DNS that blocks trackers. Every change is journaled and undone by one script.
- **A terminal for a home screen.** Black, monospace, no feeds: `terminal / ai / applications / privacy / radio / system / seed-vault`. Plain black wallpaper, lock screen included.
- **Your keys stay yours.** The Seed Vault is checked against a baseline (packages, signatures, secure hardware services, verified boot) before and after every change. Bootloader locked, nothing flashed.

The pocket hacking rig: your phone, your shell, your AI. Point it at devices and networks you own or are allowed to test.

## Measured on the phone

Benchmark `tests/bench_agent.py`, Wi-Fi off, same questions and seeds for both models, 4,096-token context. Raw results: `tests/phone/`.

| | HauhauCS Qwen3.5-4B Uncensored Q4_K_M (default) | Qwen3.5-4B Q4_0 (fallback) |
|---|---|---|
| Generation speed | 5.4 tokens/s | 5.8 tokens/s |
| Same question at the start, then at the end | 5.4 → 5.6 tokens/s | 5.9 → 6.0 tokens/s |
| Prompt reading | 20 tokens/s | 24 tokens/s |
| First token, cold agent prompt (1153 tokens) | 45 s | 35 s |
| First token afterwards (median) | 2.6 s | 2.4 s |
| Server RAM, model read into RAM (default) | 3.6 GB | 3.5 GB |
| Tool calls right (15 cases × 2 seeds) | 30/30 | 30/30 |
| Python functions passing unit tests (6 × 2) | 12/12 | 11/12 |
| Agent tasks: script, bug fix, git commit | 3/3 | 3/3 |
| 12-turn conversation | 12/12 | 12/12 |
| Outbound connections of the terminal app | 0 | 0 |
| Peak temperature, CPU / skin | 83.5 / 48.5 °C | 81.5 / 44.6 °C |

The default model was picked by `tests/bench_decide.py`, with a rule written before any measurement. Then a full validation on the phone (`tests/termux-round7.sh`, `tests/termux-round7b.sh`): offline start, permissions, the Seed Vault lock, 4 programming tasks, a conversation longer than the context, the fallback model, network silence with a positive control, dashboard, Android health afterwards. The benchmark and validation prompts are in French on purpose: they test the model in its owner's language.

## What it is not

- **Not root.** Root needs an unlocked bootloader, which wipes the phone and the Seed Vault. ADB-level rights through Shizuku are the ceiling.
- **Not invisible.** Play Services, the services framework and the Play Store stay: they deliver the security updates and the wallet's QR scanner. Google still sees the device. Why, in detail: `debloat/PLAN.md`.
- **Not always right.** A 4B model makes things up: it once described a private key as "a secret password of 12 to 24 characters". Don't ask it about your wallet's security.
- **Not cool to the touch.** Sustained AI work reaches 48.5 °C on the skin and Android's "severe" thermal status. The first agent answer after a start takes about 50 s, the next ones 1 to 15 s.
- Battery drain is not measured yet: the phone stayed on USB.

## Use it

| Command | What it does |
|---|---|
| `ai` | the agent, with tools; the chat is saved (`--resume` picks it up) |
| `ai --chat` | conversation only, no tools |
| `ai "task"`, `ai -f file "question"`, `cmd \| ai "question"` | one request, with files or piped input |
| `ai --start`, `ai --stop`, `ai --status` | load the model, free its 3.5 GB, full status |
| `seeker-ai --models`, `--use NAME`, `--model NAME` | list models, switch the default, try one once |
| `dash` | live dashboard: battery, temperatures, memory, AI agent, processes of the whole phone, connections per app, sensitive permissions |

Permissions, folders the AI may see, memory and history: `~/.config/seeker-ai/config.json`, `~/.local/share/seeker-ai/`. Your own instructions for the AI: `~/.config/seeker-ai/system.md`.

## Build your own

You need a Solana Seeker (tested on Android 16, security patch of 2026-09-05), a Mac or Linux computer with `adb`, and USB debugging on.

1. `export SEEKER_SERIAL=<your phone's serial from adb devices>`
2. Read-only audit and Seed Vault baseline: `audit/collect.sh`, `tests/seedvault_check.sh baseline`.
3. Verified apps from F-Droid (signed index, pinned key, SHA-256 and signer of every APK): `python3 -I apk-manager/fdroid_fetch.py <package> ...`
4. De-Google: `debloat/apply.sh G1`, then `debloat/g2lite.sh`. Both stop at the first failed health check. Read `debloat/PLAN.md` first.
5. Termux from Google Play (Play Protect blocks the F-Droid build). Copy this repository to the phone (`adb push . /sdcard/Download/seeker-zero`), then in Termux: `bash /sdcard/Download/seeker-zero/terminal/termux-setup.sh`. It installs the tools, `seeker-ai`, `dash`, and downloads both models with their SHA-256 checked.
6. Shizuku: in the Shizuku app, "Use Shizuku in terminal apps" > "Export files" into `terminal/shizuku/`, then `terminal/seeker-setup-shizuku` in Termux. After every reboot, from the computer: `terminal/start-shizuku.sh`.
7. Home screen: `launcher/build.sh`, install the APK, pick it as the home app. Black wallpaper: in the launcher, `system > wallpaper: black` (it keeps a copy of the old one).
8. Undo anything: `restore/restore.sh` (everything) or `restore/restore.sh <group>`, then `tests/seedvault_check.sh`.

Check the Seed Vault yourself too: `tests/SEEDVAULT_MANUAL.md`.

## Tests

- On the computer: `python3 ai/test_seeker_ai.py` (30 scenarios: permissions, protected folders, the Seed Vault lock dodged with quotes, command injection through a notification, full context, a stop in the middle of a task...), `python3 terminal/test_seeker_dash.py`, `bash tests/test_bench_dry.sh`, `python3 tests/bench_decide.py --test`.
- On the phone: `tests/termux-round6.sh` (benchmark of both models, offline), `tests/termux-round7.sh` (validation), `tests/health.sh` and `tests/seedvault_check.sh` (Android and Seed Vault health).

## Map

| Folder | What is in it |
|---|---|
| `ai/` | `seeker-ai`, the agent (Python, no dependency), its self-test, the model installer |
| `terminal/` | Termux setup, the `dash` dashboard, Shizuku helpers |
| `launcher/` | the terminal-style home screen (Java, built without Gradle) |
| `debloat/`, `restore/` | de-Googling groups, journaled operations, one-command undo |
| `apk-manager/` | verified F-Droid downloads |
| `audit/`, `privacy/` | read-only audit, network watch |
| `tests/` | health and Seed Vault checks, benchmark, validation, raw results from the phone |
