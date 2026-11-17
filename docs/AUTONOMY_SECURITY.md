# OPERATOR — Autonomy and high-assurance security review

Review branch status, 2026-11-17: **new UI code; only isolated Python validation tested off-device**. The earlier README performance and agent benchmarks do not validate this UI feature.

## Goal and operating system boundary

Goal: a terminal-first, mostly unattended, offline AI operator that can navigate supported apps, execute scoped tasks, and verify outcomes. Termux and Debian proot run **on top of Android**; they do not replace the kernel, drivers, trusted execution environment, or radio firmware.

The tested **Solana Seeker** runs Android 16 with a locked bootloader and a hardware-backed Seed Vault. No independently verified, maintained alternative OS image for this exact Seeker hardware with secure bootloader relocking and full Seed Vault support has been established. Do not confuse the older Solana Saga's custom ROM support with the Seeker. Never flash generic MediaTek images, unlock, modify vendor partitions, disable SELinux or Verified Boot, or risk the wallet to claim Android was "destroyed."

An officially supported Google Pixel running GrapheneOS can be a useful separate security-first platform; **GrapheneOS is not supported on the Seeker** and that Pixel would not retain its Seed Vault. Replacing the OS is a separate hardware project, not a requirement for excellent terminal control.

Official: https://solanamobile.com/seeker ; https://grapheneos.org/faq ; https://grapheneos.org/install/web

## What's implemented in this branch

New OPERATOR Android actions through the Shizuku/rish shell (uid 2000, NOT root):

| Android action | Purpose | Default authorization |
| --- | --- | --- |
| app_open (package) | Launch installed app | write / auto; protected packages refused |
| ui_focus | Inspect top resumed activity | read / auto |
| ui_home, ui_back | Android navigation | write / auto |
| ui_tree (package) | Dump UIAutomator XML into a temporary file and delete it | sensitive / ask |
| ui_tap (package, value=x,y) | Tap coordinates | sensitive / ask |
| ui_swipe (package, value=x1,y1,x2,y2,ms) | Swipe | sensitive / ask |
| ui_text (package, text) | Type 1–200 printable ASCII characters | sensitive / ask |

For any UI-tree/tap/swipe/text action, the bridge verifies that its **exact package** is (a) in the configured explicit list ui_allowed_packages AND (b) matches the Android foreground package. The default allowlist is empty, which **denies all scoped UI operations**. The agent cannot override these checks by persuasion. A race remains between the check and input; this is an initial bridge, not a transaction-safe UI executor.

Example ~/.config/seeker-ai/config.json fragment; substitute your own VERIFIED harmless test app package:

    {
      "ui_allowed_packages": ["org.example.notes"],
      "android_policy": {
        "ui_tree": "ask",
        "ui_tap": "auto",
        "ui_swipe": "auto",
        "ui_text": "ask"
      }
    }

Then use ai --status. Do not enable blanket auto execution for arbitrary shell, Python, git network operations, package installation, permission changes, payments, wallet or remote hosts. For unattended operation, authorize only a known app/action combination. Protect credentials and all wallet signing behind an independently enforced physical/biometric approval.

**Unverified on physical Seeker:** action bridge, UIAutomator XML availability, focus parsing on this firmware, gesture reliability and unattended task success. These must be tested before rollout.

## Relevant upstream research

Source code should be audited and selectively adapted, not installed blindly.

| Project | Specific useful capability | Limit |
| --- | --- | --- |
| https://github.com/RikkaApps/Shizuku | Supported Android privileged-shell bridge | ADB shell not root; startup requires authorized mechanism |
| https://github.com/xjunz/AutoTask | Shizuku + AccessibilityService for automation | Accessibility is exceptionally powerful |
| https://github.com/droidrun/mobilerun | UI trees, gestures, mobile task loops | Avoid optional cloud infrastructure for local-only design |
| https://github.com/yashas-13/accessdroid-termux | Termux-to-accessibility control | Review IPC, exported receivers, permissions and APK signer |
| https://github.com/niki914/zafiro | Agent with phone and shell tools | BYOK/remote features must be explicitly disabled if local only |
| https://github.com/zai-org/Open-AutoGLM | Observe/plan/act UI control loop | Frequently relies on off-device model/ADB |
| https://github.com/agents-io/PokeClaw | On-device agent ideas | Audit inference and bridge claims independently |
| https://github.com/AhmetCanArslan/ShizuWall | Native per-app firewall, no VPN | Restart/persistence and OS support must be measured |
| https://github.com/celzero/rethink-app | Local VPN, DNS, per-app firewall, WireGuard | Only one active Android VpnService per user in general |
| https://github.com/emanuele-f/PCAPdroid | No-root traffic capture and diagnostics | Diagnostic evidence, not a guarantee of zero egress |
| https://github.com/GrapheneOS | Verified boot and stronger exploit defenses | Does not provide an official Seeker build |

