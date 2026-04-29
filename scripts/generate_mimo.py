#!/usr/bin/env python3
"""Generate audio with Xiaomi MiMo for voice-router."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def load_local_mimo_impl():
    local_impl = Path(__file__).resolve().parents[2] / "noizai-skills" / "skills" / "tts" / "scripts" / "mimo_tts.py"
    spec = importlib.util.spec_from_file_location("local_mimo_tts", local_impl)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load MiMo helper: {local_impl}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate audio with Xiaomi MiMo")
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice", default="茉莉")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="mimo-v2.5-tts")
    parser.add_argument("--context", default="温柔、自然、语速略快")
    parser.add_argument("--format", choices=["wav", "mp3"], default="wav")
    parser.add_argument("--timeout-sec", type=int, default=120)
    args = parser.parse_args()

    text = args.text.strip()
    if not text:
        print(json.dumps({"error": "input text is empty"}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        helper = load_local_mimo_impl()
        result = helper.synthesize_mimo(
            text=text,
            style=args.context,
            voice=args.voice,
            output_path=Path(args.output),
            model=args.model,
            fmt=args.format,
            timeout_sec=args.timeout_sec,
        )
        result["text_length"] = len(text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        message = str(exc)
        try:
            payload = json.loads(message)
        except Exception:
            payload = {
                "provider": "mimo",
                "voice": args.voice,
                "output": str(Path(args.output)),
                "status": "error",
                "error": message,
            }
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
