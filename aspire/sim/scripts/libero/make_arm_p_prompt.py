#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Generate the Arm P (process-only) subagent prompt as an auditable patch of Arm A.

Arm B (the full diagnosis-harness prompt, not on this branch) bundles two kinds of intervention:

  KNOWLEDGE  the curated probe library and the corrected gripper-width decoder
  PROCESS    the contract, the immutable attempt log, the falsification bar, the
             required refuted-hypothesis section, the `Harness` cause class

A vs B therefore compares the whole bundle against nothing, and cannot say which
half did the work. The half a reader will discount first is the KNOWLEDGE half,
because `probes.py` was reverse-engineered from failures of the very tasks it is
evaluated on (8 of 10 contributed cases, including all four with headroom). No
individual probe contains a task's answer, but the *selection* carries information
about the exam.

Arm P is the process half alone. It is uncontaminated by construction: every rule
below is a global discipline that encodes no task-specific content, and would have
been written the same way had a different set of failures been read.

Measured basis for the split, across both Arm B runs:
ZERO of the seven library probes were executed. The winning cell
confirmed its causes from `trace.json` already collected. So the knowledge half was
inert, and Arm B as executed was already close to Arm P.

    .venv/bin/python3 scripts/libero/make_arm_p_prompt.py          # write
    .venv/bin/python3 scripts/libero/make_arm_p_prompt.py --check  # verify in sync
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[2]
ARM_A = SIM / ".claude/libero/fix-loop/subagent-prompt.md"
ARM_P = SIM / ".claude/libero/process/subagent-prompt.md"

# Anchors are literal excerpts of Arm A.
# Each must appear exactly once in Arm A or the build fails, so the arms cannot
# silently drift apart.
#
# DELIBERATELY OMITTED from Arm P (these are Arm B's KNOWLEDGE half):
#   * "decoder-is-ambiguous" -- the corrected gripper-width decoder. Pure knowledge,
#     and it names a specific task's answer.
#   * every reference to `probes.py`, to named probes, and to the shared
#     diagnose.md / pitfalls.md skill files. Probe NAMES alone shape the hypothesis
#     vocabulary: in both Arm B runs the winning records named `ik_branch` as the discriminator
#     they would use and then declined to run it. That is still knowledge delivery.
#
# Task identifiers are stripped from every lesson below. Citing `push_the_plate`'s
# refuted `Physical` verdict inside a prompt that is then evaluated on
# `push_the_plate` is answer-key leakage for that task.
EDITS: list[tuple[str, str, str]] = [
    (
        # PROCESS. Adds the fourth cause class and a source-agnostic falsification
        # field. Arm B's version reads "the probe you RAN"; Arm P accepts evidence
        # from any source, so the rule does not smuggle in the probe library.
        "four-cause-classes-source-agnostic",
        """    ## Root Cause: [Physical|Perception|Algorithmic]""",
        """    ## Root Cause: [Physical|Perception|Algorithmic|Harness]
    ## Falsification: <the evidence you produced and what it showed. A measurement
    mined from a trace you already have counts. A new observation you construct
    counts. An argument does not.>""",
    ),
    (
        # PROCESS. The contract, the attempt log, and the completeness rule.
        # Source-agnostic throughout: it demands EVIDENCE, never a named probe.
        "contract-and-completeness",
        """**Hard limit: 3 replay attempts per seed.** After 3 failed replays (reward=0), write BLOCKED.md
and move immediately to the next seed — no further attempts, no exceptions.""",
        """**Mine what you already have before you spend anything.** Every sweep leaves
`trace.json`, keyframes, and a per-seed scoreboard behind. Reading them costs no
replay budget. In the previous campaign the strongest fix produced was confirmed
entirely from traces already on disk, with no new replay spent.

**The contract rule: you may not spend a replay while two or more candidate causes
remain unrefuted and you have not produced evidence that separates them.** Record
candidates when you raise them, via `scripts/libero/attempt_log.py`:

    from attempt_log import AttemptLog
    log = AttemptLog(TASK_DIR, seed=N)
    d = log.new_diagnosis(symptom="...")
    d.candidate("<cause>", "<class>", predicted="<what would distinguish it>")
    d.refute("<cause>", "<evidence>")
    allowed, reason = d.may_spend_replay()
    path = log.write_attempt(code_str, d)   # immutable attempts/attempt_NNN.py
    log.set_outcome(NNN, reward=...)

**Completeness check — REQUIRED before you attribute a cause.** State what would
have to be true for NONE of your candidates to be right. If you cannot rule that out
with evidence you already hold, add it as a candidate and keep going.

A cause you never named can never be refuted. Elimination over an incomplete set
does not produce a cautious wrong answer — it produces a *confident* one, carrying
all the apparent rigour of the refutations that preceded it. This is the specific
way a disciplined loop fails, and it is measured: one previous diagnosis quantified
its symptom correctly, named two candidates, ran a discriminating test, got a true
reading, refuted one candidate on that reading, crowned the survivor, and fixed
exactly the crowned cause — for 0/15 development seeds and 0/50 held out. The true
cause was never among the two.

**Elimination is not confirmation.** Narrowing to one surviving candidate does NOT
by itself license a replay. Before attributing, do one of:
  * record a positive confirmation in `cause_confirmed_by` — evidence that the
    surviving cause IS PRESENT, not merely that the others are absent; or
  * write an explicit exhaustiveness argument for why the candidate set is complete.

**Hard limit: 3 replay attempts per seed.** After 3 failed replays (reward=0), write BLOCKED.md
and move immediately to the next seed — no further attempts, no exceptions.

Before writing BLOCKED.md, name the change you did not get to try. One task in the
previous campaign did, and a later task confirmed that exact change on the exact
seeds the first had blocked on — at least 3 of that campaign's 23 blocked seeds were
budget artifacts, not real blockers.""",
    ),
    (
        # PROCESS. Requires an executed falsification for the one verdict that is
        # self-sealing. Arm B names `guard_veto`/`contact_transfer`; Arm P states the
        # requirement behaviourally so no probe is named. Task identifier stripped.
        "physical-needs-falsification-generic",
        """    ## Details: <what exactly fails and why>""",
        """    ## Details: <what exactly fails and why>
    A `Physical` verdict REQUIRES an executed falsification: you must let the motion
    happen and measure the outcome. A guard that aborts before acting collects no
    evidence and can never be shown wrong. In the previous campaign one task was
    closed `Physical` on exactly that mistake — 15/15 development seeds and 0/50 held
    out — and the verdict was later refuted by existence proof when the task was made
    to succeed. A narrative about an exhausted search is not evidence of
    impossibility.""",
    ),
    (
        # PROCESS. Immutable iteration history. Identical to Arm B's edit.
        "immutable-attempts",
        """Save to TWO locations (create `outputs/working_codes` first if missing):""",
        """Every replayed program must already exist as an immutable `attempts/attempt_<NNN>.py`
(see the contract above). `fix_code.py` is a COPY of the winning attempt, never an
in-place edit — 6 of 10 tasks in the previous campaign ended with `initial_code.py`
byte-identical to `fix_code.py`, which destroyed the per-iteration history.

Save to TWO locations (create `outputs/working_codes` first if missing):""",
    ),
    (
        # PROCESS. Refuted hypotheses are findings. Identical to Arm B's edit except
        # that it does not route them into the shared pitfalls library, which both
        # arms can read.
        "findings-refutations",
        """   If nothing generalizes beyond this task, write "none".>""",
        """   If nothing generalizes beyond this task, write "none".>

  ## Refuted hypotheses (REQUIRED — write "none" only if you refuted nothing)
  <one bullet per cause you raised and then ruled out, with: Trigger (the symptom that
   suggested it), Why it looked right, what Distinguished it, and the Evidence that
   killed it. A refuted hypothesis is a finding: the previous campaign discarded all
   of them, so later tasks re-paid for the same wrong turns.>

  ## Causes considered and NOT ruled out (REQUIRED — write "none" only if none remain)
  <one bullet per cause still standing when you stopped, and what evidence would
   settle it. An unresolved cause recorded is cheap; an unnamed one is what makes the
   next agent repeat your mistake.>""",
    ),
]

