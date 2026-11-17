# Other systems for the Seeker: what is real, what is not

Checked on **17/11/2026**. Every "not found" below means searched and not found on that date, not proven absent.
Nothing here was flashed, unlocked or tried on the phone: ZION-CELLPHONE never unlocks the bootloader.

## The tested phone

| Fact | Value | Source |
|---|---|---|
| SoC | MediaTek Dimensity 7300 (`ro.soc.model=MT6878`, `ro.board.platform=mt6878`) | [Solana Mobile](https://www.solanamobile.com/seeker), the phone's own properties |
| RAM | 8 GB (about 7.5 GB visible to Android) | Solana Mobile, `/proc/meminfo` |
| Build | Android 16, `BP2A.261008.100.A3`, security patch 2026-09-05, `user/release-keys` | phone properties |
| Boot chain | `ro.boot.verifiedbootstate=green`, `ro.boot.flash.locked=1`, `ro.boot.vbmeta.device_state=locked`, dm-verity `enforcing` | phone properties |
| Storage | file-based encryption (`ro.crypto.type=file`) | phone properties |
| Secure hardware | a StrongBox (TrustKernel applet, provisioned, root-of-trust binding on) next to the TEE; Solana Mobile says the Seed Vault keeps its keys in secure hardware | phone properties; [Solana Mobile](https://solanamobile.com/blog/seed-vault-wallet-solana-seekers-native-mobile-wallet) (vendor statement) |
| OEM unlock | `ro.oem_unlock_supported` is not set on this build | phone properties |

## The options, side by side

| Option | Exists for the Seeker? | Seed Vault | Verified boot | Autonomy it allows | Verdict |
|---|---|---|---|---|---|
| **Stock Android, hardened and minimal** (what ZION does) | yes | kept | green, locked | everything below, through Termux and Shizuku | **the base** |
| **Android + Shizuku** (uid 2000, ADB-level shell) | yes, used here | kept | unchanged | screens, settings, apps, firewall chain, permissions, logs; no `/system`, no kernel, no raw sockets | **used**: the most an unrooted phone gives |
| **Android rooted** | would need an unlocked bootloader: no official procedure found, `ro.oem_unlock_supported` unset | at risk: unlocking changes the boot state the Seed Vault checks rely on; no Solana Mobile statement about it found | lost (orange/yellow) | iptables, `/system`, governors, any file | **studied only**, not done |
| **Linux mobile, native** (postmarketOS, Droidian, Ubuntu Touch) | **no device port found**. postmarketOS ships a mainline kernel package for the SoC, [`linux-postmarketos-mediatek-mt6878`](https://pkgs.postmarketos.org/package/main/postmarketos/aarch64/linux-postmarketos-mediatek-mt6878), and [upstream work](https://www.collabora.com/news-and-blog/news-and-events/collabora-mediatek-pushing-boundaries-on-the-latest-iot-boards-and-chromebooks.html) targets other MT6878 phones (CMF Phone 1) | gone: the Seed Vault is Android software over the secure hardware | none comparable | a real Linux, but modem, camera, GPU and power management would have to be brought up for this board | **not possible today** without a Seeker port and an unlock |
| **Custom ROM** (LineageOS, /e/OS, CalyxOS) | **not found** for the Seeker. LineageOS supports the **Saga** (`ingot`, the previous Solana phone), [not the Seeker](https://wiki.lineageos.org/devices/ingot/install/) | gone | only with a relockable bootloader and the ROM's own keys, none exists here | same as stock, minus Google | **not available** |
| **GrapheneOS** | **no**: [Pixels only](https://grapheneos.org/faq) | n/a | its own, on supported Pixels | a separate, security-first phone | **only on a Pixel** |
| **Debian inside Termux** (`proot-distro`) | yes, used here | kept | unchanged | a full Linux userland, no root, no kernel change | **used**: Debian 13 installed in 9 s |

Kernel source for the Seeker: **not found** (no kernel, device tree or AOSP repository in [Solana Mobile's GitHub](https://github.com/solana-mobile)).

## Why Android stays

- It is the only system that keeps the **Seed Vault**, verified boot and the StrongBox in their intended state.
- Shizuku plus Termux already give the agent screens, settings, apps, per-app firewall, permissions, logs and a full Linux userland, with no unlock.
- Every alternative above needs an unlocked bootloader first, and no source documents that for this phone, nor what it does to the wallet.

So ZION keeps Android and pushes its interface to the side: the home screen is a terminal-first launcher, the AI answers on its own screen, and most of the system is reached from the terminal.

## What stays out of reach without root (and is said, not hidden)

- Shizuku stops at every reboot; its own wireless-debugging restart was not tested here. Until it runs again, OPERATOR has no screen and no system actions (zion waits).
- One VPN slot: a firewall VPN app and a capture app cannot run together.
- Android forgets the per-app firewall chain at a restart (`net_status reapply` puts it back, with Shizuku running).
- The AI and its supervisor share Termux's Linux user: a malicious package inside Termux could act as both (see [AUTONOMY_SECURITY.md](AUTONOMY_SECURITY.md)).
- A boot-ROM flaw of the Dimensity 7300, reachable with physical access and electromagnetic fault injection, is reported by news sites as found by Ledger's lab and not fixable in software ([one such report](https://coin360.com/news/mediatek-dimensity-7300-bootrom-flaw-crypto-security-warning)). Not verified here: the original disclosure was not read.
