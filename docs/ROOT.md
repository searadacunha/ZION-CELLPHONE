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
| Block the network of one app | `cmd connectivity set-chain3-enabled` / `set-package-networking-enabled` | **tested on 13/11**: a test app's request works, fails while cut, works again (`tests/firewall_real.sh`); `privacy/firewall.sh` and OPERATOR's `net_block` wrap them, journaled; forgotten by Android at a restart |
| Per-app traffic counters | eBPF map `mAppUidStatsMap`, read from `dumpsys netstats detail` | used by `privacy/netwatch.sh` |
| Battery current, voltage, charge counter | `/sys/class/power_supply/battery` | read by `tests/bench_power.py` |
| Temperatures and thermal status | `dumpsys thermalservice` | read by the dashboard and the benchmarks |
| System logs of every app | `logcat` | used by OPERATOR's `crashes` and `logs` tools |
| Screenshots, taps, typing | `screencap`, `input` | used by the tests and by OPERATOR's `ui` tool |
| Read the screen of the app in front | the accessibility tree through `UiAutomation`, started by the shell with `app_process` (`UiShell` in the launcher's APK), or `uiautomator dump` | used by OPERATOR's `ui` tool; 0.3 to 0.5 s per read, see [RESULTS.md](RESULTS.md) |
| Type any text, accents included | `ACTION_SET_TEXT` through the same connection (`input text` crashes on "é") | used by OPERATOR's `ui` tool |
| List USB accessories and radio states | `dumpsys usb`, `dumpsys bluetooth_manager`, `dumpsys nfc`, `cmd wifi` | used by `zion-hw`; with nothing plugged in on 13/11 |
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
| Capture other apps' packets at the interface | raw sockets | a VPN-based capture app (PCAPdroid), driven by `privacy/pcap.sh`; its first start asks the owner two questions |
| Open a USB serial device as `/dev/ttyUSB0`, or an SDR dongle directly | kernel drivers and device nodes are root-only | Android's USB host API: `termux-usb` hands a file descriptor to a program; for an SDR, a driver app serving rtl_tcp on 127.0.0.1 (**not tested**: no accessory was available) |
| Read another app's private files (`/data/data/...`) | app sandbox | nothing: that is the sandbox doing its job |
| Change CPU governors, clocks or thermal limits | sysfs is root-only | choose llama.cpp threads and cores (`-t`, `-C`), see `tests/termux-p6-sweep.sh` |
| Change SELinux, or run a different kernel | needs an unlocked bootloader | none |

Rooting this phone would need an unlocked bootloader. That changes the verified boot state (`ro.boot.verifiedbootstate`,
`ro.boot.flash.locked`) that `tests/seedvault_check.sh` requires before it calls the **Seed Vault** healthy. ZION ZERO
never unlocks it, and never touches `com.solanamobile.*` packages.
