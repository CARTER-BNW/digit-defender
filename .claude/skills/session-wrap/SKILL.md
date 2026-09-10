---
name: session-wrap
description: End-of-session wrap — update STATUS.md and HANDOFF.md, check phase progress, commit and push
---

# Session wrap

## 1. Update STATUS.md
Add a new `## vN (date): title` entry at the top (reverse-chronological). One bullet per meaningful change, naming the files touched. Note anything left open. Bump the `_Last updated_` header line.

## 2. Refresh HANDOFF.md
Rewrite **Live state** and **Next actions** so a fresh session can continue without re-reading history. Verify the health-check commands still work; update them if the app changed.

## 3. Check phase progress
Open docs/PHASES.md. If any checkpoint was completed this session, tick it — but only if it was actually verified by running the thing, not just written.

## 4. Log gotchas
If any trap was hit this session and isn't in docs/GOTCHAS.md yet, add it now (Symptom / Cause / Fix).

## 5. Commit and push
```powershell
git add -A
git status   # confirm nothing unexpected (no data dumps, logs, secrets)
git commit -m "<summary>"
git push
```
