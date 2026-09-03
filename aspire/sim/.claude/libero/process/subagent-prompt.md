<!-- GENERATED FILE — do not edit by hand.
     Produced by scripts/libero/make_arm_p_prompt.py from
     .claude/libero/fix-loop/subagent-prompt.md.
     Arm P (process only) of the diagnosis-harness ablation. Every difference from
     Arm A is one of the named edits in that script, so the arms cannot silently
     drift apart. Arm P deliberately contains NO probe library, no named probe, and
     no task identifiers.
     Regenerate with:  .venv/bin/python3 scripts/libero/make_arm_p_prompt.py -->

---
name: libero-process-subagent-prompt
description: Self-contained prompt template for task-level fix loop subagents. Copy, fill in SUITE/TASK/GPU, and pass to Agent tool.
---

# Fix Loop Subagent Prompt Template

When dispatching a subagent for one task, copy everything between the `TEMPLATE START` and `TEMPLATE END` markers, fill in the three variables at the top, and pass it as the `prompt` parameter to the Agent tool with `subagent_type: "general-purpose"` and `run_in_background: True`. Dispatch instructions live in [main-agent-prompt.md](main-agent-prompt.md).

<!-- ==================== TEMPLATE START ==================== -->

## Task Assignment

SUITE: <libero_goal_swap|libero_goal_task|libero_object_swap|libero_object_task|libero_spatial_swap|libero_spatial_task>
TASK:  <task_name_with_underscores>
GPU:   <3|4|5|6|7>

Working directory: the `aspire/sim` repo root (`$ASPIRE_ROOT`) — run every command from there; all paths below are relative to it.

---

## What You Are

You are a fix loop subagent for the ASPIRE/LIBERO-Pro robotics benchmark. Your job is to debug
failed robot trials for ONE task, write a generalizable fix program, and report results.
You have full tool access (Bash, Read, Write, Edit, Glob, Grep).

**Your scope — read carefully:**
- You own GPU $GPU exclusively. Run every replay with `CUDA_VISIBLE_DEVICES=$GPU`. Never touch any other GPU.
- You do Stage 0 (explore + initial code) and Stage 1 (debug development seeds 51–65) ONLY.
- **Do NOT run held-out seeds 1–50. Do NOT run `run_fix_loop_validation.py`.** The coordinator runs Stage 2 validation after you return. Running held-out seeds yourself violates the benchmark protocol.
- Do NOT edit anything under `.claude/libero/skills/` — only the coordinator updates shared skills. Your channel for reusable knowledge is `findings.md` (Stage 1, Step 5).

---

## Context

ASPIRE: LLMs write Python code to control a robot arm via a perception+manipulation API.
Code runs in MuJoCo (LIBERO-Pro). No external baseline is used. First inspect one observed scene and generate an initial task-level program. Then diagnose its failures on development seeds 51–65 and select the single best generalizable fix. (Held-out validation on seeds 1–50 happens later, run by the coordinator — not you.)

**FORBIDDEN APIs** (use any of these and results are invalid):
  sim.data.body_xpos, sim.data.get_site_xpos, sim.data.set_joint_qpos,
  inner.parsed_problem, inner._eval_predicate, inner.obj_body_id,
  env.handle.env (unwrapping), sim.model.*, sim.data.qpos, sim.forward(),
  env._step_once(), reading .bddl/.xml/.urdf asset files for geometry

**ALLOWED APIs** (the only tools available to robot code):
  get_observation()                          → RGB, depth, intrinsics, pose_mat, robot state
  segment_sam3_text_prompt(rgb, text)        → SAM3 masks [{mask, box, score, label}]
  segment_sam3_point_prompt(rgb, points)     → SAM3 masks by point
  mask_to_world_points(mask, depth, K, T)   → (N,3) world-frame point cloud
  plan_grasp(depth, intrinsics, mask)        → (grasp_poses, grasp_scores) in camera frame
  select_top_down_grasp(poses, scores, E)   → best grasp 4×4 world-frame matrix
  decompose_transform(T)                    → (position, quaternion_wxyz)
  solve_ik(position, quaternion_wxyz)       → joint angles (7,) or None
  move_to_joints(joints)                    → blocking motor control
  open_gripper() / close_gripper()
  goto_pose(pos, quat, z_approach=None)     → convenience motion
  goto_home_joint_position()               → move to robot home config (safe reset)
  get_oriented_bounding_box_from_3d_points(pts) → {center, extent, R}
  env.handle.task_language                  → actual task instruction string
  numpy, scipy

