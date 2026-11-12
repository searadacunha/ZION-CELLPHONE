#!/bin/bash
# Build the ZION launcher without Gradle: aapt2 + javac + d8 + zipalign + apksigner (debug key).
# Output: launcher/build/seeker-zero-launcher.apk
set -euo pipefail
cd "$(dirname "$0")"
SDK=${ANDROID_SDK_ROOT:-/opt/homebrew/share/android-commandlinetools}
BT=${BUILD_TOOLS:-$SDK/build-tools/37.0.0}
JAR=$SDK/platforms/android-35/android.jar
export PATH=/opt/homebrew/opt/openjdk@17/bin:$PATH
rm -rf build && mkdir -p build/classes build/dex
"$BT/aapt2" link -o build/base.apk --manifest AndroidManifest.xml -I "$JAR"
javac -Xlint:-options --release 11 -cp "$JAR" -d build/classes $(find src -name '*.java')
"$BT/d8" --min-api 31 --lib "$JAR" --output build/dex $(find build/classes -name '*.class')
(cd build/dex && zip -q ../base.apk classes.dex)
"$BT/zipalign" -f -p 4 build/base.apk build/aligned.apk
"$BT/apksigner" sign --ks ~/.android/debug.keystore --ks-pass pass:android --key-pass pass:android \
  --out build/seeker-zero-launcher.apk build/aligned.apk
"$BT/apksigner" verify build/seeker-zero-launcher.apk && echo "OK build/seeker-zero-launcher.apk"
