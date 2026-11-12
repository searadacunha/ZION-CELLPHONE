# ZION-CELLPHONE

> ## IN THE MATRIX, THE ONLY WAY OUT WAS A PAYPHONE.
>
> A ringing public telephone. A hardline. One last connection to the real world.
>
> **They took every last one.**
>
> # THIS IS THE NEW WAY OUT.
>
> **ZION-CELLPHONE. THE LAST HARDLINE.**

**ZION-CELLPHONE** is a Solana Seeker rebuilt around a simple idea: **the most powerful thing your phone can do is belong to you.**

An AI that thinks and works **on the device**. A real Linux command-line environment. Android system controls. A stripped-down, terminal-first home screen. Privacy changes you can audit and reverse. And a hardware wallet left alone.

No cloud is required to run the local model. No AI account. No API key. No bootloader unlock.

**Your phone. Your terminal. Your AI. Your rules.**

---

## THIS IS NOT A CONCEPT

It runs on a real **Solana Seeker**, tested on **Android 16** (security patch **2026-09-05**).

| On-device result | Measured outcome |
|---|---|
| Local AI generation | **5.4 tokens/second** with the default model |
| Tool-call correctness | **30/30** cases on the benchmark |
| Real agent tasks | **4/4** completed in full-device validation |
| Outbound connections from the terminal app during the offline inference test | **0 observed** |
| Local model loaded in memory | **3.6 GB RAM** |
| Bootloader | **Locked** |
| Root | **Not required** |

These are results from the tested device and specific test procedures—not claims that the whole phone is invisible, anonymous, or permanently disconnected. Raw artifacts and scripts live in [`tests/`](tests/).

## WHAT HAPPENS WHEN YOU UNPLUG?

Most AI products make your phone a remote control for someone else's computer.

**ZION-CELLPHONE puts the model on your phone.**

The default is **HauhauCS Qwen3.5-4B Uncensored Q4_K_M**, running through **llama.cpp**, compiled for the Seeker's CPU. A standard **Qwen3.5-4B Q4_0** build is available as a fallback.

Turn off Wi-Fi. Start the model. Keep working.

The project is more than a local chat interface: the agent can use tools, inspect errors, revise its own code, and carry a task through to completion—subject to explicit permissions.

### OPERATOR: AN AGENT, NOT JUST AN ANSWER BOX

**OPERATOR** is the local AI agent, launched from the terminal with `ai`. It is a project identity, not a separate cloud service.

It can:

- Write, run, debug, and fix **Python** and shell scripts.
- Create and edit permitted files, inspect output, and retry after ordinary programming errors.
- Use **git**, including creating a commit.
- Read a CSV, calculate results, and explain what it did.
- Work with Android services through **Shizuku**, within ADB shell-level permissions.
- Continue saved conversations and use your own system instructions.

On the phone, the full validation included **four practical programming tasks**. The narrower model comparison benchmark separately recorded **3/3** agent tasks.

**The difference:** you do not merely ask your phone how to do something. You can ask it to do the work, review the proposed action, and decide whether it may proceed.

### THE PHONE IS THE WORKSTATION

The terminal environment is built around **Termux**:

```text
bash · zsh · Python 3.13 · Node.js 24
git · clang · cmake · OpenSSH
nmap · dig · tmux · ripgrep · jq
```

Code compiled on the phone runs on the phone. The terminal is not a decorative interface to a cloud service.

### ANDROID ACCESS, WITHOUT ROOT

**Shizuku** gives supported tools access through the Android shell identity (**uid 2000**), similar to ADB—not root.

Depending on the command and Android restrictions, that means access to system diagnostics, settings, package information, notifications, Wi-Fi state, screenshots, APK installation, and more. Battery, volume, and toast utilities are also available from Termux.

**This does not bypass Android's security model.** Shizuku must be started again after reboot using the documented procedure.

## THE INTERFACE: NOTHING BETWEEN YOU AND THE MACHINE

No infinite feed. No attention economy. No unnecessary decoration.

The custom launcher replaces the usual app grid with a black, monospace command-center aesthetic:

```text
ZION
─────────────────────────────────
> terminal
> ai
> applications
> privacy
> radio
> system
> seed-vault
─────────────────────────────────
ZION  /  OPERATOR  /  USER CONTROL
```

The launcher is written in **Java** and built **without Gradle**. A black wallpaper option covers the home and lock screens, with the previous wallpaper backed up.

## PRIVACY IS A CONFIGURATION, NOT A SLOGAN

This is a **reversible reduction of Google and factory software**, not a replacement ROM.

