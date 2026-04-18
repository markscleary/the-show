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
