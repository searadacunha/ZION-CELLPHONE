# Without root, and what root would add

ZION ZERO runs with a **locked bootloader and no root**. Everything below was done on the tested Solana Seeker
(Android 16, security patch 2026-09-05) through three identities Android grants on purpose:

- **Termux** (the Termux app's own user): files of Termux, the local model, Python, compilers, `proot-distro` Linux.
- **Shizuku / ADB shell** (uid 2000, the same rights as `adb shell`): reached from Termux with `rish`.
- **Android APIs** used by the ZION ZERO launcher and Termux:API (battery, notifications, wallpaper, shortcuts).

## Done without root, on the phone

| Capability | How | Status |
|---|---|---|
| Disable or re-enable an app for the user | `pm disable-user`, `pm enable` | used: groups G1 and G2-lite, journaled, reversible |
| Revoke app permissions | `pm revoke`, `appops` | used: 16 permissions of Play Services |
| Install an APK | `pm install` | used: verified F-Droid apps, the launcher |
| Change a system setting | `settings put` | used: Private DNS, stay awake while charging |
| Change a default role (home app, keyboard) | `cmd role add-role-holder` | used, journaled |
| Block the network of one app | `cmd connectivity set-chain3-enabled` / `set-package-networking-enabled` | commands present for the shell user on this build; `privacy/firewall.sh` wraps them, journaled; **not yet run on the phone** |
| Per-app traffic counters | eBPF map `mAppUidStatsMap`, read from `dumpsys netstats detail` | used by `privacy/netwatch.sh` |
| Battery current, voltage, charge counter | `/sys/class/power_supply/battery` | read by `tests/bench_power.py` |
| Temperatures and thermal status | `dumpsys thermalservice` | read by the dashboard and the benchmarks |
| System logs of every app | `logcat` | used by OPERATOR's `crashes` and `logs` tools |
| Screenshots, taps, typing | `screencap`, `input` | used by the tests |
| Wi-Fi state, on/off | `cmd wifi` | used; see the Wi-Fi note in [RESULTS.md](RESULTS.md) |
| Notifications, vibration | `cmd notification post`, `cmd vibrator_manager` | used by the measurement chain |
| A full Debian or Alpine userland | `proot-distro` inside Termux | Debian 13 installed in 9 s, see [RESULTS.md](RESULTS.md) |

Shizuku has to be started again after each reboot: `terminal/start-shizuku.sh` from the computer (tested after a
reboot on 12/11; Shizuku's own wireless-debugging start was not tested here). None of these commands bypasses Android's permission model: they are the rights of the
shell user that `adb` already has.

## What would really need root

| Wish | Why root | Without root instead |
|---|---|---|
| Remove system apps for good, or change `/system` | the system partition is read-only and verified (dm-verity) | disable them for the user (reversible) |
| A kernel firewall (iptables/nftables rules) | `CAP_NET_ADMIN` | Android's per-app chain above, or a local VPN app (RethinkDNS) |
| Capture other apps' packets at the interface | raw sockets | a VPN-based capture app (PCAPdroid) |
| Read another app's private files (`/data/data/...`) | app sandbox | nothing: that is the sandbox doing its job |
| Change CPU governors, clocks or thermal limits | sysfs is root-only | choose llama.cpp threads and cores (`-t`, `-C`), see `tests/termux-p6-sweep.sh` |
| Change SELinux, or run a different kernel | needs an unlocked bootloader | none |

Rooting this phone would need an unlocked bootloader. That changes the verified boot state (`ro.boot.verifiedbootstate`,
`ro.boot.flash.locked`) that `tests/seedvault_check.sh` requires before it calls the **Seed Vault** healthy. ZION ZERO
never unlocks it, and never touches `com.solanamobile.*` packages.
