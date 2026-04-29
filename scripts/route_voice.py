#!/usr/bin/env python3
"""Resolve voice-router config into a concrete routing plan.

First-phase scope:
- Load voice_router.json
- Resolve explicit slot/model, task binding, agent binding, task default
- Return chosen slot/model/provider/voice/delivery profile
- Do not call TTS providers here
- Do not send messages here
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "voice_router.json"


class RouteError(Exception):
    pass


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_task_binding_slot(config: Dict[str, Any], task: Optional[str]) -> Optional[str]:
    if not task:
        return None
    bindings = config.get("bindings", {})
    task_bindings = bindings.get("task_bindings", {})
    return task_bindings.get(task)



def get_agent_binding_slot(config: Dict[str, Any], agent: Optional[str]) -> Optional[str]:
    if not agent:
        return None
    bindings = config.get("bindings", {})
    agent_bindings = bindings.get("agent_bindings", {})
    return agent_bindings.get(agent)



def get_default_task_slot(config: Dict[str, Any]) -> Optional[str]:
    bindings = config.get("bindings", {})
    task_bindings = bindings.get("task_bindings", {})
    return task_bindings.get("default")


def validate_model_exists(config: Dict[str, Any], model_id: str) -> None:
    models = config.get("models", {})
    if model_id not in models:
        raise RouteError(f"model not found: {model_id}")
    if not models[model_id].get("enabled", True):
        raise RouteError(f"model is disabled: {model_id}")



def validate_slot_exists(config: Dict[str, Any], slot_id: str) -> None:
    slots = config.get("slots", {})
    if slot_id not in slots:
        raise RouteError(f"slot not found: {slot_id}")
    if not slots[slot_id].get("enabled", True):
        raise RouteError(f"slot is disabled: {slot_id}")



def validate_delivery_profile(profile: Optional[Dict[str, Any]], channel: str) -> None:
    if not profile:
        raise RouteError(f"delivery profile not found: {channel}")
    if not profile.get("enabled", True):
        raise RouteError(f"delivery profile is disabled: {channel}")


def resolve_route(
    config: Dict[str, Any],
    explicit_slot: Optional[str] = None,
    explicit_model: Optional[str] = None,
    task: Optional[str] = None,
    agent: Optional[str] = None,
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    routing = config.get("routing", {})
    order = routing.get(
        "default_selection_order",
        ["explicit_slot", "explicit_model", "task_binding", "agent_binding", "task_default"],
    )

    chosen_slot = None
    chosen_model = None
    source = None

    for step in order:
        if step == "explicit_slot" and explicit_slot:
            validate_slot_exists(config, explicit_slot)
            chosen_slot = explicit_slot
            source = "explicit_slot"
            break
        if step == "explicit_model" and explicit_model:
            validate_model_exists(config, explicit_model)
            chosen_model = explicit_model
            source = "explicit_model"
            break
        if step == "task_binding":
            slot = get_task_binding_slot(config, task=task)
            if slot:
                validate_slot_exists(config, slot)
                chosen_slot = slot
                source = step
                break
        if step == "agent_binding":
            slot = get_agent_binding_slot(config, agent=agent)
            if slot:
                validate_slot_exists(config, slot)
                chosen_slot = slot
                source = step
                break
        if step == "task_default":
            slot = get_default_task_slot(config)
            if slot:
                validate_slot_exists(config, slot)
                chosen_slot = slot
                source = step
                break

    if not chosen_slot and not chosen_model:
        raise RouteError("no route matched")

    models = config.get("models", {})
    slots = config.get("slots", {})
    delivery = config.get("delivery", {})
    profiles = delivery.get("profiles", {})
    target_channel = channel or delivery.get("fallback_channel", "feishu")
    profile = profiles.get(target_channel)

    validate_delivery_profile(profile, target_channel)

    fallback_models = []

    if chosen_slot:
        slot_cfg = slots[chosen_slot]
        chosen_model = slot_cfg["primary_model"]
        validate_model_exists(config, chosen_model)
        fallback_models = slot_cfg.get("fallback_models", [])

    model_cfg = models[chosen_model]

    return {
        "source": source,
        "chosen_slot": chosen_slot,
        "chosen_model": chosen_model,
        "fallback_models": fallback_models,
        "provider": model_cfg["provider"],
        "provider_model": model_cfg.get("model"),
        "voice": model_cfg.get("voice"),
        "reference_mode": model_cfg.get("reference_mode"),
        "model_display_name": model_cfg.get("display_name"),
        "delivery_channel": target_channel,
        "delivery_profile": profile,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Resolve voice-router route")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--slot")
    parser.add_argument("--model")
    parser.add_argument("--task")
    parser.add_argument("--agent")
    parser.add_argument("--channel")
    args = parser.parse_args()

    try:
        config = load_config(Path(args.config))
        result = resolve_route(
            config,
            explicit_slot=args.slot,
            explicit_model=args.model,
            task=args.task,
            agent=args.agent,
            channel=args.channel,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except RouteError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
