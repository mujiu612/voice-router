#!/usr/bin/env python3
"""Generate audio with xAI TTS for voice-router.

Uses xAI batch TTS endpoint:
  POST https://api.x.ai/v1/tts

Returns raw audio bytes on success.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests


XAI_API_BASE = os.getenv("XAI_API_BASE", "https://api.x.ai/v1")
VALID_FORMATS = {"mp3", "wav", "pcm", "mulaw", "alaw"}
VALID_SAMPLE_RATES = {8000, 16000, 22050, 24000, 44100, 48000}
VALID_MP3_BITRATES = {32000, 64000, 96000, 128000, 192000}
OPENCLAW_ENV_FILE = Path.home() / ".openclaw" / ".env"


def load_env_value(key: str) -> str:
    if not OPENCLAW_ENV_FILE.exists():
        return ""
    for line in OPENCLAW_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


def get_api_key() -> str:
    api_key = os.getenv("XAI_API_KEY", "").strip() or load_env_value("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set in env or ~/.openclaw/.env")
    return api_key


def make_payload(
    text: str,
    voice_id: str | None,
    language: str,
    codec: str,
    sample_rate: int,
    bit_rate: int | None,
) -> dict:
    payload = {
        "text": text,
        "language": language,
        "output_format": {
            "codec": codec,
            "sample_rate": sample_rate,
        },
    }
    if voice_id:
        payload["voice_id"] = voice_id
    if codec == "mp3" and bit_rate:
        payload["output_format"]["bit_rate"] = bit_rate
    return payload


def save_audio(content: bytes, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)


def probe_file(path: Path) -> int:
    if not path.exists():
        raise RuntimeError(f"output not created: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise RuntimeError(f"output is empty: {path}")
    head = path.read_bytes()[:256].lstrip()
    if head.startswith(b"{") or head.startswith(b"["):
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            raise RuntimeError(f"output is not valid audio: {path}")
        raise RuntimeError(f"output is JSON, not audio: {payload}")
    return size


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate audio with xAI TTS")
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice")
    parser.add_argument("--output", required=True)
    parser.add_argument("--format", choices=sorted(VALID_FORMATS), default="mp3")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--sample-rate", type=int, default=24000)
    parser.add_argument("--bit-rate", type=int, default=128000)
    parser.add_argument("--timeout-sec", type=int, default=120)
    args = parser.parse_args()

    text = args.text.strip()
    if not text:
        print(json.dumps({"error": "input text is empty"}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.sample_rate not in VALID_SAMPLE_RATES:
        print(json.dumps({"error": f"unsupported sample_rate: {args.sample_rate}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.format == "mp3" and args.bit_rate not in VALID_MP3_BITRATES:
        print(json.dumps({"error": f"unsupported mp3 bit_rate: {args.bit_rate}"}, ensure_ascii=False), file=sys.stderr)
        return 2

    output = Path(args.output)

    try:
        api_key = get_api_key()
        payload = make_payload(
            text=text,
            voice_id=args.voice,
            language=args.language,
            codec=args.format,
            sample_rate=args.sample_rate,
            bit_rate=args.bit_rate if args.format == "mp3" else None,
        )
        resp = requests.post(
            f"{XAI_API_BASE.rstrip('/')}/tts",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=args.timeout_sec,
        )
        if not resp.ok:
            content_type = resp.headers.get("Content-Type", "")
            detail = resp.text[:4000] if "text" in content_type or "json" in content_type else f"HTTP {resp.status_code}"
            raise RuntimeError(f"HTTP {resp.status_code}: {detail}")

        save_audio(resp.content, output)
        size = probe_file(output)
        result = {
            "provider": "xai",
            "voice": args.voice or "eve",
            "language": args.language,
            "text_length": len(text),
            "output": str(output),
            "format": args.format,
            "sample_rate": args.sample_rate,
            "bit_rate": args.bit_rate if args.format == "mp3" else None,
            "size_bytes": size,
            "status": "ok",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "provider": "xai",
            "voice": args.voice or "eve",
            "output": str(output),
            "status": "error",
            "error": str(exc),
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
