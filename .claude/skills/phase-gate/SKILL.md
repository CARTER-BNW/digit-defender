---
name: phase-gate
description: Verify the current phase's checkpoints in docs/PHASES.md by actually running them, then open the next phase
---

# Phase gate

## 1. Identify the current phase
Read docs/PHASES.md — the phase marked `← CURRENT`.

## 2. Verify every checkpoint
For each checkbox: don't trust memory or code reading — **run the verification** (execute the script, run the tests, open the app). A checkpoint that can't be demonstrated right now stays unchecked.

## 3. Report
List each checkpoint with pass/fail and the evidence (command output, test summary). If anything fails, stop here — the phase stays open. Fix or report to John.

## 4. Advance
Only if all checkpoints pass: tick the remaining boxes, move the `← CURRENT` marker to the next phase, and add a STATUS.md entry noting the gate passed and what evidence was seen.
