#!/data/data/com.termux/files/usr/bin/bash
# Inside Termux: does a Linux userland run on this phone (Termux from Google Play, proot-distro)? Alpine then Debian.
exec > /sdcard/Download/seeker-zero/p2-linux.log 2>&1
seeker-ai --stop   # free the model's 3.5 GB first
echo "== $(date +%T) proot-distro"; proot-distro --help 2>&1 | head -25
for d in alpine debian; do
  echo; echo "== $(date +%T) install $d"; t0=$(date +%s)
  proot-distro install "$d" 2>&1 | tail -6; echo "install $d: $(( $(date +%s) - t0 )) s, exit ${PIPESTATUS[0]}"
  echo "== $d login"; proot-distro login "$d" -- /bin/sh -c 'uname -m; head -2 /etc/os-release; id -u; echo ok-login' 2>&1 | tail -6
done
echo; echo "== $(date +%T) debian: apt python3 git"; t0=$(date +%s)
proot-distro login debian -- /bin/sh -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update -qq && apt-get install -y -qq python3 git >/dev/null && python3 -c "import sys,platform; print(sys.version.split()[0], platform.machine())" && git --version' 2>&1 | tail -5
echo "apt python3+git: $(( $(date +%s) - t0 )) s"
echo "== startup cost: python3 -c pass, native vs debian"
t0=$(date +%s%N); for i in 1 2 3 4 5; do python3 -c pass; done; echo "native  $(( ($(date +%s%N) - t0) / 5000000 )) ms"
t0=$(date +%s%N); for i in 1 2 3 4 5; do proot-distro login debian -- python3 -c pass; done; echo "debian  $(( ($(date +%s%N) - t0) / 5000000 )) ms (includes proot start)"
echo "== disk"; du -sh "$PREFIX/var/lib/proot-distro/installed-rootfs/"* 2>&1
echo "== done $(date +%T)"
