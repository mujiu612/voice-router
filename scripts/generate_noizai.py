#!/usr/bin/env python3
"""Generate audio with NoizAI for voice-router.

Security-focused behavior:
- Load API key from env / ~/.openclaw/.env / ~/.noiz_api_key
- Call NoizAI directly instead of passing secrets via subprocess CLI args
- Only allow HTTPS reference-audio downloads from a small allowlist
- Enforce timeout, size limit, and basic content-type checks for URL downloads
- Return structured JSON for downstream routing/transcode steps
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests


DEFAULT_REF_AUDIO_URL_CN = "https://storage.googleapis.com/noiz_audio_public/resource/audio/ref_cn_fm1.WAV"
DEFAULT_REF_AUDIO_URL_EN = "https://noiz.ai/resource/img/tts/landing_creative1.mp3"
NOIZ_API_BASE = os.getenv("NOIZ_API_BASE", "https://noiz.ai/v1")
NOIZ_KEY_FILE = Path.home() / ".noiz_api_key"
OPENCLAW_ENV_FILE = Path.home() / ".openclaw" / ".env"
ALLOWED_REFERENCE_AUDIO_HOSTS = {"noiz.ai", "storage.googleapis.com"}
ALLOWED_REFERENCE_AUDIO_EXTS = {".wav", ".mp3", ".opus", ".ogg", ".m4a"}
MAX_REFERENCE_AUDIO_BYTES = 15 * 1024 * 1024


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


def ensure_safe_reference_audio_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise RuntimeError("reference-audio URL must use https")
    hostname = (parsed.hostname or "").lower()
    if hostname not in ALLOWED_REFERENCE_AUDIO_HOSTS:
        raise RuntimeError(
            "reference-audio host is not allowlisted; use a local file or one of: "
            + ", ".join(sorted(ALLOWED_REFERENCE_AUDIO_HOSTS))
        )
    suffix = Path(parsed.path).suffix.lower()
    if suffix and suffix not in ALLOWED_REFERENCE_AUDIO_EXTS:
        raise RuntimeError(
            "reference-audio URL has unsupported extension; allowed: "
            + ", ".join(sorted(ALLOWED_REFERENCE_AUDIO_EXTS))
        )
    return url


def download_ref_audio(url: str, timeout_sec: int) -> Path:
    url = ensure_safe_reference_audio_url(url)
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".wav"
    fd, temp_path = tempfile.mkstemp(prefix="voice_router_ref_", suffix=suffix)
    os.close(fd)
    path = Path(temp_path)

    try:
        with requests.get(url, stream=True, timeout=(5, timeout_sec)) as resp:
            resp.raise_for_status()
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_REFERENCE_AUDIO_BYTES:
                raise RuntimeError("reference-audio download is larger than safety limit")
            content_type = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if content_type and content_type not in {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/ogg", "audio/opus", "audio/mp4", "application/octet-stream"}:
                raise RuntimeError(f"reference-audio content-type not allowed: {content_type}")

            total = 0
            with path.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1024 * 64):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_REFERENCE_AUDIO_BYTES:
                        raise RuntimeError("reference-audio download exceeded safety limit")
                    fh.write(chunk)
        if path.stat().st_size <= 0:
            raise RuntimeError("reference-audio download is empty")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


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


def synthesize_noiz(
    *,
    api_key: str,
    text: str,
    output: Path,
    output_format: str,
    voice: Optional[str],
    reference_audio: Optional[Path],
    lang: str,
    speed: float,
    timeout_sec: int,
) -> float:
    url = f"{NOIZ_API_BASE.rstrip('/')}/text-to-speech"
    data: dict[str, str] = {
        "text": text,
        "output_format": output_format,
        "speed": str(speed),
        "target_lang": lang,
    }
    if voice:
        data["voice_id"] = voice
    elif not reference_audio:
        raise RuntimeError("Either voice or reference-audio is required")

    files = None
    if reference_audio:
        files = {
            "file": (
                reference_audio.name,
                reference_audio.open("rb"),
                "application/octet-stream",
            )
        }

    try:
        resp = requests.post(
            url,
            headers={"Authorization": api_key},
            data=data,
            files=files,
            timeout=timeout_sec,
        )
    finally:
        if files and files["file"][1]:
            files["file"][1].close()

    if resp.status_code != 200:
        raise RuntimeError(f"/text-to-speech failed: status={resp.status_code}, body={resp.text}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(resp.content)
    dur = resp.headers.get("X-Audio-Duration")
    duration_val = float(dur) if dur else -1.0
    output.with_suffix(".duration").write_text(str(duration_val), encoding="utf-8")
    return duration_val


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate audio with NoizAI")
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice", help="NoizAI voice id")
    parser.add_argument("--output", required=True)
    parser.add_argument("--format", choices=["wav", "mp3", "opus", "ogg"], default="mp3")
    parser.add_argument("--lang")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--reference-audio", help="Local path or allowlisted HTTPS URL")
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

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

    local_ref: Optional[Path] = None
    try:
        if reference_audio:
            if reference_audio.startswith(("http://", "https://")):
                temp_ref = download_ref_audio(reference_audio, args.timeout_sec)
                local_ref = temp_ref
            else:
                local_ref = Path(reference_audio).expanduser().resolve()
                if not local_ref.exists():
                    raise RuntimeError(f"reference-audio not found: {local_ref}")
                if local_ref.suffix.lower() not in ALLOWED_REFERENCE_AUDIO_EXTS:
                    raise RuntimeError(
                        "reference-audio file has unsupported extension; allowed: "
                        + ", ".join(sorted(ALLOWED_REFERENCE_AUDIO_EXTS))
                    )

        duration = synthesize_noiz(
            api_key=api_key,
            text=text,
            output=output,
            output_format=("opus" if args.format == "ogg" else args.format),
            voice=args.voice,
            reference_audio=local_ref,
            lang=lang,
            speed=args.speed,
            timeout_sec=args.timeout_sec,
        )
        size = probe_file(output)
        result = {
            "provider": "noizai",
            "voice": args.voice,
            "lang": lang,
            "text_length": len(text),
            "output": str(output),
            "format": ("opus" if args.format == "ogg" else args.format),
            "size_bytes": size,
            "duration_sec": duration,
            "status": "ok",
        }
        if local_ref:
            result["reference_audio_mode"] = "url_download" if temp_ref else "local_file"
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
