# De-Googling plan

`classify.py` sorts every package found on the phone into four classes, from the phone's own package list (`inventory.py`) and the public UAD-NG package list (download its `uad_lists.json` into `debloat/uad/` first).

| Class | Meaning | Treatment |
|---|---|---|
| A | needed by the system, by security or by the Seed Vault | kept |
| B | needed by a feature, replaceable | group G2, on the owner's approval |
| C | optional, no major effect | group G1 |
| D | touching it can break boot or integrity | never touched |

Rule: a package UAD-NG does not know stays in A until identified. The Solana and TrustKernel packages are also in a protected list in `ops.sh` that every script refuses to touch.

## G1: unused packages (35, reversible)
List and reasons: `groups/G1.txt`. Apply: `debloat/apply.sh G1`. Undo: `restore/restore.sh G1`.

## G2-lite: every Google app (23, reversible)
List: `groups/G2lite.txt`. Apply: `debloat/g2lite.sh`. It installs the replacements first (verified F-Droid APKs), makes them the defaults (keyboard, dialer, SMS, browser), disables the Google apps, revokes runtime permissions of Play Services and turns on a filtering Private DNS. Undo: `restore/restore.sh G2lite`.

Why Play Services, the services framework and the Play Store stay, measured on the Seeker:

1. System updates are delivered through Play Services (`com.google.android.gms/.update.SystemUpdateActivity`). Without it, no more security patches.
2. Seed Vault Wallet scans QR codes with ML Kit inside Play Services and gets its notifications through Firebase Cloud Messaging. Both stop without it.
3. The location permission of Play Services is fixed by the system: it cannot be revoked.

Going further (G2-full: Play Services, the services framework and the Play Store disabled too) costs the points above and the push notifications of every app that uses them. Not applied.
