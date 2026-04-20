"""Tests for the YAML loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from loader import load_show, ValidationError


YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"


def test_loads_example_show():
    show = load_show(YAML_PATH)
    assert show.id == "outreach-enrichment-001"
    assert show.title == "Outreach enrichment run"
    assert len(show.running_order) == 5


def test_scene_ids():
    show = load_show(YAML_PATH)
    ids = [s.scene for s in show.running_order]
    assert ids == [
        "load_targets",
        "approve_run",
        "enrich_contacts",
        "filter_contacts",
        "write_output",
    ]


def test_bible_kebab_to_snake():
    """Bug 1 fix: adaptation-bounds should map to adaptation_bounds."""
    show = load_show(YAML_PATH)
    assert show.bible.adaptation_bounds == {"batch-size": {"min": 2, "max": 20}}


def test_strategy_success_when():
    """Strategies can declare their own success-when; loader must parse it."""
    show = load_show(YAML_PATH)
    # The example show doesn't have per-strategy success-when, so check default empty dict
    load_targets = show.running_order[0]
    assert load_targets.principal.success_when == {}


def test_adaptive_config_parsed():
    show = load_show(YAML_PATH)
    enrich = next(s for s in show.running_order if s.scene == "enrich_contacts")
    assert enrich.adaptive.allowed is True
    assert enrich.adaptive.bounds["batch-size"]["min"] == 3


def test_input_trust_parsed():
    show = load_show(YAML_PATH)
    enrich = next(s for s in show.running_order if s.scene == "enrich_contacts")
    assert enrich.input_trust == "untrusted"


def test_missing_show_key_raises():
    import tempfile, yaml
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump({"not_show": {}}, f)
        f.flush()
        with pytest.raises(ValidationError):
            load_show(f.name)


_APPROVAL_GATE_SCENE_YAML = """
show:
  id: approval-test-{suffix}
  title: Approval Test
  running-order:
    - scene: gate
      title: Human Gate
      outputs:
        decision: {{type: string, schema: string}}
      principal:
        method: human-approval
        agent: stage-manager
        brief: "Approve?"
"""

_APPROVAL_GATE_WITH_TIMEOUT_YAML = """
show:
  id: approval-timeout-{suffix}
  title: Approval Timeout Test
  running-order:
    - scene: gate
      title: Human Gate
      timeout-seconds: {timeout}
      outputs:
        decision: {{type: string, schema: string}}
      principal:
        method: human-approval
        agent: stage-manager
        brief: "Approve?"
"""


def _write_yaml(tmp_path, content, name="show.yaml"):
    p = tmp_path / name
    p.write_text(content)
    return p


def test_approval_gate_default_timeout_is_7_days(tmp_path):
    """An approval gate with no declared timeout should default to 7 days (604800s)."""
    p = _write_yaml(tmp_path, _APPROVAL_GATE_SCENE_YAML.format(suffix="default"))
    show = load_show(p)
    gate = show.running_order[0]
    assert gate.timeout_seconds == 604800


def test_approval_gate_declared_timeout_honoured(tmp_path):
    """An approval gate with timeout-seconds: 300 should use exactly 300."""
    p = _write_yaml(
        tmp_path,
        _APPROVAL_GATE_WITH_TIMEOUT_YAML.format(suffix="declared", timeout=300),
    )
    show = load_show(p)
    gate = show.running_order[0]
    assert gate.timeout_seconds == 300


def test_approval_gate_declared_7day_timeout_honoured(tmp_path):
    """An approval gate with timeout-seconds: 604800 should use exactly 604800."""
    p = _write_yaml(
        tmp_path,
        _APPROVAL_GATE_WITH_TIMEOUT_YAML.format(suffix="7days", timeout=604800),
    )
    show = load_show(p)
    gate = show.running_order[0]
    assert gate.timeout_seconds == 604800


def test_approval_gate_short_timeout_emits_warning(tmp_path, capsys):
    """Validation should warn when an approval gate has timeout < 86400s (24h)."""
    p = _write_yaml(
        tmp_path,
        _APPROVAL_GATE_WITH_TIMEOUT_YAML.format(suffix="warn", timeout=300),
    )
    load_show(p)
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "gate" in captured.out
    assert "less than 24 hours" in captured.out


def test_approval_gate_no_warning_for_7day_timeout(tmp_path, capsys):
    """No warning when approval gate has timeout >= 86400s."""
    p = _write_yaml(
        tmp_path,
        _APPROVAL_GATE_WITH_TIMEOUT_YAML.format(suffix="nowarn", timeout=604800),
    )
    load_show(p)
    captured = capsys.readouterr()
    assert "[WARN]" not in captured.out


def test_non_approval_scene_default_timeout_unchanged(tmp_path):
    """Non-approval scenes should still default to 60s."""
    content = """
show:
  id: non-approval-test
  title: Non-approval Test
  running-order:
    - scene: task
      title: Regular Task
      outputs:
        result: {type: string, schema: string}
      principal:
        method: tool-call
        agent: deep-dive
        action: read-csv
"""
    p = _write_yaml(tmp_path, content)
    show = load_show(p)
    assert show.running_order[0].timeout_seconds == 60


def test_example_show_approve_run_defaults_to_7_days():
    """The example show's approve_run scene (no timeout declared) should be 7 days."""
    show = load_show(YAML_PATH)
    gate = next(s for s in show.running_order if s.scene == "approve_run")
    assert gate.timeout_seconds == 604800


def test_duplicate_scene_ids_raise(tmp_path):
    content = """
show:
  id: dup-test
  title: Dup
  running-order:
    - scene: foo
      title: Foo
      outputs:
        out: {type: string, schema: string}
      principal:
        method: tool-call
        agent: agent1
        action: read-csv
    - scene: foo
      title: Foo Again
      outputs:
        out: {type: string, schema: string}
      principal:
        method: tool-call
        agent: agent1
        action: read-csv
"""
    p = tmp_path / "dup.yaml"
    p.write_text(content)
    with pytest.raises(ValidationError, match="Duplicate"):
        load_show(p)
