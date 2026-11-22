# Privacy audit

What was measured on the tested Seeker, how, and what is still open. This reduces what the phone sends; it does not
make it invisible. Google Play Services stay installed (security updates, push, the wallet's dependencies).

## 1. Inventory

`audit/collect.sh` (read-only) records the phone's packages and public service state; `debloat/inventory.py` joins
them with the UAD-NG debloat list (`debloat/uad/uad_lists.json`, from the UAD-NG project, not shipped here) and
`debloat/classify.py` sorts every package into four classes: needed (kept),
replaceable, optional, never touched (could break boot or integrity). A package nobody identified stays "needed". The
groups and their trade-offs are in [`debloat/PLAN.md`](../debloat/PLAN.md).

## 2. What each app sends

`privacy/netwatch.sh` samples the phone's sockets over a window (owner app, remote address, port) and reads the
kernel's per-app byte counters (the eBPF map `mAppUidStatsMap` in `dumpsys netstats detail`) before and after.
`privacy/netwatch_report.py` groups the result by vendor and resolves the remote names. No VPN, no root, no
interception: it shows who talks to whom and how much, not what is said.

Baseline of 12/11/2026, 20 minutes, phone on Wi-Fi and not in use (apps still ran in the background: "Other apps" is
mostly one social app and F-Droid), after the debloat groups G1 and G2-lite, Private DNS still on Mullvad:

| Vendor group | Bytes moved | Distinct destinations |
|---|---:|---:|
| Android system (system, root, netd, network stack) | 2,885,015 | 5 |
| Google (Play Services, services framework, key provisioning) | 257,301 | 7 |
| Other apps | 62,843 | 7 |
| Solana Mobile (dApp Store) | 41,420 | 3 |

## 3. Google and manufacturer connections

- **Google Play Services / services framework**: Google front ends on port 443 and the push channel on port 5228.
- **Key provisioning** (`com.google.android.rkpdapp`): one Google connection on 443. It provisions the keys used for
  hardware key attestation; it is kept.
- **System**: DNS-over-TLS on port 853 (Private DNS), DHCP to the local router; part of the Google push traffic is
  counted under uid 0.
- **MediaTek**: no connection seen in this window.

## 4. What stays, and why

Calls, mobile network and Wi-Fi stacks; Google Play Services, the services framework and the Play Store (Google Play
system updates, push notifications, apps that need them); the Seed Vault, wallet and dApp Store packages and the
TrustKernel secure-hardware packages, which the change scripts (`debloat/ops.sh`) and OPERATOR refuse to change even
when asked.

## 5. Reversible changes

Every change is written to `restore/journal.tsv` with its old value before it is made, and `restore/restore.sh` undoes it
(the whole journal, or one group):

| Group | Changes |
|---|---|
| G1 | 35 unused Google and manufacturer packages disabled |
| G2-lite | 23 Google apps disabled, 16 permissions of Play Services revoked, 11 F-Droid replacements installed (verified), default apps and keyboard switched, Private DNS on |
| P13-dns | Private DNS moved to AdGuard DNS (12/11) |

## 6. DNS and filtering

Private DNS (DNS-over-TLS) answers for the whole phone. Tracker names really blocked, out of 8 tested from the computer
over DNS-over-TLS (12/11): Mullvad `base` 6, AdGuard DNS 5, DNS4EU `noads` 4, DNS4EU `protective` 0, Quad9 0; none of
the 8 ordinary names tested alongside was blocked. Mullvad announced on mullvad.net the end of its public DNS service
(read on 12/11/2026), so the phone moved to **AdGuard DNS**, and `debloat/g2lite.sh` now sets it. On the phone after the switch: `app-measurement.com`,
`doubleclick.net`, `googleads.g.doubleclick.net` and `adservice.google.com` resolve to nothing (127.0.0.1); `google.com`,
`github.com`, `huggingface.co` and `mtalk.google.com` resolve.

`privacy/firewall.sh` blocks or allows the network of one app at a time through Android's own per-app chain (shell
user, no root, no VPN), journaled and undone by `restore/restore.sh`. **It has not been run on the phone yet.**

## 7. Watching for new talkers

