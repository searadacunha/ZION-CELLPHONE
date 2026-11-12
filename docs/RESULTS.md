# Measured results

Device: one Solana Seeker, Android 16, security patch 2026-09-05, MediaTek SoC (cores 4-7 Cortex-A78, 0-3 Cortex-A55),
Termux from Google Play (build 2026.10.09), llama.cpp compiled on the phone (commit `9e9619d`, CPU backend).
Each figure comes from **one run** unless stated, on the date given; raw files are in [`tests/phone/`](../tests/phone/).
Nothing here is extrapolated to other phones.

## 1. Termux opens on OPERATOR (12/11/2026)

| Action on the phone | Result |
|---|---|
| Open Termux from its icon (cold) | OPERATOR starts |
| ZION ZERO launcher, `ai` | OPERATOR starts (first use only: Termux asks once to pin the shortcut, one tap) |
| ZION ZERO launcher, `terminal` | interactive bash, no OPERATOR (`ZION_TERMINAL_MODE=1`) |
| `/exit` in OPERATOR | a usable shell |
| interactive `zsh` | OPERATOR, then a usable zsh |
| `bash -c ...`, `zsh -i -c ...`, scripts, pipes | nothing starts |
| After a reboot | home is ZION ZERO; `ai`: OPERATOR running after 5 s, model ready after about 26 s, first word 1.33 s; `terminal`: a shell without OPERATOR |

Raw: `tests/phone/p1-*.txt`, `p1-setup.log`. On the computer, `terminal/test_zion_shell.py` replays these cases in
real bash and zsh on a pseudo-terminal.

## 2. A Linux station inside Termux (12/11/2026)

`proot-distro` 5.3.0, no root:

| Step | Time |
|---|---|
| Install Alpine | 4 s |
| Install Debian 13 | 9 s |
| `apt-get install python3 git` in Debian | 107 s (Python 3.13.5, git 2.47.3) |
| `python3 -c pass`, native Termux | 55 ms |
| `python3 -c pass`, inside Debian (with the proot start) | 427 ms |

Native Termux stays the fast path; Debian is for packages Termux does not have. Raw: `tests/phone/p2-linux.log`.

## 3. The local AI

Default model: HauhauCS Qwen3.5-4B Uncensored Q4_K_M. Context 4,096 tokens, 4 threads.

### First answer

| Situation | Time |
|---|---|
| First message, nothing cached (1,180-token agent prompt) | 43.4 s |
| Same, after OPERATOR restored the saved start of the conversation (196 MB, saved in 0.19 s, restored in 0.21 s) | 1.1 s |
| Whole `ai` command from a stopped server, saved start present | 8.8 s (first token 1.03 s) |
| Same without the saved start (computed and saved on the way) | 70.0 s |
| Server already running | 1.5 s |

Raw: `tests/phone/probe-slots.json`, `tests/phone/p5-ttft.log`.

### Memory when idle

OPERATOR lets llama-server unload the model after 10 minutes without use: resident memory went from 3,507 MB to
217 MB; the next request reloads it (51.9 s without the saved start; with it, see above).

### Tried and not kept

| Option | Result |
|---|---|
| Speculative decoding `--spec-type ngram-mod` | 5.52 vs 5.61 tokens/s: no gain |
| `draft-mtp` | refused by the server with this model |
| Model read into RAM instead of mapped (`--load-mode none`) | **kept**: server peak 3.5-3.6 GB instead of 5.1-5.5 GB, same speed |

### Default against fallback (12/11/2026)

The table of the [README](../README.md#proof-not-promises) (`tests/phone/bench-*.json`): the default model was chosen
by `tests/bench_decide.py` with a rule written before the measurements.

### Speed by thread layout (llama-bench)

The run of 12/11 16:31 measured only the first layout (a script bug, fixed): 4 threads, prompt 512 tokens and
generation 128 tokens: HauhauCS Q4_K_M 26.13 and 5.61 tokens/s, Qwen3.5-4B Q4_0 33.64 and 5.54 tokens/s
(`tests/phone/p6-sweep.jsonl`). The full sweep (big cores only, 2-3-4-8 threads, polling) runs in
`tests/termux-chain.sh`; results will be added here.

### Other models

Candidates: Qwen3.5-4B Q4_0, Qwen3-4B-Instruct-2507 Q4_0, Ministral-3-3B-Instruct-2512 Q4_0, granite-4.0-micro Q4_0.
The rule was written before any of them ran: a candidate becomes the default only with at least 2 more correct French
answers out of 24 (`tests/eval_fr.py`), no more than 1 tool call and 1 Python task lost, no server error, at least
90 % of the default's generation and prompt speed, and at most 300 MB more memory. It is applied by
`python3 tests/bench_decide.py --p5 DIR`. Results will be added here.

## 4. Battery and temperature

| Measurement | Result |
|---|---|
| Peak CPU / skin temperature during the 12/11 benchmark, default model | 83.5 / 48.5 °C (thermal status 3 reached) |
| Drain at rest and during inference, unplugged | **not measured yet** |

`tests/bench_power.py` measures, unplugged: 20 minutes at rest (screen off), then 8 minutes of continuous generation
for each thread layout, with energy per token from the battery's charge counter, current, temperatures, thermal
status and screen state every 15 s. Android's thermal protections are never changed. On this phone the battery
current reads **positive while charging**, checked against the charge counter on 12/11.

## 5. Known issues

- After a reboot, or after Wi-Fi is switched off by command, Wi-Fi stays on but does not reconnect until
  Settings > Wi-Fi is opened (then it connects in 4 to 6 s). Cause not found.
- Android killed Termux once for lack of memory during a benchmark with a 4B model; benchmarks run with
  `--cache-ram 0`.
- `rish` mixes its standard output and error at random; the tools read both.
- On this phone `llama-server` shows up as `linker64` in the process list.