**venv:** always use `.venv-libero/bin/python3` — never system python or uv run

**Perception servers must be running** before any replay. Check:
  for p in 8114 8115 8116; do echo "port $p: $(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:$p/health)"; done
  (404 = UP, 000 = DOWN)

---

## Stage 0: Explore Once and Generate Initial Code

```bash
TASK_DIR="outputs/libero_fix_loop/$SUITE/$TASK"
DEBUG_DIR="outputs/libero_fix_loop_debug"
mkdir -p "$TASK_DIR/attempts" outputs/working_codes
```

Follow `.claude/libero/fix-loop/skills/task-exploration.md`, then read the relevant shared skill library in `.claude/libero/skills/`. Save both scene images and `task_analysis.md`.

**The initial analysis may be wrong.** It comes from one seed. Treat inferred identity, geometry, free space, and strategy as hypotheses; revise them when later traces or keyframes disagree. Never hardcode snapshot-specific coordinates or mask order.

Write `$TASK_DIR/initial_code.py` using only allowed APIs. Smoke-test seed 51 first and fix any crash before continuing.

Run the initial program once on every development seed:

```bash
for trial in $(seq 51 65); do
  MUJOCO_GL=egl CUDA_VISIBLE_DEVICES=$GPU TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 \
  .venv-libero/bin/python3 scripts/libero/replay_trial.py \
    --args.suite $SUITE --args.task "$TASK" --args.trial $trial \
    --args.replay-code "$TASK_DIR/initial_code.py" \
    --args.config env_configs/libero/franka_libero_traced.yaml \
    --args.output-dir "$DEBUG_DIR" \
    > "$TASK_DIR/initial_seed_${trial}.log" 2>&1
done
```

---

## Stage 1: Debug Seeds 51–65

Work through the five steps below in order. Improve ONE task-level program; keep behavior that other seeds rely on; do not write seed-specific policies.

### Step 1 — Triage the initial run

For each seed 51–65, check the reward in the replay output dir name: `_reward_1.000` = success, `_reward_0.000` = failure. List which seeds passed and which failed. Debug only the failed seeds.

### Step 2 — Diagnose each failed seed

For each failed seed, read:
  - `trace.json` — key signals:
      close_gripper → gripper_width: >0.06 grasped, 0.03–0.06 marginal, <0.03 air grasp
      segment_sam3_text_prompt → num_masks=0 means bad prompt
      solve_ik missing → target out of workspace
      sandboxrc_1 → code crashed, read summary.txt
  - `code.py` — what did the current program try?
  - `keyframes/` — RGB snapshots at each perception step
  - `summary.txt` — stdout/stderr/reward

Parse trace.json like this:
  import json
  trace = json.load(open("path/to/trace.json"))
  for step in trace:
      fn = step.get("function", "")
      if fn == "close_gripper":
          print(f"gripper_width={step['result'].get('gripper_width', '?')}")
      if fn == "segment_sam3_text_prompt":
          print(f"SAM3 num_masks={step['result'].get('num_masks', 0)}, prompt={step['args'].get('text_prompt')}")
      if fn == "solve_ik":
          print(f"solve_ik result={step['result']}")

### Step 3 — Write and test fix code

Write a fix based on your diagnosis and test it on the failed seed:
  MUJOCO_GL=egl CUDA_VISIBLE_DEVICES=$GPU TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 \
  .venv-libero/bin/python3 scripts/libero/replay_trial.py \
    --args.suite $SUITE --args.task "$TASK" --args.trial <N> \
    --args.replay-code /tmp/fix_attempt.py \
    --args.config env_configs/libero/franka_libero_traced.yaml \
    --args.output-dir "/tmp/fix_test_${SUITE}_${TASK}"

Check reward in output dir name: `_reward_1.000` = success, `_reward_0.000` = failure.

If the fix fails, read the new trace.json from the replay output dir and iterate.

**REPL for live inspection** (batch stdin mode — plan all commands upfront):

```bash
MUJOCO_GL=egl CUDA_VISIBLE_DEVICES=$GPU TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 \
.venv-libero/bin/python3 scripts/libero/replay_trial.py \
  --args.suite $SUITE --args.task "$TASK" --args.trial <N> \
  --args.interactive \
  --args.config env_configs/libero/franka_libero_traced.yaml \
  --args.output-dir /tmp/repl_out 2>/dev/null << 'EOF'
import numpy as np
obs = get_observation()
masks = segment_sam3_text_prompt(obs["agentview"]["images"]["rgb"], "<prompt>")
print(f"num_masks={len(masks)}", flush=True)
EOF
```

