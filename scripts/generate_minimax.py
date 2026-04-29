#!/usr/bin/env python3
"""Generate audio with MiniMax for voice-router.

This wrapper intentionally uses MiniMax's synchronous HTTP TTS path directly,
so voice-router does not depend on the broader MiniMax skill runtime or optional
websocket packages.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests


MINIMAX_API_BASE = os.getenv("MINIMAX_API_BASE", "https://api.minimaxi.com/v1")
VALID_FORMATS = {"mp3", "wav", "flac", "pcm"}
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
    api_key = os.getenv("MINIMAX_API_KEY", "").strip() or load_env_value("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY is not set in env or ~/.openclaw/.env")
    return api_key


def make_payload(text: str, voice: str, model: str, fmt: str, emotion: str | None, speed: float, volume: float, pitch: int, sample_rate: int) -> dict:
    payload = {
        "model": model,
        "text": text,
        "voice_setting": {
            "voice_id": voice,
            "speed": speed,
            "vol": volume,
            "pitch": pitch,
        },
        "audio_setting": {
            "sample_rate": sample_rate,
            "bitrate": 128000,
            "format": fmt,
            "channel": 1,
        },
        "stream": False,
        "subtitle_enable": False,
        "output_format": "hex",
        "aigc_watermark": False,
    }
    if emotion:
        payload["voice_setting"]["emotion"] = emotion
    return payload


def save_audio_from_hex(hex_data: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bytes.fromhex(hex_data))


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
    parser = argparse.ArgumentParser(description="Generate audio with MiniMax")
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--format", choices=sorted(VALID_FORMATS), default="mp3")
    parser.add_argument("--model", default="speech-2.8-hd")
    parser.add_argument("--emotion")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--volume", type=float, default=1.0)
    parser.add_argument("--pitch", type=int, default=0)
    parser.add_argument("--sample-rate", type=int, default=32000)
    parser.add_argument("--timeout-sec", type=int, default=120)
    args = parser.parse_args()

    text = args.text.strip()
    if not text:
        print(json.dumps({"error": "input text is empty"}, ensure_ascii=False), file=sys.stderr)
        return 2

    output = Path(args.output)

    try:
        api_key = get_api_key()
        payload = make_payload(
            text=text,
            voice=args.voice,
            model=args.model,
            fmt=args.format,
            emotion=args.emotion,
            speed=args.speed,
            volume=args.volume,
            pitch=args.pitch,
            sample_rate=args.sample_rate,
        )
        resp = requests.post(
            f"{MINIMAX_API_BASE.rstrip('/')}/t2a_v2",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
            json=payload,
            timeout=args.timeout_sec,
        )
        resp.raise_for_status()
        data = resp.json()
        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            raise RuntimeError(f"API Error [{base_resp.get('status_code')}]: {base_resp.get('status_msg', 'Unknown error')}")
        audio_hex = data.get("data", {}).get("audio") or data.get("extra_info", {}).get("audio")
        if not audio_hex:
            raise RuntimeError("No audio data returned from API")
        save_audio_from_hex(audio_hex, output)
        size = probe_file(output)
        result = {
            "provider": "minimax",
            "voice": args.voice,
            "model": args.model,
            "text_length": len(text),
            "output": str(output),
            "format": args.format,
            "size_bytes": size,
            "status": "ok",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "provider": "minimax",
            "voice": args.voice,
            "output": str(output),
            "status": "error",
            "error": str(exc),
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
