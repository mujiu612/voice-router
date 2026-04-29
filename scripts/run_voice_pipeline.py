#!/usr/bin/env python3
"""Minimal first-phase pipeline runner for voice-router.

This script orchestrates:
- route resolution
- provider generation (NoizAI / MiniMax)
- model fallback inside a slot
- opus transcode
- Feishu delivery-plan preparation

It intentionally stops before actual Feishu send. Runtime delivery should be
performed by OpenClaw after inspecting the emitted JSON plan.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DEFAULT_CONFIG = ROOT / "voice_router.json"


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip() or "command failed"
        raise RuntimeError(stderr)
    try:
        return json.loads(proc.stdout)
    except Exception as exc:
        raise RuntimeError(f"invalid JSON output from {' '.join(cmd)}: {exc}\n{proc.stdout}")


def load_config(config_path: Path) -> dict[str, Any]:
    return json.loads(config_path.read_text(encoding="utf-8"))


def build_attempt(model_id: str, model_cfg: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "enabled": model_cfg.get("enabled", True),
        "provider": model_cfg["provider"],
        "provider_model": model_cfg.get("model"),
        "voice": model_cfg.get("voice"),
        "context": model_cfg.get("context"),
        "reference_mode": model_cfg.get("reference_mode"),
        "lang": model_cfg.get("lang"),
        "codec": model_cfg.get("codec"),
        "output_format": model_cfg.get("output_format"),
        "sample_rate": model_cfg.get("sample_rate"),
        "bit_rate": model_cfg.get("bit_rate"),
        "timeout_sec": model_cfg.get("timeout_sec"),
        "retry": model_cfg.get("retry", 1),
        "delivery_profile": route["delivery_profile"],
    }


def generation_command(attempt: dict[str, Any], text: str, raw_path: Path) -> list[str]:
    provider = attempt["provider"]
    voice = attempt.get("voice")
    provider_model = attempt.get("provider_model")
    lang = attempt.get("lang")
    context = attempt.get("context")
    output_format = attempt.get("output_format")

    if provider == "noizai":
        cmd = [
            sys.executable,
            str(SCRIPTS / "generate_noizai.py"),
            "--text", text,
            "--output", str(raw_path),
        ]
        if voice:
            cmd.extend(["--voice", voice])
        if lang:
            cmd.extend(["--lang", lang])
        if attempt.get("timeout_sec"):
            cmd.extend(["--timeout-sec", str(attempt["timeout_sec"])])
        return cmd

    if provider == "minimax":
        cmd = [
            sys.executable,
            str(SCRIPTS / "generate_minimax.py"),
            "--text", text,
            "--voice", voice,
            "--output", str(raw_path),
        ]
        if provider_model:
            cmd.extend(["--model", provider_model])
        if attempt.get("timeout_sec"):
            cmd.extend(["--timeout-sec", str(attempt["timeout_sec"])])
        return cmd

    if provider == "xai":
        cmd = [
            sys.executable,
            str(SCRIPTS / "generate_xai.py"),
            "--text", text,
            "--output", str(raw_path),
        ]
        if voice:
            cmd.extend(["--voice", voice])
        if lang:
            cmd.extend(["--language", lang])
        if attempt.get("codec"):
            cmd.extend(["--format", attempt["codec"]])
        if attempt.get("sample_rate"):
            cmd.extend(["--sample-rate", str(attempt["sample_rate"])])
        if attempt.get("bit_rate"):
            cmd.extend(["--bit-rate", str(attempt["bit_rate"])])
        if attempt.get("timeout_sec"):
            cmd.extend(["--timeout-sec", str(attempt["timeout_sec"])])
        return cmd

    if provider == "mimo":
        cmd = [
            sys.executable,
            str(SCRIPTS / "generate_mimo.py"),
            "--text", text,
            "--output", str(raw_path),
        ]
        if voice:
            cmd.extend(["--voice", voice])
        if provider_model:
            cmd.extend(["--model", provider_model])
        if context:
            cmd.extend(["--context", context])
        if output_format:
            cmd.extend(["--format", output_format])
        if attempt.get("timeout_sec"):
            cmd.extend(["--timeout-sec", str(attempt["timeout_sec"])])
        return cmd

    raise RuntimeError(f"unsupported provider: {provider}")


def try_generation(attempt: dict[str, Any], text: str, prefix: str) -> tuple[dict[str, Any], Path, Path]:
    out_dir = Path(attempt["delivery_profile"]["output_dir"])
    provider = attempt["provider"]
    output_format = (attempt.get("output_format") or attempt.get("codec") or "mp3").lower()
    raw_path = out_dir / f"{prefix}-{provider}.{output_format}"
    opus_path = out_dir / f"{prefix}-{provider}.opus"
    generation = run_json(generation_command(attempt, text=text, raw_path=raw_path))
    return generation, raw_path, opus_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run minimal voice-router pipeline")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--text", required=True)
    parser.add_argument("--task")
    parser.add_argument("--agent")
    parser.add_argument("--channel", default="feishu")
    parser.add_argument("--slot")
    parser.add_argument("--model")
    parser.add_argument("--filename-suffix", help="Optional unique suffix appended to output filename prefix, e.g. chunk-01")
    args = parser.parse_args()

    try:
        config_path = Path(args.config)
        config = load_config(config_path)
        route = run_json([
            sys.executable,
            str(SCRIPTS / "route_voice.py"),
            "--config", str(config_path),
            *( ["--task", args.task] if args.task else [] ),
            *( ["--agent", args.agent] if args.agent else [] ),
            *( ["--channel", args.channel] if args.channel else [] ),
            *( ["--slot", args.slot] if args.slot else [] ),
            *( ["--model", args.model] if args.model else [] ),
        ])

        prefix = route["delivery_profile"]["filename_prefix"]
        if args.filename_suffix:
            safe_suffix = str(args.filename_suffix).strip()
            if safe_suffix:
                prefix = f"{prefix}-{safe_suffix}"
        models_cfg = config["models"]
        attempt_model_ids = [route["chosen_model"], *route.get("fallback_models", [])]

        attempts: list[dict[str, Any]] = []
        selected_attempt = None
        generation = None
        raw_path = None
        opus_path = None

        for model_id in attempt_model_ids:
            model_cfg = models_cfg[model_id]
            attempt = build_attempt(model_id=model_id, model_cfg=model_cfg, route=route)

            if not attempt["enabled"]:
                attempt["status"] = "skipped"
                attempt["error"] = f"model is disabled: {model_id}"
                attempts.append(attempt)
                continue

            max_attempts = max(1, int(attempt.get("retry") or 1))
            last_error = None
            for retry_index in range(max_attempts):
                try:
                    generation, raw_path, opus_path = try_generation(attempt, text=args.text, prefix=prefix)
                    attempt["status"] = "ok"
                    attempt["generation"] = generation
                    attempt["retry_attempts_used"] = retry_index + 1
                    attempts.append(attempt)
                    selected_attempt = attempt
                    break
                except Exception as exc:
                    last_error = str(exc)
            if selected_attempt:
                break
            attempt["status"] = "error"
            attempt["error"] = last_error or "unknown generation error"
            attempt["retry_attempts_used"] = max_attempts
            attempts.append(attempt)

        if not selected_attempt or not generation or not raw_path or not opus_path:
            raise RuntimeError(json.dumps({"message": "all model attempts failed", "attempts": attempts}, ensure_ascii=False))

        transcode = run_json([
            str(SCRIPTS / "transcode_to_opus.sh"),
            str(raw_path),
            str(opus_path),
        ])
        delivery = run_json([
            sys.executable,
            str(SCRIPTS / "deliver_feishu.py"),
            "--input", str(opus_path),
            "--filename-prefix", prefix,
        ])

        result = {
            "status": "ok",
            "route": route,
            "selected_attempt": selected_attempt,
            "attempts": attempts,
            "generation": generation,
            "transcode": transcode,
            "delivery": delivery,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