HEADER = """<!-- GENERATED FILE — do not edit by hand.
     Produced by scripts/libero/make_arm_p_prompt.py from
     .claude/libero/fix-loop/subagent-prompt.md.
     Arm P (process only) of the diagnosis-harness ablation. Every difference from
     Arm A is one of the named edits in that script, so the arms cannot silently
     drift apart. Arm P deliberately contains NO probe library, no named probe, and
     no task identifiers.
     Regenerate with:  .venv/bin/python3 scripts/libero/make_arm_p_prompt.py -->

"""


def build() -> str:
    src = ARM_A.read_text()
    for name, anchor, repl in EDITS:
        n = src.count(anchor)
        if n != 1:
            raise SystemExit(
                f"edit {name!r}: anchor found {n} times in Arm A (expected exactly 1). "
                "Arm A changed; update EDITS rather than letting the arms diverge."
            )
        src = src.replace(anchor, repl)
    src = src.replace("name: libero-fix-loop-subagent-prompt",
                      "name: libero-process-subagent-prompt")
    return HEADER + src


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    want = build()
    if a.check:
        if not ARM_P.exists() or ARM_P.read_text() != want:
            print("Arm P is OUT OF SYNC with Arm A. Diff (current -> expected):")
            cur = ARM_P.read_text().splitlines() if ARM_P.exists() else []
            sys.stdout.writelines(difflib.unified_diff(
                cur, want.splitlines(), "current", "expected", lineterm="", n=1))
            return 1
        print("Arm P in sync with Arm A")
        return 0
    ARM_P.parent.mkdir(parents=True, exist_ok=True)
    ARM_P.write_text(want)
    added = len(want.splitlines()) - len(ARM_A.read_text().splitlines())
    print(f"wrote {ARM_P.relative_to(SIM)} ({len(EDITS)} edits, +{added} lines vs Arm A)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
