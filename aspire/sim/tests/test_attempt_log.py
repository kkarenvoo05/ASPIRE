# SPDX-License-Identifier: Apache-2.0
"""Tests for the diagnosis contract.

The contract's whole value is that it BLOCKS something. A gate that never fires
is documentation, so these tests assert the blocking behaviour directly rather
than only the happy path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/libero"))
from attempt_log import AttemptLog, Diagnosis, DiagnosisError  # noqa: E402


def _d(seed=53):
    return Diagnosis(seed=seed, symptom="gripper_width 0.0148 after close")


def test_gate_blocks_replay_while_two_causes_stand():
    d = _d()
    d.candidate("localization error", "Perception", probe="grasp_escape",
                predicted="width varies with height")
    d.candidate("grasped then escaped", "Algorithmic", probe="grasp_escape",
                predicted="width identical at every height")
    allowed, reason = d.may_spend_replay()
    assert not allowed
    assert "grasp_escape" in reason


def test_gate_opens_once_a_candidate_is_refuted():
    d = _d()
    d.candidate("localization error", "Perception", probe="grasp_escape", predicted="varies")
    d.candidate("grasped then escaped", "Algorithmic", probe="grasp_escape", predicted="identical")
    d.record_probe({"probe": "grasp_escape", "verdict": "grasped_then_escaped", "cost_s": 28.4})
    d.refute("localization error", "width spread 1e-05 m across 4 heights")
    allowed, _ = d.may_spend_replay()
    assert allowed
    assert d.surviving == ["grasped then escaped"]


def test_gate_opens_when_probe_was_run_even_if_ambiguous():
    """If the applicable probe has been run, the replay IS the next experiment.

    The rule exists to stop replays substituting for cheap discrimination, not
    to deadlock when discrimination has been attempted and failed.
    """
    d = _d()
    d.candidate("a", "Physical", probe="contact_transfer", predicted="no motion")
    d.candidate("b", "Algorithmic", probe="contact_transfer", predicted="slip")
    d.record_probe({"probe": "contact_transfer", "verdict": "inconclusive"})
    allowed, reason = d.may_spend_replay()
    assert allowed and "no unrun applicable probe" in reason


def test_gate_allows_when_no_probe_applies():
    d = _d()
    d.candidate("a", "Physical")
    d.candidate("b", "Algorithmic")
    assert d.may_spend_replay()[0]


def test_refutation_requires_evidence():
    d = _d()
    d.candidate("a", "Perception", probe="p", predicted="x")
    with pytest.raises(DiagnosisError, match="evidence"):
        d.refute("a", "   ")


def test_cannot_refute_an_unraised_cause():
    d = _d()
    with pytest.raises(DiagnosisError, match="not a surviving candidate"):
        d.refute("never mentioned", "some evidence")


def test_harness_is_a_valid_class_and_typos_are_not():
    d = _d()
    d.candidate("ambiguous threshold", "Harness", probe="grasp_escape", predicted="identical")
    with pytest.raises(DiagnosisError, match="not in"):
        d.candidate("x", "algorithmic")  # lowercase is a typo, not a class


def test_attempts_are_immutable_and_numbered(tmp_path):
    log = AttemptLog(tmp_path, seed=53)
    p1 = log.write_attempt("print(1)\n")
    p2 = log.write_attempt("print(2)\n")
    assert p1.name == "attempt_001.py" and p2.name == "attempt_002.py"
    assert p1.read_text() != p2.read_text()
    meta = json.loads((tmp_path / "attempts/attempt_001.json").read_text())
    assert meta["code_sha256"] and meta["outcome"] is None


def test_attempt_log_records_the_gate_decision(tmp_path):
    """A blocked replay must leave a trace, or the metric is unrecoverable."""
    log = AttemptLog(tmp_path, seed=53)
    d = _d()
    d.candidate("a", "Perception", probe="grasp_escape", predicted="varies")
    d.candidate("b", "Algorithmic", probe="grasp_escape", predicted="identical")
    log.write_attempt("print(0)\n", d)
    meta = json.loads((tmp_path / "attempts/attempt_001.json").read_text())
    assert meta["replay_allowed"] is False
    assert "grasp_escape" in meta["replay_gate_reason"]
    assert log.summary()["gate_blocked"] == 1


def test_summary_computes_replays_to_first_success(tmp_path):
    log = AttemptLog(tmp_path, seed=53)
    for i, r in enumerate([0.0, 0.0, 1.0], start=1):
        log.write_attempt(f"print({i})\n")
        log.set_outcome(i, reward=r)
    s = log.summary()
    assert s["attempts"] == 3
    assert s["replays_to_first_success"] == {53: 3}


def test_probe_cost_is_accumulated_for_the_cheapness_claim(tmp_path):
    """The 'probes are ~free' claim has to be backed by recorded numbers."""
    log = AttemptLog(tmp_path, seed=53)
    d = _d()
    d.candidate("a", "Perception", probe="grasp_escape", predicted="varies")
    d.record_probe({"probe": "grasp_escape", "verdict": "x", "cost_s": 28.35})
    log.write_attempt("print(0)\n", d)
    assert log.summary()["probe_cost_s"] == 28.35
