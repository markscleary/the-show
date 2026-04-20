from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml

from models import (
    AdaptiveConfig,
    Bible,
    CutRule,
    RetryPolicy,
    Scene,
    ShowSettings,
    Strategy,
)


class ValidationError(Exception):
    pass


def _strategy_from_dict(data: Dict[str, Any]) -> Strategy:
    return Strategy(
        method=data["method"],
        agent=data["agent"],
        action=data.get("action"),
        brief=data.get("brief"),
        params=data.get("params", {}),
        label=data.get("label"),
        success_when=data.get("success-when", {}),  # per-strategy override
        severity=data.get("severity", "urgent"),
    )


def _retry_policy_from_dict(data: Dict[str, Any]) -> RetryPolicy:
    if not data:
        return RetryPolicy()
    return RetryPolicy(
        max_attempts=data.get("max-attempts", 1),
        backoff=data.get("backoff", "none"),
        base_delay_seconds=data.get("base-delay-seconds", 0.0),
        jitter=data.get("jitter", False),
        retriable_errors=data.get("retriable-errors", []),
    )


def _cut_rule_from_dict(data: Dict[str, Any]) -> CutRule:
    if not data:
        return CutRule()
    return CutRule(
        condition=data.get("condition", "escalate"),
        reason=data.get("reason"),
        minimum_acceptable=data.get("minimum-acceptable"),
    )


def _adaptive_from_dict(data: Dict[str, Any]) -> AdaptiveConfig:
    if not data:
        return AdaptiveConfig()
    return AdaptiveConfig(
        allowed=data.get("allowed", False),
        bounds=data.get("bounds", {}),
    )


def _kebab_to_snake_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Convert top-level dict keys from kebab-case to snake_case."""
    return {k.replace("-", "_"): v for k, v in d.items()}


def load_show(path: str | Path) -> ShowSettings:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if "show" not in raw:
        raise ValidationError("Top-level 'show' key is required.")

    show = raw["show"]
    running = show.get("running-order", [])
    scenes: List[Scene] = []

    for item in running:
        principal = _strategy_from_dict(item["principal"])
        fallbacks = [_strategy_from_dict(fb) for fb in item.get("fallbacks", [])]
        retry_policy = _retry_policy_from_dict(item.get("retry-policy", {}))
        cut = _cut_rule_from_dict(item.get("cut", {}))
        adaptive = _adaptive_from_dict(item.get("adaptive", {}))
        scene = Scene(
            scene=item["scene"],
            title=item["title"],
            principal=principal,
            outputs=item.get("outputs", {}),
            inputs=item.get("inputs", {}),
            depends_on=item.get("depends-on", []),
            fallbacks=fallbacks,
            success_when=item.get("success-when", {}),
            retry_policy=retry_policy,
            timeout_seconds=item.get("timeout-seconds", 60),
            cut=cut,
            adaptive=adaptive,
            input_trust=item.get("input-trust", {}).get("level", "trusted")
                if isinstance(item.get("input-trust"), dict)
                else item.get("input-trust", "trusted"),
            must_complete=item.get("must-complete", False),
        )
        scenes.append(scene)

    settings = ShowSettings(
        id=show["id"],
        title=show["title"],
        rehearsal=show.get("rehearsal", False),
        max_duration_seconds=show.get("max-duration-seconds", 3600),
        max_scenes=show.get("max-scenes", 100),
        sliders=show.get("sliders", {}),
        stage_manager=show.get("stage-manager", {}),
        bible=Bible(**_kebab_to_snake_dict(show.get("bible", {}))),
        running_order=scenes,
        urgent_contact=show.get("urgent-contact", {}),
    )
    # SHOW_REHEARSAL=1 env var overrides the YAML rehearsal flag
    if os.environ.get("SHOW_REHEARSAL") == "1":
        settings.rehearsal = True

    validate_show(settings)
    return settings


def validate_show(show: ShowSettings) -> None:
    if len(show.running_order) > show.max_scenes:
        raise ValidationError("Running order exceeds max-scenes.")
    scene_ids = {scene.scene for scene in show.running_order}
    if len(scene_ids) != len(show.running_order):
        raise ValidationError("Duplicate scene IDs are not allowed.")

    for scene in show.running_order:
        for dep in scene.depends_on:
            if dep not in scene_ids:
                raise ValidationError(f"Scene {scene.scene} depends on missing scene {dep}.")
        for name, binding in scene.inputs.items():
            if not isinstance(binding, str) or not binding.startswith("from(") or not binding.endswith(")"):
                raise ValidationError(
                    f"Scene {scene.scene} input '{name}' must use binding form from(scene.output)."
                )
        if not scene.outputs:
            raise ValidationError(f"Scene {scene.scene} must declare outputs.")
        if scene.input_trust not in {"trusted", "untrusted"}:
            raise ValidationError(f"Scene {scene.scene} has invalid input_trust.")
