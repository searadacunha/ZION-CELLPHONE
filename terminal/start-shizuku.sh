#!/bin/bash
# From the Mac, after each reboot of the Seeker: start the Shizuku server (uid 2000 "shell", NOT root) so that Termux's
# `rish`, seeker-ai's system/android tools and seeker-dash get ADB-level rights. It stops by itself at the next reboot.
set -eu
cd "$(dirname "$0")/.." && . ./adb.sh
dir=$(a shell pm path moe.shizuku.privileged.api | head -1 | sed 's/^package://; s#/base.apk$##' | tr -d '\r')
[ -n "$dir" ] || { echo "Shizuku is not installed"; exit 1; }
out=$(a shell "$dir/lib/arm64/libshizuku.so" 2>&1) || { echo "$out" | tail -5; echo "Shizuku did not start"; exit 1; }
echo "$out" | tail -2
