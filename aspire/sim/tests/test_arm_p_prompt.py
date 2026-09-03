# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The Arm P prompt is generated, never hand-edited: it must always equal what
`make_arm_p_prompt.py` produces from the stock fix-loop prompt, and every one of
its anchors must still match the stock prompt exactly once."""

import subprocess
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]


def test_arm_p_is_in_sync_with_the_stock_prompt():
    r = subprocess.run(
        [sys.executable, str(SIM / "scripts/libero/make_arm_p_prompt.py"), "--check"],
        capture_output=True, text=True, cwd=SIM,
    )
    assert r.returncode == 0, f"Arm P out of sync with the stock prompt:\n{r.stdout}{r.stderr}"


def test_arm_p_adds_only_process_rules():
    stock = (SIM / ".claude/libero/fix-loop/subagent-prompt.md").read_text()
    arm_p = (SIM / ".claude/libero/process/subagent-prompt.md").read_text()
    # Every stock line survives except the ones the five edits deliberately replace.
    stock_lines = set(stock.splitlines())
    arm_p_lines = set(arm_p.splitlines())
    dropped = [l for l in stock_lines - arm_p_lines if l.strip()]
    assert len(dropped) <= 2, dropped
    assert "Refuted hypotheses" in arm_p
    assert "attempt_" in arm_p
