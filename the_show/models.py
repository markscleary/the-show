from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union


@dataclass
class RetryPolicy:
    max_attempts: int = 1
    backoff: str = "none"
    base_delay_seconds: float = 0.0
    jitter: bool = False
    retriable_errors: List[str] = field(default_factory=list)


@dataclass
class Strategy:
    method: str
    agent: str
    action: Optional[str] = None
    brief: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    label: Optional[str] = None
    success_when: Dict[str, Any] = field(default_factory=dict)  # per-strategy override; falls back to scene-level
    severity: str = "urgent"  # for human-approval: urgent | critical
    channels: Optional[List[str]] = None  # per-scene channel filter for human-approval (None = all)
    to: Optional[Union[str, List[str]]] = None  # per-scene handle filter for human-approval (None = all)


@dataclass
class AdaptiveConfig:
    allowed: bool = False
    bounds: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class CutRule:
    condition: str = "escalate"
    reason: Optional[str] = None
    minimum_acceptable: Optional[int] = None


@dataclass
class Scene:
    scene: str
    title: str
    principal: Strategy
    outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    inputs: Dict[str, str] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    fallbacks: List[Strategy] = field(default_factory=list)
    success_when: Dict[str, Any] = field(default_factory=dict)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_seconds: int = 60
    cut: CutRule = field(default_factory=CutRule)
    adaptive: AdaptiveConfig = field(default_factory=AdaptiveConfig)
    input_trust: str = "trusted"
    must_complete: bool = False


@dataclass
class Bible:
    objective: str = ""
    escalation: Dict[str, Any] = field(default_factory=dict)
    reporting: Dict[str, Any] = field(default_factory=dict)
    adaptation_bounds: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class ShowSettings:
    id: str
    title: str
    rehearsal: bool = False
    max_duration_seconds: int = 3600
    max_scenes: int = 100
    sliders: Dict[str, str] = field(default_factory=dict)
    stage_manager: Dict[str, str] = field(default_factory=dict)
    bible: Bible = field(default_factory=Bible)
    running_order: List[Scene] = field(default_factory=list)
    urgent_contact: Dict[str, Any] = field(default_factory=dict)  # contacts, mode, throttle config


@dataclass
class AttemptRecord:
    scene: str
    strategy_label: str
    status: str
    error_type: Optional[str] = None
    message: Optional[str] = None
    duration_ms: int = 0
    cost_usd: float = 0.0


@dataclass
class SceneState:
    scene: str
    status: str = "queued"
    attempts: List[AttemptRecord] = field(default_factory=list)
    selected_strategy: Optional[str] = None
    output_bindings: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    skip_reason: Optional[str] = None


@dataclass
class ShowState:
    show_id: str
    title: str
    status: str = "planned"
    scenes: Dict[str, SceneState] = field(default_factory=dict)
    outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    total_cost_usd: float = 0.0
    events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MonitorEvent:
    id: int
    show_id: str
    trigger_type: str   # oscillation | stalled | retry-storm | cost-runaway | policy-denials
    severity: str       # info | warning | urgent | critical
    scene_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    threshold_config: Optional[str] = None
    acknowledged: bool = False
    created_at: Optional[str] = None
