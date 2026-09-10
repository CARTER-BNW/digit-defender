# Digit Defender

## Purpose
Digit Defender - a Python game
Scope not yet confirmed — Phase 0 checkpoint in @docs/PHASES.md.

## Stack & tooling
- Python 3.12 (Windows / PowerShell)
- Deps kept minimal — see `requirements.txt`

## Commands
- Deps: `pip install -r requirements.txt`
- Run: `python app.py` (once it exists)
- Tests: `python -m pytest`

## Architecture map
No code yet. Add one line per file as files are created, stating what that file owns.


## Project rules
- Discover a trap → log it in @docs/GOTCHAS.md immediately (`/gotcha`).
- Phase gates: don't start the next phase until the current phase's checkpoints are verified (`/phase-gate`).
- End of session: new vN entry in @STATUS.md, refresh HANDOFF.md, commit & push (`/session-wrap`).
- Never commit data dumps, logs, or secrets — .gitignore covers these; keep it that way.

## Pointers
- @HANDOFF.md — read first in a new session: live state + next actions
- @STATUS.md — reverse-chron session log
- @docs/PHASES.md — roadmap with phase checkpoints
- @docs/GOTCHAS.md — known traps
