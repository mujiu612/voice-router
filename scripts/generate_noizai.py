#!/usr/bin/env python3
"""Generate audio with NoizAI for voice-router.

This wrapper reuses the existing NoizAI TTS implementation already present in the
workspace, instead of reinventing the API call flow.

First-phase behavior:
- Accept text/voice/output path
- Load API key from the NOIZ_API_KEY environment variable or ~/.noiz_api_key
- Reuse noiz_tts.py from the installed NoizAI skill
- Return structured JSON for downstream routing/transcode steps
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


DEFAULT_REF_AUDIO_URL_CN = "https://storage.googleapis.com/noiz_audio_public/resource/audio/ref_cn_fm1.WAV"
DEFAULT_REF_AUDIO_URL_EN = "https://noiz.ai/resource/img/tts/landing_creative1.mp3"
NOIZ_KEY_FILE = Path.home() / ".noiz_api_key"
OPENCLAW_ENV_FILE = Path.home() / ".openclaw" / ".env"
SKILL_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = SKILL_ROOT.parent.parent
NOIZ_IMPL_CANDIDATES = [
    WORKSPACE_ROOT / "skills" / "noizai-skills" / "skills" / "tts" / "scripts" / "noiz_tts.py",
    WORKSPACE_ROOT / "skills" / "noizai-skills" / "scripts" / "noiz_tts.py",
]


def resolve_noiz_impl() -> Path:
    for path in NOIZ_IMPL_CANDIDATES:
        if path.exists():
            return path
    return NOIZ_IMPL_CANDIDATES[0]


def normalize_api_key_base64(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    padded = value + ("=" * (-len(value) % 4))
    try:
        decoded = base64.b64decode(padded, validate=True)
        canonical = base64.b64encode(decoded).decode("ascii").rstrip("=")
        if decoded and canonical == value.rstrip("="):
            return value
    except binascii.Error:
        pass
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


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


def load_api_key() -> str:
    env_key = os.environ.get("NOIZ_API_KEY", "").strip() or load_env_value("NOIZ_API_KEY")
    if env_key:
        return normalize_api_key_base64(env_key)
    if NOIZ_KEY_FILE.exists():
        return normalize_api_key_base64(NOIZ_KEY_FILE.read_text(encoding="utf-8").strip())
    raise RuntimeError("NOIZ_API_KEY not configured in env, ~/.openclaw/.env, or ~/.noiz_api_key")


def detect_lang(text: str) -> str:
    for ch in text:
        if "\u3400" <= ch <= "\u9fff":
            return "cmn"
    return "en"


def choose_default_ref_audio(lang: str) -> str:
    return DEFAULT_REF_AUDIO_URL_CN if lang == "cmn" else DEFAULT_REF_AUDIO_URL_EN


def download_ref_audio(url: str) -> Path:
    import urllib.request

    suffix = Path(url).suffix or ".wav"
    fd, temp_path = tempfile.mkstemp(prefix="voice_router_ref_", suffix=suffix)
    os.close(fd)
    path = Path(temp_path)
    urllib.request.urlretrieve(url, path)
    return path


def probe_file(path: Path) -> int:
    if not path.exists():
        raise RuntimeError(f"output not created: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise RuntimeError(f"output is empty: {path}")

    head = path.read_bytes()[:256]
    stripped = head.lstrip()
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            raise RuntimeError(f"output is not valid audio: {path}")
        raise RuntimeError(f"output is JSON, not audio: {payload}")

    return size


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate audio with NoizAI")
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice", help="NoizAI voice id")
    parser.add_argument("--output", required=True)
    parser.add_argument("--format", choices=["wav", "mp3"], default="mp3")
    parser.add_argument("--lang")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--reference-audio", help="Local path or URL")
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    noiz_impl = resolve_noiz_impl()
    if not noiz_impl.exists():
        print(json.dumps({"error": f"NoizAI implementation not found: {noiz_impl}"}, ensure_ascii=False), file=sys.stderr)
        return 2

    text = args.text.strip()
    if not text:
        print(json.dumps({"error": "input text is empty"}, ensure_ascii=False), file=sys.stderr)
        return 2

    api_key = load_api_key()
    lang = args.lang or detect_lang(text)

    temp_ref: Optional[Path] = None
    reference_audio = args.reference_audio
    if not args.voice and not reference_audio:
        reference_audio = choose_default_ref_audio(lang)

    if reference_audio and reference_audio.startswith(("http://", "https://")):
        temp_ref = download_ref_audio(reference_audio)
        reference_audio = str(temp_ref)

    cmd = [
        sys.executable,
        str(noiz_impl),
        "--api-key",
        api_key,
        "--text",
        text,
        "--output",
        str(output),
        "--output-format",
        args.format,
        "--speed",
        str(args.speed),
        "--timeout-sec",
        str(args.timeout_sec),
        "--target-lang",
        lang,
    ]

    if args.voice:
        cmd.extend(["--voice-id", args.voice])
    elif reference_audio:
        cmd.extend(["--reference-audio", reference_audio])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "NoizAI synthesis failed")
        size = probe_file(output)
        result = {
            "provider": "noizai",
            "voice": args.voice,
            "lang": lang,
            "text_length": len(text),
            "output": str(output),
            "format": args.format,
            "size_bytes": size,
            "status": "ok",
            "stdout": proc.stdout.strip(),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "provider": "noizai",
            "output": str(output),
            "status": "error",
            "error": str(exc),
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    finally:
        if temp_ref and temp_ref.exists():
            temp_ref.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
