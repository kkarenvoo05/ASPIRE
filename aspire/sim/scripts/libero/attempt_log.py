#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Versioned attempts and the diagnosis contract for the fix loop.

Two defects this closes, both measured on the libero_goal_swap campaign:

1. NO PER-ITERATION HISTORY. The fix loop keeps exactly two code snapshots per
   task and overwrites them across retries, so 6 of 10 tasks ended with
   `initial_code.py` byte-identical to `fix_code.py`. You cannot measure what
   debugging bought from artifacts debugging overwrote. Here every replayed
   program is written once, immutably, as attempt_<NNN>.py.

2. ONLY SURVIVORS ARE RECORDED. `findings.md` states the causes the agent
   believed at the end. A hypothesis that was raised, cost three replays, and
   was dropped leaves no trace -- which is why no unbiased misattribution rate
   can be computed from the existing tree. Here every candidate cause is
   recorded WHEN RAISED, with the probe that would discriminate it and the
   outcome predicted under it.

The contract rule the prompts enforce:

    A replay may not be spent while >=2 candidate causes remain unrefuted and
    an applicable probe exists.

Probes are cheap and unmetered; replays are the scarce resource. Spending a
replay to choose between hypotheses a 30-second probe could separate is the
single most expensive habit the campaign displayed.

Usage:
    from attempt_log import AttemptLog
    log = AttemptLog(task_dir, seed=53)
    d = log.new_diagnosis(symptom="gripper_width 0.0148 after close")
    d.candidate("localization error", "Perception", probe="grasp_escape",
                predicted="width varies with grasp height")
    d.candidate("grasped then escaped", "Algorithmic", probe="grasp_escape",
                predicted="width identical at every height")
    d.record_probe(probe_result_dict)          # result dict of an executed probe
    d.refute("localization error", "width spread 1e-05 m across 4 heights")
    d.settle("grasped then escaped")
    path = log.write_attempt(code_str, d)      # -> attempts/attempt_003.py + .json
    log.set_outcome(3, reward=1.0)
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CAUSE_CLASSES = ("Physical", "Perception", "Algorithmic", "Harness")

# `Harness` is the class the original [Physical|Perception|Algorithmic] taxonomy
# lacked. Several real campaign causes were properties of the debugging
# apparatus -- an ambiguous gripper_width threshold, a self-authored guard that
# aborts before acting, a replay budget expiring on a named-but-untried fix.
# With nowhere correct to file them they were filed under Perception or
# Physical, which is precisely how they stayed hidden.


class DiagnosisError(RuntimeError):
    pass


@dataclass
class Diagnosis:
    seed: int
    symptom: str
    candidates: list[dict] = field(default_factory=list)
    probes_run: list[dict] = field(default_factory=list)
    refuted: list[dict] = field(default_factory=list)
    surviving: list[str] = field(default_factory=list)
    attributed_cause: str | None = None
    cause_confirmed_by: str | None = None
    created_at: float = field(default_factory=time.time)

    def candidate(self, cause: str, cls: str, probe: str | None = None,
                  predicted: str | None = None) -> "Diagnosis":
        if cls not in CAUSE_CLASSES:
            raise DiagnosisError(f"cause class {cls!r} not in {CAUSE_CLASSES}")
        if any(c["cause"] == cause for c in self.candidates):
            raise DiagnosisError(f"duplicate candidate {cause!r}")
        self.candidates.append({"cause": cause, "class": cls,
                                "discriminating_probe": probe,
                                "predicted_outcome": predicted})
        self.surviving.append(cause)
        return self

    def record_probe(self, result: dict) -> "Diagnosis":
        for key in ("probe", "verdict"):
            if key not in result:
                raise DiagnosisError(f"probe result missing {key!r}")
        self.probes_run.append({k: result[k] for k in
                                ("probe", "verdict", "cost_s", "reading")
                                if k in result})
        return self

    def refute(self, cause: str, evidence: str) -> "Diagnosis":
        if cause not in self.surviving:
            raise DiagnosisError(f"{cause!r} is not a surviving candidate")
        if not evidence.strip():
            raise DiagnosisError("refutation requires evidence, not an assertion")
        self.surviving.remove(cause)
        self.refuted.append({"cause": cause, "evidence": evidence})
        return self

    def settle(self, cause: str, confirmed_by: str | None = None) -> "Diagnosis":
        self.attributed_cause = cause
        self.cause_confirmed_by = confirmed_by
        return self

    # -- the gate --------------------------------------------------------
    def may_spend_replay(self) -> tuple[bool, str]:
        """The contract rule. Returns (allowed, reason).

        Blocked when two or more candidates are still standing AND at least one
        of them names a probe that has not been run. If no applicable probe
        exists, the replay IS the experiment and is allowed -- the rule exists
        to stop replays substituting for cheap discrimination, not to stop
        experiments.
        """
        if len(self.surviving) < 2:
            return True, "fewer than two candidates standing"
        ran = {p["probe"] for p in self.probes_run}
        pending = [c for c in self.candidates
                   if c["cause"] in self.surviving
                   and c["discriminating_probe"]
                   and c["discriminating_probe"] not in ran]
        if pending:
            names = ", ".join(sorted({c["discriminating_probe"] for c in pending}))
            return False, (
                f"{len(self.surviving)} candidates unrefuted and probe(s) not run: {names}. "
                "Run the probe before spending a replay."
            )
        return True, "no unrun applicable probe; the replay is the experiment"

    def to_dict(self) -> dict:
        return {
            "schema_version": "1", "seed": self.seed, "symptom": self.symptom,
            "candidates": self.candidates, "probes_run": self.probes_run,
            "refuted": self.refuted, "surviving": self.surviving,
            "attributed_cause": self.attributed_cause,
            "cause_confirmed_by": self.cause_confirmed_by,
            "probe_cost_s": round(sum(p.get("cost_s", 0) for p in self.probes_run), 2),
            "created_at": self.created_at,
        }


