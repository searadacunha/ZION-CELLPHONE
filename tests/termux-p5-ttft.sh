#!/data/data/com.termux/files/usr/bin/bash
# Inside Termux: OPERATOR's real first answer after a cold start, without then with the saved prefix (seeker-ai v4).
exec > /sdcard/Download/seeker-zero/p5-ttft.log 2>&1
P=~/.local/share/seeker-ai/perf.jsonl
rm -f ~/.cache/seeker-ai/slots/prefix-*.bin
for run in "no-copy" "with-copy"; do
  seeker-ai --stop >/dev/null
  t0=$(date +%s%N)
  seeker-ai "Réponds juste OK." </dev/null
  echo; echo "== $run: whole command $(( ($(date +%s%N) - t0) / 1000000 )) ms"
  tail -1 "$P"
  ls -la ~/.cache/seeker-ai/slots/
done
echo "== warm (server already up, prefix in place)"
t0=$(date +%s%N); seeker-ai "Réponds juste NON." </dev/null; echo; echo "whole command $(( ($(date +%s%N) - t0) / 1000000 )) ms"; tail -1 "$P"
echo "== done $(date +%T)"