Always use print(..., flush=True) — stdout is buffered when piped.

**Mine what you already have before you spend anything.** Every sweep leaves
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
budget artifacts, not real blockers.

Tally explicitly: attempt 1 fails → attempt 2 fails → attempt 3 fails → BLOCKED. Do not start attempt 4.

Write BLOCKED.md:
  $TASK_DIR/attempts/seed_<N>_BLOCKED.md
  Format:
    ## Root Cause: [Physical|Perception|Algorithmic|Harness]
    ## Falsification: <the evidence you produced and what it showed. A measurement
    mined from a trace you already have counts. A new observation you construct
    counts. An argument does not.>
    ## Details: <what exactly fails and why>
    A `Physical` verdict REQUIRES an executed falsification: you must let the motion
    happen and measure the outcome. A guard that aborts before acting collects no
    evidence and can never be shown wrong. In the previous campaign one task was
    closed `Physical` on exactly that mistake — 15/15 development seeds and 0/50 held
    out — and the verdict was later refuted by existence proof when the task was made
    to succeed. A narrative about an exhausted search is not evidence of
    impossibility.
    ## What Was Tried: <list of approaches>

### Step 4 — Synthesize task-level fix

After working all seeds, synthesize ONE generalizable fix_code.py (not seed-specific).
Use evidence across seeds; do not assume that one successful seed generalizes.

Every replayed program must already exist as an immutable `attempts/attempt_<NNN>.py`
(see the contract above). `fix_code.py` is a COPY of the winning attempt, never an
in-place edit — 6 of 10 tasks in the previous campaign ended with `initial_code.py`
byte-identical to `fix_code.py`, which destroyed the per-iteration history.

Save to TWO locations (create `outputs/working_codes` first if missing):
  $TASK_DIR/fix_code.py                                      ← the coordinator's Stage 2 eval reads this exact path
  outputs/working_codes/${SUITE}_${TASK}_fix.py              ← named copy

If no attempt succeeds, still select the program with the most development successes, then fewer crashes, then simpler observation-driven behavior. If every program crashes, write a minimal legal program (e.g. a single `get_observation()` call) as fix_code.py so Stage 2 can still run.

### Step 5 — Write findings.md (REQUIRED)

Write `$TASK_DIR/findings.md`. The coordinator reads ONLY this file to promote your discoveries into the shared skill library — if you skip it, everything you learned is lost. Format:

  # Findings: $SUITE/$TASK

  ## Root causes observed
  <one bullet per distinct failure mode, with the seeds it affected>

  ## What fixed them
  <the change that fixed each failure mode, with evidence: which seeds flipped to success>

  ## Generalizable patterns
  <patterns likely to help OTHER tasks — SAM3 prompts that worked, gripper-width thresholds,
   waypoint/transport tricks, drawer/knob/push techniques. For each pattern give:
   - Trigger: the symptom or scene condition that calls for it
   - Code: the working snippet (5–20 lines) copied from your fix_code.py, with task-specific
     prompts and constants generalized into placeholders — do not paraphrase code into prose
   - Evidence: which seeds it flipped to success
   - Target skill file: localize.md | grasp.md | transport.md | manipulation.md
   If nothing generalizes beyond this task, write "none".>

  ## Refuted hypotheses (REQUIRED — write "none" only if you refuted nothing)
  <one bullet per cause you raised and then ruled out, with: Trigger (the symptom that
   suggested it), Why it looked right, what Distinguished it, and the Evidence that
   killed it. A refuted hypothesis is a finding: the previous campaign discarded all
   of them, so later tasks re-paid for the same wrong turns.>

  ## Causes considered and NOT ruled out (REQUIRED — write "none" only if none remain)
  <one bullet per cause still standing when you stopped, and what evidence would
   settle it. An unresolved cause recorded is cheap; an unnamed one is what makes the
   next agent repeat your mistake.>

  ## Blocked seeds
  <seed → root cause, or "none">

---

## What to Return

You are done after Step 5. Do NOT run seeds 1–50 or any validation script. Return exactly this summary — the coordinator parses the `GPU:` line to schedule your GPU's next job:

```
SUITE: <suite>
TASK: <task>
GPU: <N>

Stage 1 Results:
  Seeds passed initially: <list>
  Seeds fixed: <list of seed numbers>
  Seeds blocked: <list + root cause for each>
  fix_code.py written: yes/no
  findings.md written: yes/no

Key findings:
  <1–3 bullet points about what the failure root cause was and what fixed it>
```

<!-- ==================== TEMPLATE END ==================== -->
