#!/data/data/com.termux/files/usr/bin/bash
# Inside Termux: download a GGUF from Hugging Face into ~/models and check its sha256 against the Hub's LFS record.
#   install-model.sh                                   -> HauhauCS Qwen3.5-4B Uncensored Q4_K_M (default model of seeker-ai)
#   install-model.sh unsloth/Qwen3.5-4B-GGUF Qwen3.5-4B-Q4_0.gguf     -> fallback (seeker-ai --use Qwen3.5-4B-Q4_0)
set -euo pipefail
REPO=${1:-HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive}
FILE=${2:-Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf}
mkdir -p ~/models && cd ~/models
want=$(curl -sSf --max-time 60 "https://huggingface.co/api/models/$REPO/tree/main" |
  python3 -c 'import json,sys; print(next(x["lfs"]["oid"] for x in json.load(sys.stdin) if x["path"] == sys.argv[1]))' "$FILE")
[ -f "$FILE" ] && [ "$(sha256sum "$FILE" | cut -d' ' -f1)" = "$want" ] && { echo "already there: ~/models/$FILE"; exit 0; }
# a stalled Wi-Fi must not hang an unattended run: give up under 10 kB/s for 2 min (a re-run resumes the .part)
curl -fL -C - --connect-timeout 30 --speed-limit 10000 --speed-time 120 -o "$FILE.part" "https://huggingface.co/$REPO/resolve/main/$FILE"
got=$(sha256sum "$FILE.part" | cut -d' ' -f1)
[ "$got" = "$want" ] || { rm -f "$FILE.part"; echo "sha256 mismatch: $got != $want (bad download deleted)"; exit 1; }
mv "$FILE.part" "$FILE"
echo "OK ~/models/$FILE sha256 $want"
