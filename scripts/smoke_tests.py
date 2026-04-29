#!/usr/bin/env python3
"""Minimal smoke tests for voice-router.

These tests intentionally cover the most drift-prone invariants first.
They do not call external providers or send messages.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CONFIG = ROOT / "voice_router.json"


class TestFailure(Exception):
    pass



def run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr



def run_json(cmd: list[str], expect_success: bool = True) -> dict:
    code, out, err = run(cmd)
    raw = out if code == 0 else err
    raw = raw.strip()
    if expect_success and code != 0:
        raise TestFailure(f"command failed: {' '.join(cmd)}\n{raw}")
    if not expect_success and code == 0:
        raise TestFailure(f"command unexpectedly succeeded: {' '.join(cmd)}\n{out}")
    try:
        return json.loads(raw)
    except Exception as exc:
        raise TestFailure(f"invalid JSON from {' '.join(cmd)}: {exc}\n{raw}")



def assert_eq(actual, expected, message: str) -> None:
    if actual != expected:
        raise TestFailure(f"{message}: expected={expected!r}, actual={actual!r}")



def test_validate_config_ok() -> None:
    result = run_json([
        sys.executable,
        str(SCRIPTS / "validate_config.py"),
        "--config",
        str(CONFIG),
    ])
    assert_eq(result["status"], "ok", "validate_config status")
    assert_eq(result["error_count"], 0, "validate_config error_count")



def test_task_binding_beats_agent_binding() -> None:
    result = run_json([
        sys.executable,
        str(SCRIPTS / "route_voice.py"),
        "--config", str(CONFIG),
        "--task", "daily_news",
        "--agent", "main",
        "--channel", "feishu",
    ])
    assert_eq(result["source"], "task_binding", "task binding should beat agent binding")
    assert_eq(result["chosen_slot"], "slot_mimo_tts_2_5", "daily_news should route to its task-bound slot")



def test_agent_binding_used_when_no_task_binding() -> None:
    result = run_json([
        sys.executable,
        str(SCRIPTS / "route_voice.py"),
        "--config", str(CONFIG),
        "--agent", "main",
        "--channel", "feishu",
    ])
    assert_eq(result["source"], "agent_binding", "agent binding should be used when no task binding exists")
    assert_eq(result["chosen_slot"], "slot_main", "main should route to slot_main")



def test_default_task_used_as_last_fallback() -> None:
    result = run_json([
        sys.executable,
        str(SCRIPTS / "route_voice.py"),
        "--config", str(CONFIG),
        "--channel", "feishu",
    ])
    assert_eq(result["source"], "task_default", "task_default should be used as final fallback")
    assert_eq(result["chosen_slot"], "slot_main", "default task should route to slot_main")



def test_disabled_slot_rejected() -> None:
    temp = ROOT / "tmp" / "smoke-disabled-slot.json"
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    data["slots"]["slot_main"]["enabled"] = False
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        result = run_json([
            sys.executable,
            str(SCRIPTS / "route_voice.py"),
            "--config", str(temp),
            "--agent", "main",
            "--channel", "feishu",
        ], expect_success=False)
        if "slot is disabled" not in result.get("error", ""):
            raise TestFailure(f"expected disabled slot error, got: {result}")
    finally:
        temp.unlink(missing_ok=True)



def test_validator_warns_on_disabled_primary_model() -> None:
    temp = ROOT / "tmp" / "smoke-disabled-primary-model.json"
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    primary = data["slots"]["slot_main"]["primary_model"]
    data["models"][primary]["enabled"] = False
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        result = run_json([
            sys.executable,
            str(SCRIPTS / "validate_config.py"),
            "--config", str(temp),
        ])
        warnings = result.get("issues", [])
        if not any(i.get("level") == "warning" and "references disabled model" in i.get("message", "") for i in warnings):
            raise TestFailure(f"expected warning about disabled primary model, got: {warnings}")
    finally:
        temp.unlink(missing_ok=True)



def test_transcode_empty_input_fails_structured() -> None:
    temp_in = ROOT / "tmp" / "smoke-empty.mp3"
    temp_out = ROOT / "tmp" / "smoke-empty.opus"
    temp_in.parent.mkdir(parents=True, exist_ok=True)
    temp_in.write_bytes(b"")
    try:
        result = run_json([
            str(SCRIPTS / "transcode_to_opus.sh"),
            str(temp_in),
            str(temp_out),
        ], expect_success=False)
        if result.get("error") != "input is empty":
            raise TestFailure(f"expected input is empty error, got: {result}")
    finally:
        temp_in.unlink(missing_ok=True)
        temp_out.unlink(missing_ok=True)



def main() -> int:
    tests = [
        test_validate_config_ok,
        test_task_binding_beats_agent_binding,
        test_agent_binding_used_when_no_task_binding,
        test_default_task_used_as_last_fallback,
        test_disabled_slot_rejected,
        test_validator_warns_on_disabled_primary_model,
        test_transcode_empty_input_fails_structured,
    ]

    results = []
    failed = 0
    for test in tests:
        name = test.__name__
        try:
            test()
            results.append({"test": name, "status": "ok"})
        except Exception as exc:
            failed += 1
            results.append({"test": name, "status": "error", "error": str(exc)})

    summary = {
        "status": "ok" if failed == 0 else "error",
        "total": len(tests),
        "passed": len(tests) - failed,
        "failed": failed,
        "results": results,
    }

    output = json.dumps(summary, ensure_ascii=False, indent=2)
    if failed == 0:
        print(output)
        return 0
    print(output, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