The documented configuration:

- Disables **35** unused Google and factory packages in the first group.
- Disables another **23** Google applications and replaces selected functions with open-source alternatives from **F-Droid**.
- Revokes **16** permissions from Play Services.
- Uses **Private DNS** to block known trackers.
- Journals changes so they can be reversed with a restore script.
- Checks Android and Seed Vault health after modifications.

**Important:** Google Play Services, the services framework, and the Play Store remain for security updates and wallet-related functionality. Google may still observe activity. ZION-CELLPHONE does **not** claim to make the device untraceable.

See [`debloat/PLAN.md`](debloat/PLAN.md) for the actual trade-offs.

### THE WALLET IS NOT AN EXPERIMENT

The Solana Seeker includes a **Seed Vault**. ZION-CELLPHONE does not flash a new OS, unlock the bootloader, or deliberately modify wallet components.

Before and after changes, scripts check the wallet's package baseline, signatures, secure-hardware services, and verified boot state. Additional manual checks are documented in [`tests/SEEDVAULT_MANUAL.md`](tests/SEEDVAULT_MANUAL.md).

A passing baseline check is **not** a guarantee of wallet security. Do not entrust private keys or seed phrases to the local model.

## YOU DECIDE WHAT THE AGENT MAY DO

The tool layer separates permissions into **four levels**:

| Level | Purpose |
|---|---|
| **Read** | Inspect approved data |
| **Write** | Change approved files |
| **Execute** | Run commands and code |
| **Sensitive** | Perform higher-risk operations |

Actions that execute code, reach the network, or affect the system request approval. A refusal is final for that action: the agent must not retry through a workaround.

Built-in file tools exclude hidden files such as `.ssh`, `.env`, and `.git`. Seed Vault packages are protected even from an approved request.

**The model is not a security boundary.** Permission enforcement belongs in the surrounding code, and the repository includes tests for attempted bypasses and prompt injection.

## PROOF, NOT PROMISES

The offline comparison uses the same questions and seeds, a **4,096-token context**, and the benchmark in [`tests/bench_agent.py`](tests/bench_agent.py). Results are under [`tests/phone/`](tests/phone/).

| Measurement | HauhauCS Qwen3.5-4B Uncensored Q4_K_M **(default)** | Qwen3.5-4B Q4_0 **(fallback)** |
|---|---:|---:|
| Generation speed | **5.4 tok/s** | 5.8 tok/s |
| Start → end of repeated-question test | 5.4 → 5.6 tok/s | 5.9 → 6.0 tok/s |
| Prompt processing | 20 tok/s | 24 tok/s |
| Cold first token, 1,153-token agent prompt | 45 s | 35 s |
| Subsequent first-token latency, median | 2.6 s | 2.4 s |
| RAM, model loaded | 3.6 GB | 3.5 GB |
| Correct tool calls, 15 cases × 2 seeds | **30/30** | **30/30** |
| Python unit tests, 6 functions × 2 | **12/12** | 11/12 |
| Agent benchmark tasks: script, fix, commit | **3/3** | **3/3** |
| 12-turn conversation | **12/12** | **12/12** |
| Observed outbound terminal-app connections | **0** | **0** |
| Peak CPU / skin temperature | 83.5 / 48.5 °C | 81.5 / 44.6 °C |

The default model was chosen by [`tests/bench_decide.py`](tests/bench_decide.py) using a rule defined **before** measurements were taken, rather than choosing a favorite result afterward.

A separate on-device validation with `tests/termux-round7.sh` and `tests/termux-round7b.sh` checked startup without Wi-Fi, approvals, Seed Vault protections, four programming tasks, long conversation handling, fallback selection, network silence with a positive control, dashboard behavior, and Android health.

Prompts are deliberately **in French**: this tests how the model performs in the language actually used by its owner.

## USE THE PHONE

From Termux, after installation:

| Command | Action |
|---|---|
| `ai` | Launch the agent with tools |
| `ai --chat` | Talk to the model without tools |
| `ai "your task"` | Run a single task |
| `ai -f file "question"` | Ask about a file |
| `command \| ai "question"` | Pipe terminal output to the model |
| `ai --start` | Load the local model |
| `ai --stop` | Stop it and release roughly 3.5 GB RAM |
| `ai --status` | Inspect agent/model status |
| `ai --resume` | Resume the saved conversation |
| `seeker-ai --models` | Show available models |
| `seeker-ai --use NAME` | Change the default |
| `seeker-ai --model NAME` | Run with a selected model once |
| `dash` | Open the live system dashboard |