`python3 -I privacy/netwatch_report.py --compare privacy/<A> privacy/<B>` lists, for B against A, the bytes per
vendor and every new app or destination.

## 8. Before and after

"After" capture of 13/11/2026 from 07:30, the same 20 minutes, phone on Wi-Fi with AdGuard DNS, plugged into a
computer, screen on and not used (the local model server was loaded and idle; it listens on 127.0.0.1 only). One
window each, at different times of day: an indication, not a controlled comparison.

| Vendor group | Bytes before | Bytes after | Destinations before | Destinations after |
|---|---:|---:|---:|---:|
| Android system | 2,885,015 | 394,415 | 5 | 2 |
| Google | 257,301 | 24,431 | 7 | 2 |
| Other apps | 62,843 | 29,852 | 7 | 3 |
| Solana Mobile | 41,420 | 0 | 3 | 0 |
| Total | 3,246,579 | 448,698 | 22 | 7 |

New destinations in the "after" window: AdGuard DNS (`dns.adguard-dns.com`, the new Private DNS), one Google front
end for Play Services, and two new addresses of the social app already seen in the baseline. The capture folders stay
off the public repository: they describe one person's phone and network.

## 9. Cutting one app off the network (13/11/2026)

`privacy/firewall.sh block|allow|status|reapply` (from the computer) and OPERATOR's `net_block`, `net_allow`,
`net_status` actions (on the phone, asked first, journaled with their undo) use Android's own firewall chain
`FIREWALL_CHAIN_OEM_DENY_3` through the shell identity: `cmd connectivity set-chain3-enabled` and
`set-package-networking-enabled`. No root, and the VPN slot stays free for whatever you run there.

Tested for real with `tests/firewall_real.sh` ([`tests/phone/2026-11-13-firewall/firewall.log`](../tests/phone/2026-11-13-firewall/firewall.log)):
a throwaway app that fetches one URL when asked.

| Step | A web page (`https://example.com/`) | The phone's own service on `127.0.0.1` |
|---|---|---|
| network open | HTTP 200 | HTTP 200 |
| app cut | fails: the name is not even resolved | fails: connection times out |
| network given back | HTTP 200 | (not asked again) |

- The block is real, and it is total for that app: it also loses the phone's local services. Cutting Termux or the
  launcher would therefore cut the local AI: the scripts refuse those, as they refuse the Seed Vault, the Solana apps,
  Android's core packages and any app that shares a system uid.
- The phone ends as it started: `restore/restore.sh` undoes the group, the chain is off again, the test app is removed.
- Android forgets the chain at a restart (its help text calls it a debugging switch). `privacy/firewall.sh reapply`,
  or OPERATOR's `net_status` with `reapply`, blocks again what the journal says. Persistence across a restart was
  **not tested**.
- The first version of the script had never run on the phone and expected `true`/`false`: Android answers
  `chain:enabled` and `package:deny`. Corrected on 13/11, and the dry-run test now imitates the real answers.

## 10. Which names an app asks for

`privacy/pcap_domains.py` reads a capture file and lists the names that travel in clear: the server name of each TLS
connection, HTTP Host headers, DNS questions. Its parser is tested offline against packets built for the test.
`privacy/pcap.sh start [PKG]` / `stop` drives PCAPdroid, already installed, as an on-demand recorder for one app.

- **Not tested on the phone**: PCAPdroid had never been given the VPN slot, and its first start shows two questions
  (its own control permission, Android's VPN request). They are the owner's to answer; no script taps them and
  OPERATOR's screen tool refuses to.
- PCAPdroid records through Android's single VPN slot: no other VPN app runs while it records.
- With Private DNS on, the DNS questions are not in the capture (they travel inside TLS to the resolver): names then
  come from TLS and HTTP only. QUIC and Encrypted Client Hello hide the name by design; the address is still listed.

## 11. What this does not do

Without root, nothing here blocks single components of an app, filters by domain inside an app, cuts off system
uids, or decrypts traffic. Google Play Services stay on for security updates and can still see the device. The
carrier, the Wi-Fi network and every server contacted still see their side of each connection. This phone is more
private than it was; it is not invisible and not untraceable.
