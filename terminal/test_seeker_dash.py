#!/usr/bin/env python3
"""Parser tests for seeker-dash (fixtures copied from the real Seeker on 11/11/2026). Run: python3 terminal/test_seeker_dash.py"""
import importlib.machinery, importlib.util, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader("dash", str(HERE / "seeker-dash"))
d = importlib.util.module_from_spec(importlib.util.spec_from_loader("dash", loader))
loader.exec_module(d)

m = d.parse_meminfo("MemTotal:        7657788 kB\nMemFree: 702656 kB\nMemAvailable:    3145728 kB\nSwapTotal: 7657784 kB\nSwapFree: 7247416 kB\n")
assert m == {"MemTotal": 7478, "MemAvailable": 3072, "SwapTotal": 7478, "SwapFree": 7077}, m

t = d.parse_thermal("Cached temperatures:\n\tTemperature{mValue=55.622, mType=0, mName=CPU, mStatus=0}\nHAL Ready: true\n"
                    "Current temperatures from HAL:\n\tTemperature{mValue=51.279, mType=0, mName=CPU, mStatus=0}\n"
                    "\tTemperature{mValue=28.902, mType=3, mName=SKIN, mStatus=0}\n\tTemperature{mValue=35.04, mType=0, mName=CPU, mStatus=0}\n"
                    "Current cooling devices from HAL:\n\tCoolingDevice{mValue=3, mType=2, mName=lcd}")
assert t == {"CPU": 51.279, "SKIN": 28.902}, t

names = d.parse_uid_map("package:com.google.android.gms uid:10113\npackage:com.google.android.gsf uid:10113\npackage:org.fdroid.fdroid uid:10230\n")
assert names[10113] == "com.google.android.gms+1" and names[10230] == "org.fdroid.fdroid"
net = ("  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
       # IPv6 ESTABLISHED to 2a00:1450:400c:c0a::bc port 5228 (0x146C), uid 10113
       "   0: 0000000000000000FFFF00002601A8C0:88B6 5014002A0A0C0C4000000000BC000000:146C 01 00000000:00000000 00:00000000 00000000 10113 0 1 1\n"
       # IPv4 ESTABLISHED to 142.250.184.4:443, uid 10230
       "   1: 2601A8C0:C350 04B8FA8E:01BB 01 00000000:00000000 00:00000000 00000000 10230 0 2 1\n"
       # LISTEN, ignored
       "   2: 2601A8C0:C9EC 00000000:0000 0A 00000000:00000000 00:00000000 00000000 10113 0 3 1\n")
c = d.parse_proc_net(net, names)
assert c == {("com.google.android.gms+1", "2a00:1450:400c:c0a::bc", 5228): 1, ("org.fdroid.fdroid", "142.250.184.4", 443): 1}, c

dump = ("Packages:\n  Package [com.android.phone] (1):\n    userId=1001\n    runtime permissions:\n      android.permission.CAMERA: granted=true\n"
        "\n  Package [com.solanamobile.wallet] (2):\n    userId=10058\n    requested permissions:\n      android.permission.CAMERA\n"
        "    User 0:\n      runtime permissions:\n        android.permission.CAMERA: granted=false, flags=[ USER_SET ]\n"
        "        android.permission.RECORD_AUDIO: granted=true, flags=[ ]\n"
        "\n  Package [org.fossify.gallery] (3):\n    userId=10240\n    runtime permissions:\n      android.permission.READ_MEDIA_IMAGES: granted=true\n")
g = d.parse_granted(dump)
assert g == {"RECORD_AUDIO": ["com.solanamobile.wallet"], "READ_MEDIA_IMAGES": ["org.fossify.gallery"]}, dict(g)

# without Termux/Shizuku (this Mac) the snapshot still renders, with honest "needs Shizuku" panels
out = subprocess.run([sys.executable, str(HERE / "seeker-dash"), "--once"], capture_output=True, text=True, timeout=60)
assert out.returncode == 0 and "needs Shizuku" in out.stdout and "SEEKER ZERO" in out.stdout, out.stdout + out.stderr
assert "AI AGENT STOPPED" in out.stdout and "permissions    read=auto write=auto exec=ask sensitive=ask" in out.stdout, out.stdout
print("seeker-dash self-test: OK")