Shizuku official startup guide: https://shizuku.rikka.app/guide/setup/ . Some Shizuku releases mention trusted-Wi-Fi automatic starting on Android 13+, but that feature has **not been verified** on this Seeker.

## CIA security model: confidentiality, integrity, availability

"Confidentiality at CIA level" is not a third-party certification or a measurable guarantee. Build an explicit threat model and test claims, including OS compromise, physical seizure, malicious apps, network operators, supply-chain attacks, prompt injection, and accidental operator actions.

### Confidentiality

- Preserve encrypted storage, verified boot, updates, a strong phone passphrase, short lock timeout, and protected hardware keys. Encryption at rest does not protect everything while unlocked.
- Keep llama-server bound to 127.0.0.1. No internet AI provider by default. Inspect outbound requests by process/app, including cellular, Wi-Fi, DNS, IPv6 and reboot.
- Deny network access where unneeded with a tested per-app firewall; use RethinkDNS or ShizuWall as appropriate, and PCAPdroid for measurement. Avoid assuming two simultaneously active local-VPN apps work together.
- Prefer Android hardware-backed Keystore/StrongBox for secrets, with authorization outside the model. Never give the model a seed phrase, raw signing key, unrestricted wallet API or authority to approve financial transfers.
- Restrict Accessibility, notification listener, clipboard, overlay, screen capture, device admin, installation and debugging permissions; install only signed audited components.
- The existing agent records prompt excerpts in history and entire conversations in session files. UI XML and screenshot artifacts may contain messages, codes and personal data. Restrict files to 0600, minimize retention, redact secrets and validate backups. **This branch does not claim encrypted chat logs or automatic redaction.**

### Integrity

- Keep verified boot, SELinux enforcing, vendor security updates and Seed Vault baseline checks. Do not disable secure-hardware provisioning simply to remove Google packages.
- Pin dependency versions and signing certificates, validate downloads and hashes, scan code, and review upstream licenses. Never download-and-execute unreviewed remote scripts on the phone.
- Consider all screen/app/web/notification/README contents untrusted, including prompt injection. Policy validation MUST live in code, not in the model's prompt.
- Confirm actions with a fresh foreground/UI read. Bounded retries, idempotence and separate approval for irreversible actions are essential. A successful input command is not a verified task outcome.

### Availability

- Protect launcher, recovery access, Seed Vault, updates, mobile data/radios and hardware identity. Maintain tested offline backup and reversible system changes.
- No second heavy on-device model concurrently on 8 GB RAM. Respect thermal protection. Don't disable throttling.
- Treat restart, Shizuku authorization loss, lock screen, UI reconfiguration and unexpected foreground apps as conditions to STOP autonomous action.
- Keep a non-AI way to force-stop OPERATOR and restore Android defaults.

## Limitations and next phases

1. **Validate on physical Seeker:** run python3 ai/test_zion_ui.py and python3 ai/test_seeker_ai.py, verify rish, UI tree and gestures on a throwaway app. Test malformed arguments, wrong foreground, lock screen, password dialog, unexpected overlay, airplane mode and reboot.
2. **Structured UI bridge:** review and potentially adapt an open-source AccessibilityService, but build a minimal locally signed APK with authenticated, non-exported IPC, app scope, explicit grants and precise state verification. Use only trusted source; do not install unattended from a URL.
3. **Reliable vision:** the current Qwen3.5-4B text agent does not understand raw screenshots. UIAutomator XML will miss games, some WebViews and custom graphics. Add an independently benchmarked on-device multimodal backend only if it fits the RAM/power budget.
4. **Supervisor:** implement scoped task queue, time and action budgets, per-step verification, crash recovery, auditable decision log, retention limits and an emergency stop.
5. **Independent security audit:** red-team prompt injection and dangerous-permission misuse; demonstrate low false-action rate and limited egress before any "fully autonomous" or high-confidentiality claim.
6. **OS migration feasibility:** only revisit after device-specific signed builds, bootloader relocking, full firmware and Seed Vault compatibility are demonstrated.

Current measured result: isolated Python zion_ui validation passed off-device. Physical-device and full-agent tests for this branch have NOT been run. Preserve the existing README and separate measured history from planned work.
