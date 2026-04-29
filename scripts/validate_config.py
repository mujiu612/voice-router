#!/usr/bin/env python3
"""Validate voice_router.json for structural consistency.

This is a pragmatic validator for the current v1 config, not a full JSON Schema.
It checks the invariants that are easiest to drift in day-to-day edits.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "voice_router.json"


class ValidationIssue:
    def __init__(self, level: str, path: str, message: str):
        self.level = level
        self.path = path
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "path": self.path,
            "message": self.message,
        }


REQUIRED_TOP_LEVEL_KEYS = [
    "version",
    "meta",
    "models",
    "slots",
    "bindings",
    "routing",
    "delivery",
    "guidance",
    "intent_examples",
    "evolution",
    "validation",
]

REQUIRED_MODEL_KEYS = ["enabled", "provider"]
REQUIRED_SLOT_KEYS = ["enabled", "display_name", "primary_model"]
REQUIRED_DELIVERY_PROFILE_KEYS = ["enabled", "preferred_format", "send_mode", "output_dir", "filename_prefix"]
VALID_SELECTION_STEPS = {"explicit_slot", "explicit_model", "task_binding", "agent_binding", "task_default"}


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def add(issues: list[ValidationIssue], level: str, path: str, message: str) -> None:
    issues.append(ValidationIssue(level=level, path=path, message=message))



def validate_top_level(config: dict[str, Any], issues: list[ValidationIssue]) -> None:
    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in config:
            add(issues, "error", key, f"missing top-level key: {key}")



def validate_models(config: dict[str, Any], issues: list[ValidationIssue]) -> None:
    models = config.get("models", {})
    if not isinstance(models, dict) or not models:
        add(issues, "error", "models", "models must be a non-empty object")
        return

    for model_id, model_cfg in models.items():
        path = f"models.{model_id}"
        if not isinstance(model_cfg, dict):
            add(issues, "error", path, "model config must be an object")
            continue
        for key in REQUIRED_MODEL_KEYS:
            if key not in model_cfg:
                add(issues, "error", path, f"missing required key: {key}")
        retry = model_cfg.get("retry")
        if retry is not None and (not isinstance(retry, int) or retry < 1):
            add(issues, "error", f"{path}.retry", "retry must be an integer >= 1")
        timeout_sec = model_cfg.get("timeout_sec")
        if timeout_sec is not None and (not isinstance(timeout_sec, (int, float)) or timeout_sec <= 0):
            add(issues, "error", f"{path}.timeout_sec", "timeout_sec must be > 0")



def validate_slots(config: dict[str, Any], issues: list[ValidationIssue]) -> None:
    models = config.get("models", {})
    slots = config.get("slots", {})
    if not isinstance(slots, dict) or not slots:
        add(issues, "error", "slots", "slots must be a non-empty object")
        return

    for slot_id, slot_cfg in slots.items():
        path = f"slots.{slot_id}"
        if not isinstance(slot_cfg, dict):
            add(issues, "error", path, "slot config must be an object")
            continue
        for key in REQUIRED_SLOT_KEYS:
            if key not in slot_cfg:
                add(issues, "error", path, f"missing required key: {key}")
        primary_model = slot_cfg.get("primary_model")
        if primary_model and primary_model not in models:
            add(issues, "error", f"{path}.primary_model", f"references unknown model: {primary_model}")
        elif primary_model and not models.get(primary_model, {}).get("enabled", True):
            add(issues, "warning", f"{path}.primary_model", f"references disabled model: {primary_model}")

        fallback_models = slot_cfg.get("fallback_models", [])
        if fallback_models is not None and not isinstance(fallback_models, list):
            add(issues, "error", f"{path}.fallback_models", "fallback_models must be a list")
            continue
        for idx, model_id in enumerate(fallback_models):
            if model_id not in models:
                add(issues, "error", f"{path}.fallback_models[{idx}]", f"references unknown model: {model_id}")



def validate_bindings(config: dict[str, Any], issues: list[ValidationIssue]) -> None:
    slots = config.get("slots", {})
    bindings = config.get("bindings", {})
    task_bindings = bindings.get("task_bindings", {})
    agent_bindings = bindings.get("agent_bindings", {})

    if not isinstance(task_bindings, dict):
        add(issues, "error", "bindings.task_bindings", "task_bindings must be an object")
    else:
        for task, slot_id in task_bindings.items():
            if slot_id not in slots:
                add(issues, "error", f"bindings.task_bindings.{task}", f"references unknown slot: {slot_id}")
            elif not slots.get(slot_id, {}).get("enabled", True):
                add(issues, "warning", f"bindings.task_bindings.{task}", f"references disabled slot: {slot_id}")

    if not isinstance(agent_bindings, dict):
        add(issues, "error", "bindings.agent_bindings", "agent_bindings must be an object")
    else:
        for agent, slot_id in agent_bindings.items():
            if slot_id not in slots:
                add(issues, "error", f"bindings.agent_bindings.{agent}", f"references unknown slot: {slot_id}")
            elif not slots.get(slot_id, {}).get("enabled", True):
                add(issues, "warning", f"bindings.agent_bindings.{agent}", f"references disabled slot: {slot_id}")



def validate_routing(config: dict[str, Any], issues: list[ValidationIssue]) -> None:
    routing = config.get("routing", {})
    order = routing.get("default_selection_order", [])
    if not isinstance(order, list) or not order:
        add(issues, "error", "routing.default_selection_order", "default_selection_order must be a non-empty list")
        return
    for idx, step in enumerate(order):
        if step not in VALID_SELECTION_STEPS:
            add(issues, "error", f"routing.default_selection_order[{idx}]", f"invalid selection step: {step}")



def validate_delivery(config: dict[str, Any], issues: list[ValidationIssue]) -> None:
    delivery = config.get("delivery", {})
    profiles = delivery.get("profiles", {})
    fallback_channel = delivery.get("fallback_channel")

    if not isinstance(profiles, dict) or not profiles:
        add(issues, "error", "delivery.profiles", "delivery.profiles must be a non-empty object")
        return

    if fallback_channel and fallback_channel not in profiles:
        add(issues, "error", "delivery.fallback_channel", f"references unknown profile: {fallback_channel}")

    for channel, profile in profiles.items():
        path = f"delivery.profiles.{channel}"
        if not isinstance(profile, dict):
            add(issues, "error", path, "delivery profile must be an object")
            continue
        for key in REQUIRED_DELIVERY_PROFILE_KEYS:
            if key not in profile:
                add(issues, "error", path, f"missing required key: {key}")
        output_dir = profile.get("output_dir")
        if output_dir and not isinstance(output_dir, str):
            add(issues, "error", f"{path}.output_dir", "output_dir must be a string path")



def validate_feishu_consistency(config: dict[str, Any], issues: list[ValidationIssue]) -> None:
    routing = config.get("routing", {})
    profiles = config.get("delivery", {}).get("profiles", {})
    feishu = profiles.get("feishu")
    if not feishu:
        return

    if feishu.get("preferred_format") != "opus":
        add(issues, "warning", "delivery.profiles.feishu.preferred_format", "recommended value is 'opus' for stable Feishu delivery")
    if feishu.get("send_mode") != "audio_file":
        add(issues, "warning", "delivery.profiles.feishu.send_mode", "recommended value is 'audio_file' for current stable chain")

    global_mp3 = routing.get("allow_direct_mp3_send")
    profile_mp3 = feishu.get("allow_direct_mp3_send")
    if global_mp3 is False and profile_mp3 is not False:
        add(issues, "warning", "delivery.profiles.feishu.allow_direct_mp3_send", "recommended to explicitly set false when global routing forbids direct mp3 send")



def summarize(issues: list[ValidationIssue]) -> dict[str, Any]:
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    return {
        "status": "ok" if not errors else "error",
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": [i.to_dict() for i in issues],
    }



def main() -> int:
    parser = argparse.ArgumentParser(description="Validate voice_router.json")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()

    config_path = Path(args.config)
    try:
        config = load_config(config_path)
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error_count": 1,
            "warning_count": 0,
            "issues": [{
                "level": "error",
                "path": str(config_path),
                "message": f"failed to load config: {exc}",
            }],
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    issues: list[ValidationIssue] = []
    validate_top_level(config, issues)
    validate_models(config, issues)
    validate_slots(config, issues)
    validate_bindings(config, issues)
    validate_routing(config, issues)
    validate_delivery(config, issues)
    validate_feishu_consistency(config, issues)

    result = summarize(issues)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if result["status"] == "ok":
        print(output)
        return 0
    print(output, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
