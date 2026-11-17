#!/data/data/com.termux/files/usr/bin/bash
# Inside Termux. Builds rtl_433 (it decodes what sensors send on the ISM bands: weather stations, tyre pressure sensors,
# door contacts...) with NO SDR library. Built this way it reads recorded samples (-r file.cu8) and rtl_tcp servers
# (-d rtl_tcp:127.0.0.1:1234): the two inputs a phone without root can use. It receives and decodes, nothing more.
# Then it decodes a published reference capture and compares with the published answer: the proof that the build
# works needs no dongle.
#   bash radio/build-rtl433.sh          build (once) and check
#   bash radio/build-rtl433.sh check    check only
# Sources and sample are downloaded on the phone, never to the Mac, and verified before use.
set -euo pipefail
: "${PREFIX:?run this inside Termux}"
TAG=25.12
SHA256=d283ec7a41a02d398e8918b20b65df3bf684cf4478371830662004005dadcdd2  # sha256 of the source archive of that tag, as GitHub serves it (read from the Mac and from the phone, 13/11/2026)
TESTS=1bd5af52f389f0150bda566437e7d5e17e11fc7f  # commit of merbanan/rtl_433_tests the sample comes from
BLOB=ce74f3ff4d79441481de49ab2d751854eec6d305   # git blob id of tests/nexus/01/gfile001.cu8 at that commit
WANT='{"model": "Nexus-TH", "id": 181, "channel": 2, "temperature_C": 19.0, "humidity": 71}'
W=$HOME/.cache/zion; mkdir -p "$W"

if [ "${1:-}" != check ] && ! command -v rtl_433 >/dev/null; then
  command -v cmake >/dev/null && command -v clang >/dev/null || pkg install -y cmake clang make
  curl -fsSL -o "$W/rtl_433-$TAG.tar.gz" "https://github.com/merbanan/rtl_433/archive/refs/tags/$TAG.tar.gz"
  got=$(sha256sum "$W/rtl_433-$TAG.tar.gz" | cut -d' ' -f1)
  [ "$got" = "$SHA256" ] || { echo "source archive sha256 is $got, expected $SHA256: not built"; exit 1; }
  rm -rf "${W:?}/rtl_433-$TAG"; tar -xzf "$W/rtl_433-$TAG.tar.gz" -C "$W"
  # ENABLE_THREADS=OFF: Android's C library has no pthread_cancel, which the threaded parts call (the build stopped
  # there on the Seeker, 13/11)
  cmake -S "$W/rtl_433-$TAG" -B "$W/rtl_433-$TAG/build" -DENABLE_RTLSDR=OFF -DENABLE_SOAPYSDR=OFF -DENABLE_OPENSSL=OFF \
    -DENABLE_THREADS=OFF -DCMAKE_BUILD_TYPE=Release >"$W/rtl_433-cmake.log" 2>&1 || { tail -20 "$W/rtl_433-cmake.log"; exit 1; }
  cmake --build "$W/rtl_433-$TAG/build" -j 4 >"$W/rtl_433-build.log" 2>&1 || { tail -20 "$W/rtl_433-build.log"; exit 1; }
  install -m 755 "$W/rtl_433-$TAG/build/src/rtl_433" "$PREFIX/bin/rtl_433"
  echo "built and installed: $(rtl_433 -V 2>&1 | head -1)"
fi
command -v rtl_433 >/dev/null || { echo "rtl_433 is not built: run this script without 'check'"; exit 1; }

S=$W/nexus-gfile001.cu8
[ -f "$S" ] || curl -fsSL -o "$S" "https://raw.githubusercontent.com/merbanan/rtl_433_tests/$TESTS/tests/nexus/01/gfile001.cu8"
python3 - "$S" "$BLOB" <<'PY' || { echo "the reference capture is not the published one: not used"; exit 1; }
import hashlib, sys
data = open(sys.argv[1], "rb").read()
sys.exit(0 if hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() == sys.argv[2] else 1)
PY
rtl_433 -r "$S" -F json 2>/dev/null | python3 -c '
import json, sys
want, rows = json.loads(sys.argv[1]), [json.loads(l) for l in sys.stdin if l.startswith("{")]
hit = [r for r in rows if all(r.get(k) == v for k, v in want.items())]
print(f"rtl_433 decoded {len(rows)} message(s) from the reference capture; expected one: {'"'"'FOUND'"'"' if hit else '"'"'NOT FOUND'"'"'}")
print(json.dumps(hit[0] if hit else rows[:2]))
sys.exit(0 if hit else 1)' "$WANT"
