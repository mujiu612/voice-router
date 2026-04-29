#!/usr/bin/env bash
set -euo pipefail

# Transcode audio to opus and validate the result.
# Usage:
#   transcode_to_opus.sh <input-audio> <output-opus>

if [[ $# -lt 2 ]]; then
  echo "usage: transcode_to_opus.sh <input-audio> <output-opus>" >&2
  exit 2
fi

INPUT="$1"
OUTPUT="$2"

if [[ ! -f "$INPUT" ]]; then
  echo "{\"status\":\"error\",\"error\":\"input not found\",\"input\":\"$INPUT\"}" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"

if [[ ! -s "$INPUT" ]]; then
  echo "{\"status\":\"error\",\"error\":\"input is empty\",\"input\":\"$INPUT\"}" >&2
  exit 1
fi

# Reject obvious JSON/text error payloads masquerading as audio.
python3 - "$INPUT" <<'PY'
from pathlib import Path
import json, sys
p = Path(sys.argv[1])
head = p.read_bytes()[:256].lstrip()
if head.startswith(b'{') or head.startswith(b'['):
    try:
        payload = json.loads(p.read_text(encoding='utf-8', errors='replace'))
    except Exception:
        print('{"status":"error","error":"input is text/json, not audio"}', file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"status":"error","error":"input is JSON, not audio","payload":payload}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(1)
PY

FFMPEG_LOG=$(mktemp -t voice_router_ffmpeg.XXXXXX.log)
cleanup() {
  rm -f "$FFMPEG_LOG"
}
trap cleanup EXIT

ffmpeg -y -i "$INPUT" -c:a libopus -b:a 32k -vbr on -application voip "$OUTPUT" >"$FFMPEG_LOG" 2>&1 || {
  LOG=$(python3 - "$FFMPEG_LOG" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
print(p.read_text(encoding='utf-8', errors='replace')[-4000:])
PY
)
  python3 - "$INPUT" "$OUTPUT" "$LOG" <<'PY' >&2
import json, sys
print(json.dumps({
    "status": "error",
    "error": "ffmpeg transcode failed",
    "input": sys.argv[1],
    "output": sys.argv[2],
    "log": sys.argv[3],
}, ensure_ascii=False))
PY
  exit 1
}

if [[ ! -s "$OUTPUT" ]]; then
  echo "{\"status\":\"error\",\"error\":\"output is empty after transcode\",\"output\":\"$OUTPUT\"}" >&2
  exit 1
fi

DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUTPUT" 2>/dev/null || true)
if [[ -z "$DURATION" ]]; then
  echo "{\"status\":\"error\",\"error\":\"ffprobe failed to read duration\",\"output\":\"$OUTPUT\"}" >&2
  exit 1
fi

SIZE=$(python3 -c "import os; print(os.path.getsize('$OUTPUT'))")
python3 - "$INPUT" "$OUTPUT" "$DURATION" "$SIZE" <<'PY'
import json, sys
print(json.dumps({
    "status": "ok",
    "input": sys.argv[1],
    "output": sys.argv[2],
    "codec": "opus",
    "duration_sec": float(sys.argv[3]),
    "size_bytes": int(sys.argv[4]),
}, ensure_ascii=False, indent=2))
PY