class AttemptLog:
    """Immutable, numbered attempts under <task_dir>/attempts/."""

    _PAT = re.compile(r"attempt_(\d{3})\.py$")

    def __init__(self, task_dir: str | Path, seed: int | None = None):
        self.dir = Path(task_dir) / "attempts"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seed = seed

    def next_index(self) -> int:
        used = [int(m.group(1)) for p in self.dir.iterdir()
                if (m := self._PAT.search(p.name))]
        return (max(used) + 1) if used else 1

    def new_diagnosis(self, symptom: str, seed: int | None = None) -> Diagnosis:
        s = seed if seed is not None else self.seed
        if s is None:
            raise DiagnosisError("seed required")
        return Diagnosis(seed=s, symptom=symptom)

    def write_attempt(self, code: str, diagnosis: Diagnosis | None = None) -> Path:
        allowed, reason = (diagnosis.may_spend_replay() if diagnosis else (True, "no diagnosis"))
        i = self.next_index()
        py = self.dir / f"attempt_{i:03d}.py"
        if py.exists():  # immutable by construction
            raise DiagnosisError(f"{py} exists; attempts are never overwritten")
        py.write_text(code)
        meta = {
            "attempt": i, "seed": diagnosis.seed if diagnosis else self.seed,
            "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
            "replay_allowed": allowed, "replay_gate_reason": reason,
            "diagnosis": diagnosis.to_dict() if diagnosis else None,
            "outcome": None,
        }
        (self.dir / f"attempt_{i:03d}.json").write_text(json.dumps(meta, indent=2) + "\n")
        return py

    def set_outcome(self, index: int, reward: float | None,
                    note: str | None = None) -> None:
        j = self.dir / f"attempt_{index:03d}.json"
        meta = json.loads(j.read_text())
        meta["outcome"] = {"reward": reward, "passed": bool(reward and reward > 0),
                           "note": note, "at": time.time()}
        j.write_text(json.dumps(meta, indent=2) + "\n")

    # -- metrics ---------------------------------------------------------
    def summary(self) -> dict:
        metas = [json.loads(p.read_text()) for p in sorted(self.dir.glob("attempt_*.json"))]
        by_seed: dict[int, list[dict]] = {}
        for m in metas:
            by_seed.setdefault(m.get("seed"), []).append(m)
        first_success, probe_s = {}, 0.0
        for s, ms in by_seed.items():
            for n, m in enumerate(ms, 1):
                d = m.get("diagnosis") or {}
                probe_s += d.get("probe_cost_s", 0) or 0
                if (m.get("outcome") or {}).get("passed") and s not in first_success:
                    first_success[s] = n
        return {
            "attempts": len(metas),
            "seeds": len(by_seed),
            "replays_to_first_success": first_success,
            "median_replays_to_first_success": _median(list(first_success.values())),
            "probe_cost_s": round(probe_s, 2),
            "gate_blocked": sum(1 for m in metas if not m.get("replay_allowed", True)),
        }


def _median(xs):
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
