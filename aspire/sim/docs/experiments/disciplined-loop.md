# The disciplined loop (Arm P) — what it is, in one page

*A one-page description of a process-only variant of the LIBERO fix-loop subagent prompt. It is an experiment branch, not a proposal to change the stock prompt.*

## What it is

A **5-edit patch on the stock fix-loop subagent prompt.** Nothing else — no new
harness, no new solver, no extra budget.

| | file | lines |
|---|---|---|
| stock ("Arm A") | `aspire/sim/.claude/libero/fix-loop/subagent-prompt.md` | 236 |
| disciplined ("Arm P") | `aspire/sim/.claude/libero/process/subagent-prompt.md` | 313 |
| the patch itself | `aspire/sim/scripts/libero/make_arm_p_prompt.py` | 217 |

**+79 / −2 lines.** Arm P is not maintained by hand — it is *generated* from the stock
prompt by an auditable list of five anchored edits, and each anchor must match exactly
once or the build fails, so the two cannot silently drift:

```bash
.venv/bin/python3 scripts/libero/make_arm_p_prompt.py --check
# -> "Arm P in sync with Arm A"   (exit 0)
```

That script is the documentation. Read `EDITS` in it and you have read the intervention.

## The thesis, in one sentence

**Evidence is cheap and replays are scarce, so you may not spend a replay while you
still cannot tell your hypotheses apart.**

## The five edits

1. **`four-cause-classes-source-agnostic`** — adds a fourth root-cause class,
   `Harness`. Without it, every harness defect gets misfiled as a robot failure.
2. **`contract-and-completeness`** — the load-bearing one:
   > *you may not spend a replay while two or more candidate causes remain unrefuted
   > and you have not produced evidence that separates them*

   plus **elimination is not confirmation**: narrowing to one survivor does not license
   a replay. You must either record a positive `cause_confirmed_by` — evidence the
   surviving cause *is present*, not merely that others are absent — or argue the
   candidate set is complete.
3. **`physical-needs-falsification-generic`** — a `Physical` (i.e. "impossible")
   verdict requires an *executed* falsification:
   > *A measurement mined from a trace you already have counts. A new observation you
   > construct counts. **An argument does not.***

   A guard that aborts before acting collects no evidence and can never be shown wrong.
4. **`immutable-attempts`** — every replayed program is written once as
   `attempts/attempt_<NNN>.py`; `fix_code.py` is a *copy* of the winner, never an
   in-place edit. (This is the rule whose absence upstream is the subject of
   https://github.com/NVlabs/ASPIRE/issues/22.)
5. **`findings-refutations`** — a required "Refuted hypotheses" section. A hypothesis
   that was raised, cost three replays, and was dropped otherwise leaves no trace, so
   no unbiased misattribution rate can ever be computed.

Edits 1–3 and 5 are reporting/entry obligations; 4 is an artifact contract.

## What it cost

On the one clean head-to-head (same task, same frozen 7/50 starting draft, held-out seeds 1–50):

| arm | held-out |
|---|---|
| frozen draft (shared start) | 7/50 |
| **Arm A0 — stock loop** | **42/50** |
| Arm P — disciplined loop | 12/50 |

Against the shared start, **stock gained 35 seeds and lost 0; the discipline gained 10
and lost 5, with a CI spanning zero.** The discipline lost, and lost clearly.

Three limits were recorded *before* the score existed and still hold:
* n=50 paired seeds gives exact McNemar **10.7% power** against a 10-point effect, so
  this is an estimation run, not a test.
* **The outcome measure is blind to most of the treatment.** Arm P satisfies 4/4 spec
  predicates, Arm A0 1/4 — but three of the four are properties of the *record*
  (candidate sets, refutations, positive confirmation). A pass rate cannot see them.
* The shared skill library already contains this task's localization answers,
  symmetric across arms, which shrinks what discipline could contribute.

## Why it lost, and the part worth keeping

**It is an opening rule with no closing rule.** All of Arm P's additions are entry
conditions on spending and reporting obligations. Neither the stock loop *nor* Arm P
has any rule for deciding **when to stop and what to ship** — and Arm P did not add
one. That absence was inherited, not introduced, and it is precisely the gap the
promotion gate in evosearch's Step 7 fills.

Is this the same idea as evosearch? No. The split is clean:

> **Evosearch supplies a closing rule that the disciplined loop lacks.
> The disciplined loop supplies an evidentiary bar that evosearch lacks.**

Evosearch already enforces four of Arm P's requirements *mechanically* rather than by
instruction — candidates written before any eval, a per-candidate "expected failure if
wrong" field, an eliminated-hypotheses record with a do-not-retest rule. Arm P's
genuine residue is narrower than "not duplicative" suggests: the **falsification bar**
("an argument does not count"), the positive-confirmation requirement, and the
`Harness` cause class.

## One piece of live evidence for the thesis

On the evosearch run over `push_the_plate_to_the_front_of_the_stove`, all 16 candidates
scored **0/15** — a completely flat band. The selection metric therefore produced no
information at all. The search agent still extracted real mechanism from that run, via
displacement telemetry rather than pass counts: a sharp reachability boundary
(descend 20/20 at y ≥ −0.08, 0/21 at y ≤ −0.10) that eliminated three standing
hypotheses.

Evidence-before-replay produced a finding exactly where the selection metric produced
nothing. That is the narrow claim the discipline can actually support today — **not**
that it raises pass rates, which on the one clean cell it did not.

## Reading the intervention on this branch

```bash
cd aspire/sim
.venv/bin/python3 scripts/libero/make_arm_p_prompt.py --check      # "Arm P in sync with Arm A"
diff .claude/libero/fix-loop/subagent-prompt.md .claude/libero/process/subagent-prompt.md
.venv/bin/python3 -m pytest tests/test_arm_p_prompt.py tests/test_attempt_log.py -q
```

Files on this branch beyond upstream `main`:

| file | role |
|---|---|
| `scripts/libero/make_arm_p_prompt.py` | the five anchored edits; the intervention itself |
| `.claude/libero/process/subagent-prompt.md` | generated Arm P prompt (do not hand-edit) |
| `scripts/libero/attempt_log.py`, `tests/test_attempt_log.py` | immutable `attempts/attempt_<NNN>.py` writer and the diagnosis record that edit 4 requires |
| `tests/test_arm_p_prompt.py` | fails if the generated prompt drifts from the generator |