The **dashboard** displays battery, temperature, memory, agent state, processes, per-app network connections, and sensitive permissions.

Configure tools, allowed folders, history, and other settings in:

- `~/.config/seeker-ai/config.json`
- `~/.local/share/seeker-ai/`
- `~/.config/seeker-ai/system.md` — your own instructions to the agent

## BUILD YOUR OWN EXIT

**Requirements:** a Solana Seeker, a Mac or Linux computer with `adb`, and USB debugging enabled. Tested on Android 16 with the **2026-09-05** security patch; other versions are not verified here.

**1. Identify your device.**

```bash
adb devices
export SEEKER_SERIAL=<serial-shown-by-adb>
```

**2. Audit before changing anything.** Run the read-only collector and record the Seed Vault baseline.

```bash
bash audit/collect.sh
bash tests/seedvault_check.sh baseline
```

**3. Review the changes before debloating.** Read [`debloat/PLAN.md`](debloat/PLAN.md). The documented groups are applied in sequence and stop on failed health checks.

```bash
bash debloat/apply.sh G1
bash debloat/g2lite.sh
```

**4. Install verified applications as needed.** The F-Droid fetcher checks the signed index, pinned key, APK SHA-256, and APK signer.

```bash
python3 -I apk-manager/fdroid_fetch.py <package> ...
```

**5. Install the terminal environment.** In the tested setup, Termux comes from Google Play because Play Protect blocks the F-Droid version. From the repository root on your computer:

```bash
adb push . /sdcard/Download/seeker-zero
```

Then, in Termux on the phone:

```bash
bash /sdcard/Download/seeker-zero/terminal/termux-setup.sh
```

This installs the terminal tools, agent, dashboard, and both local model files, with SHA-256 verification.

**6. Connect Shizuku.** In the Shizuku app, use **“Use Shizuku in terminal apps” → “Export files”** into `terminal/shizuku/`, then run `terminal/seeker-setup-shizuku` in Termux. After a reboot, use `terminal/start-shizuku.sh` from the computer as documented.

**7. Install the launcher.** Build it with `launcher/build.sh`, install the generated APK, and select it as the home app. The launcher offers **system → wallpaper: black**, preserving the previous wallpaper.

**8. Restore when needed.** The project tracks reversible changes:

```bash
bash restore/restore.sh
# Or restore one group:
bash restore/restore.sh <group>
bash tests/seedvault_check.sh
```

Review the script documentation before executing it. Test the Seed Vault manually as well: [`tests/SEEDVAULT_MANUAL.md`](tests/SEEDVAULT_MANUAL.md).

## REPRODUCE THE TESTS

**On the computer:**

```bash
python3 ai/test_seeker_ai.py
python3 terminal/test_seeker_dash.py
bash tests/test_bench_dry.sh
python3 tests/bench_decide.py --test
```

The agent test suite covers **30 scenarios**, including approval boundaries, protected folders, quote-based bypass attempts, command injection through notifications, context handling, and stopping during a task.

**On the phone:**

```bash
bash tests/termux-round6.sh
bash tests/termux-round7.sh
bash tests/health.sh
bash tests/seedvault_check.sh
```

The tests are provided for inspection and reproduction. They do not establish comprehensive security or general reliability on every device.

## INSIDE THE REPOSITORY

| Path | Purpose |
|---|---|
| [`ai/`](ai/) | Python agent, local model integration, installer, and tests |
| [`terminal/`](terminal/) | Termux setup, dashboard, and Shizuku utilities |
| [`launcher/`](launcher/) | Terminal-first Android launcher |
| [`debloat/`](debloat/) | Documented, health-checked reduction of unwanted packages |
| [`restore/`](restore/) | Reversal of journaled changes |
| [`apk-manager/`](apk-manager/) | Verified F-Droid APK acquisition |
| [`audit/`](audit/) | Read-only device inspection |
| [`privacy/`](privacy/) | Network/privacy inspection utilities |
| [`tests/`](tests/) | Benchmarks, validation, raw results, wallet health checks |
| [`adb.sh`](adb.sh) | ADB helper |

## THE IDEA

You should be able to open a terminal on your own phone, run an AI on your own hardware, inspect what it can access, deny what it cannot, and shut the whole thing off.

That does not make the device magically private. It makes the architecture **visible, local, and controllable**.

Use the security and network tools only on devices and systems you own or have permission to assess.

---

> **They removed the payphones.**
>
> **We built our own hardline.**
>
> # ZION-CELLPHONE
>
> *The last hardline. The new way out.*
