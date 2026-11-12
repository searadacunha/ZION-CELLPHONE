#!/usr/bin/env python3
"""Classify every package of debloat/inventory.csv into A/B/C/D + proposed group. Writes debloat/classification.csv.
A = needed for the system, security or the Seed Vault (kept)      B = needed for a feature, replaceable (G2, needs approval)
C = optional, disable without major effect (G1 done, G3 proposed) D = touching it can break boot or integrity (never touched)
Rule of last resort: a package UAD-NG does not know stays in A until identified."""
import csv
from pathlib import Path

root = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(root / "inventory.csv")))
g1 = {l.split("#")[0].strip() for l in open(root / "groups/G1.txt") if l.split("#")[0].strip()}

A = {  # explicit keeps, with the reason
    **dict.fromkeys(["com.solanamobile.seedvaultimpl", "com.solanamobile.wallet"], "Seed Vault"),
    **dict.fromkeys(["com.solanamobile.dappstore", "com.solanamobile.dappstore.updater"], "update path of Seed Vault Wallet"),
    "com.trustkernel.android.se": "TEE / secure element overlay",
    "com.android.rkpdapp": "remote key provisioning for KeyMint attestation",
    "com.google.android.configupdater": "certificate pin / config updates",
    "com.android.se": "secure element service (eSE, NFC payments)",
    "com.android.nfc": "NFC", "com.android.bluetooth": "Bluetooth",
    "com.google.android.euicc": "eSIM manager",
    "com.google.android.captiveportallogin": "hotel/station Wi-Fi login",
    "com.mediatek.ims": "VoLTE / VoWiFi calls", "com.mediatek.telephony": "telephony",
    "com.google.android.cellbroadcastreceiver": "emergency alerts", "com.google.android.cellbroadcastservice": "emergency alerts",
    "com.android.cellbroadcastreceiver": "emergency alerts",
    "com.android.camera": "camera app", "com.dualcam.calibration": "camera calibration data, unknown use",
    "com.google.mainline.telemetry": "reports mainline module versions for security updates",
    "com.google.android.webview": "WebView, used by many apps",
}
B = {  # G2 candidates: Google core and the apps that replace it (consequence -> replacement)
    "com.google.android.gms": "Play Services: OTA updates, wallet QR scan, push, location, Google Wallet",
    "com.google.android.gsf": "Google Services Framework (with GMS)",
    "com.android.vending": "Play Store -> F-Droid / Obtainium",
    "com.google.android.partnersetup": "Google account helper",
    "com.google.android.apps.adm": "Find My Device (anti-theft)",
    "com.google.android.inputmethod.latin": "Gboard -> HeliBoard (install first or no keyboard)",
    "com.google.android.dialer": "Phone -> Fossify Phone", "com.google.android.apps.messaging": "SMS -> Fossify Messages",
    "com.google.android.contacts": "Contacts -> Fossify Contacts (export first)",
    "com.google.android.deskclock": "Clock -> Fossify Clock", "com.google.android.calculator": "-> Fossify Calculator",
    "com.google.android.calendar": "-> Fossify Calendar", "com.google.android.apps.photos": "Photos -> Fossify Gallery",
    "com.google.android.apps.maps": "-> Organic Maps / CoMaps", "com.google.android.gm": "Gmail -> K-9/Thunderbird",
    "com.google.android.apps.nbu.files": "Files -> Material Files", "com.android.chrome": "Chrome -> Fennec F-Droid",
    "com.google.android.googlequicksearchbox": "Google app / search bar", "com.google.android.apps.wellbeing": "Digital Wellbeing",
    "com.google.android.tts": "text-to-speech", "com.google.android.marvin.talkback": "TalkBack (accessibility)",
    "com.google.android.projection.gearhead": "Android Auto", "com.google.android.safetycore": "SafetyCore (message scanning)",
    "com.google.android.contactkeys": "contact key verifier", "com.google.android.apps.walletnfcrel": "Google Wallet (NFC pay)",
    "com.google.android.setupwizard": "setup wizard (only after reset)",
    "com.android.launcher3": "home screen -> SEEKER ZERO launcher (Launcher3 stays as fallback)",
}
G3 = {  # remaining C after G1: MediaTek leftovers, proposed, low value
    "com.mediatek.location.mtkgeofence": "MTK geofence", "com.mediatek.carrierexpress": "carrier switch helper",
    "com.mediatek.entitlement.fcm": "FCM entitlement push", "com.android.DeviceAsWebcam": "phone as webcam",
    "com.android.musicfx": "equalizer", "com.android.soundrecorder": "recorder", "com.google.android.apps.turbo": "Device Health (battery estimates)",
    "com.google.android.apps.safetyhub": "already disabled", "com.google.android.gms.supervision": "already disabled",
}

out = []
for r in rows:
    p, uad = r["pkg"], r["uad_removal"]
    if p in g1: c, g, why = "C", "G1 (done)", "unused, see groups/G1.txt"
    elif p in A: c, g, why = "A", "keep", A[p]
    elif p in B: c, g, why = "B", "G2 (approval)", B[p]
    elif p in G3: c, g, why = "C", "G3 (proposed)", G3[p]
    elif uad == "Unsafe" or r["partition"] == "apex" or p == "android" or ".overlay" in p or "Overlay" in p or p.startswith("com.android.internal."):
        c, g, why = "D", "never", f"UAD {uad}, {r['partition']} (core, module or resource overlay)"
    elif p.startswith("com.mediatek.op"): c, g, why = "A", "keep", "inactive carrier plugin (US/India SIMs), inert in Portugal"
    elif uad == "unknown": c, g, why = "A", "keep", "unknown to UAD-NG: kept until identified"
    elif uad == "Recommended": c, g, why = "C", "G3 (proposed)", r["uad_desc"][:120]
    else: c, g, why = "A", "keep", f"UAD {uad}: system function, kept"
    out.append({"class": c, "group": g, "pkg": p, "partition": r["partition"], "uad": uad, "reason": why})

out.sort(key=lambda x: (x["class"], x["group"], x["pkg"]))
with open(root / "classification.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=out[0].keys()); w.writeheader(); w.writerows(out)
from collections import Counter
print(Counter(x["class"] for x in out), Counter(x["group"] for x in out))
assert not [x for x in out if x["class"] != "A" and x["pkg"].startswith("com.solanamobile")], "Solana packages must stay in A"
