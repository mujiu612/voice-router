#!/usr/bin/env python3
"""Prepare a Feishu delivery plan for voice-router.

Important boundary:
- This script does NOT send Feishu messages by itself.
- Actual delivery must be performed by OpenClaw runtime/tooling.
- This script validates the audio artifact and emits a structured delivery plan.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError("ffprobe failed to read duration")
    return float(proc.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Feishu delivery plan")
    parser.add_argument("--input", required=True, help="Final audio artifact to send")
    parser.add_argument("--target-mode", default="current_channel", choices=["current_channel"])
    parser.add_argument("--filename-prefix", default="feishu-voice")
    args = parser.parse_args()

    path = Path(args.input)
    try:
        if not path.exists():
            raise RuntimeError(f"input not found: {path}")
        if not path.is_file():
            raise RuntimeError(f"input is not a file: {path}")
        if path.stat().st_size <= 0:
            raise RuntimeError(f"input is empty: {path}")
        duration = probe_duration(path)
        result = {
            "status": "ok",
            "channel": "feishu",
            "target_mode": args.target_mode,
            "path": str(path),
            "filename": path.name,
            "filename_prefix": args.filename_prefix,
            "duration_sec": duration,
            "send_via": "openclaw_message_tool",
            "send_mode": "audio_file",
            "note": "Use OpenClaw message/media delivery in the runtime layer; do not replace with curl or ad-hoc HTTP sends.",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "channel": "feishu",
            "path": str(path),
            "error": str(exc),
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
