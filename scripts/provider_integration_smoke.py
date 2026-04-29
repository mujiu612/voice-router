#!/usr/bin/env python3
"""Provider integration smoke tests for voice-router.

This script runs a lightweight real generation path for selected providers/models,
then probes whether the generated artifact can be transcoded to opus.
It intentionally stops before any delivery/send step.
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
CONFIG = ROOT / "voice_router.json"
TMP = ROOT / "tmp" / "provider-smoke"
DEFAULT_TEXT = "这是一条 provider smoke test。"



def run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr



def run_json(cmd: list[str]) -> tuple[int, dict[str, Any] | None, str]:
    code, out, err = run(cmd)
    raw = out if code == 0 else err
    raw = raw.strip()
    if not raw:
        return code, None, ""
    try:
        return code, json.loads(raw), raw
    except Exception:
        return code, None, raw



def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))



def build_generate_command(model_id: str, model_cfg: dict[str, Any], text: str, output: Path) -> list[str]:
    provider = model_cfg["provider"]
    timeout_sec = str(model_cfg.get("timeout_sec", 60))

    if provider == "noizai":
        cmd = [
            sys.executable,
            str(SCRIPTS / "generate_noizai.py"),
            "--text", text,
            "--output", str(output),
            "--timeout-sec", timeout_sec,
        ]
        if model_cfg.get("voice"):
            cmd.extend(["--voice", str(model_cfg["voice"])])
        if model_cfg.get("lang"):
            cmd.extend(["--lang", str(model_cfg["lang"])])
        return cmd

    if provider == "minimax":
        cmd = [
            sys.executable,
            str(SCRIPTS / "generate_minimax.py"),
            "--text", text,
            "--voice", str(model_cfg.get("voice", "presenter_female")),
            "--output", str(output),
            "--timeout-sec", timeout_sec,
        ]
        if model_cfg.get("model"):
            cmd.extend(["--model", str(model_cfg["model"])])
        return cmd

    if provider == "xai":
        cmd = [
            sys.executable,
            str(SCRIPTS / "generate_xai.py"),
            "--text", text,
            "--output", str(output),
            "--timeout-sec", timeout_sec,
        ]
        if model_cfg.get("voice"):
            cmd.extend(["--voice", str(model_cfg["voice"])])
        if model_cfg.get("lang"):
            cmd.extend(["--language", str(model_cfg["lang"])])
        if model_cfg.get("codec"):
            cmd.extend(["--format", str(model_cfg["codec"])])
        if model_cfg.get("sample_rate"):
            cmd.extend(["--sample-rate", str(model_cfg["sample_rate"])])
        if model_cfg.get("bit_rate"):
            cmd.extend(["--bit-rate", str(model_cfg["bit_rate"])])
        return cmd

    raise RuntimeError(f"unsupported provider for smoke test: {provider}")



def classify_external_provider_failure(raw: str) -> dict[str, Any] | None:
    text = (raw or "").lower()
    if "not support model" in text or "token plan" in text or "plan not support" in text:
        return {
            "category": "external_constraint",
            "reason": "provider plan/model capability does not support requested model",
        }
    return None



def run_one_model(model_id: str, model_cfg: dict[str, Any], text: str) -> dict[str, Any]:
    provider = model_cfg["provider"]
    TMP.mkdir(parents=True, exist_ok=True)
    raw_output = TMP / f"{model_id}.{model_cfg.get('codec', 'mp3')}"
    opus_output = TMP / f"{model_id}.opus"

    result: dict[str, Any] = {
        "model_id": model_id,
        "provider": provider,
        "status": "error",
        "classification": "hard_fail",
        "steps": {},
    }

    generate_cmd = build_generate_command(model_id, model_cfg, text, raw_output)
    code, payload, raw = run_json(generate_cmd)
    result["steps"]["generate"] = {
        "exit_code": code,
        "payload": payload,
        "raw": raw if payload is None else None,
    }
    if code != 0 or not payload or payload.get("status") != "ok":
        result["error"] = "generation failed"
        external = classify_external_provider_failure(raw)
        if external:
            result["classification"] = external["category"]
            result["external_reason"] = external["reason"]
        return result

    transcode_cmd = [str(SCRIPTS / "transcode_to_opus.sh"), str(raw_output), str(opus_output)]
    t_code, t_payload, t_raw = run_json(transcode_cmd)
    result["steps"]["transcode"] = {
        "exit_code": t_code,
        "payload": t_payload,
        "raw": t_raw if t_payload is None else None,
    }
    if t_code != 0 or not t_payload or t_payload.get("status") != "ok":
        result["error"] = "transcode failed"
        return result

    result["status"] = "ok"
    result["classification"] = "pass"
    return result



def main() -> int:
    parser = argparse.ArgumentParser(description="Run provider integration smoke tests")
    parser.add_argument("--config", default=str(CONFIG))
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--providers", nargs="*", help="Optional provider allowlist, e.g. noizai minimax")
    parser.add_argument("--models", nargs="*", help="Optional explicit model ids to test")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    models = config.get("models", {})

    selected: list[tuple[str, dict[str, Any]]] = []
    for model_id, model_cfg in models.items():
        if not model_cfg.get("enabled", True):
            continue
        if args.models and model_id not in args.models:
            continue
        if args.providers and model_cfg.get("provider") not in args.providers:
            continue
        selected.append((model_id, model_cfg))

    if not selected:
        summary = {
            "status": "error",
            "error": "no enabled models matched selection",
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    results = [run_one_model(model_id, model_cfg, args.text) for model_id, model_cfg in selected]
    passed = [r for r in results if r.get("classification") == "pass"]
    external_failed = [r for r in results if r.get("classification") == "external_constraint"]
    hard_failed = [r for r in results if r.get("classification") == "hard_fail"]
    summary = {
        "status": "ok" if not hard_failed else "error",
        "text": args.text,
        "total": len(results),
        "passed": len(passed),
        "external_failed": len(external_failed),
        "hard_failed": len(hard_failed),
        "results": results,
    }

    output = json.dumps(summary, ensure_ascii=False, indent=2)
    if hard_failed:
        print(output, file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
