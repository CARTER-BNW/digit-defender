# Gotchas

Format: Symptom / Cause / Fix. Add an entry the moment a trap is found (`/gotcha`).

## hash() of tuples with strings is salted per process
- **Symptom:** "deterministic" generation that seeds random.Random(hash((seed, cx, cy, "dep"))) differs between runs.
- **Cause:** Python salts str hashes per process (PYTHONHASHSEED), so hash() of any tuple containing a string changes every launch.
- **Fix:** seed with a string: random.Random(f"{seed}:{cx}:{cy}:dep") (str seeds go through sha512, stable everywhere). Used in world/generator.py and sim/nests.py.

## Cached pygame Fonts die across pygame.quit()/init()
- **Symptom:** pygame.error: Invalid font (font module quit since font created) in the second test that builds a Game.
- **Cause:** render/numbers.py LRU-caches Font objects; tests call pygame.quit() between Games, invalidating cached fonts.
- **Fix:** Renderer.__init__ calls numbers.reset() (clears both caches) right after pygame.font.init().

## Stale hover tile regenerates chunks that streaming just dropped
- **Symptom:** after flying 200 chunks away, chunk (0,0) is still loaded every frame.
- **Cause:** HUD hover info and the ghost preview query terrain at game.hover_tile; if the mouse never moved, that tile is far off-screen and get_tile() regenerates its chunk each frame right after update() unloads it.
- **Fix:** Game.update() recomputes hover_tile from the current mouse position every frame, so hover queries always land inside the visible (kept) area.

## Backslash-n inside a Bash heredoc patch script becomes a real newline
- **Symptom:** game.py stopped importing: SyntaxError "unterminated string literal" at a line that should read fh.write(... + "\n").
- **Cause:** the Bash tool layer unescapes backslashes before bash sees the (quoted) heredoc, so a Python patch script containing an escaped newline wrote a literal line break into the source.
- **Fix:** never route escape sequences through Bash heredocs; use the Edit/Write tools for any text containing backslashes. Always run the test suite (which imports game.py) before committing.

## Belt items are 3-field lists, not (value, progress) pairs
- **Symptom:** `ValueError: too many values to unpack` in code doing `for v, p in belt.items`.
- **Cause:** since STATUS v5 every item is `[value, progress, entry_rel]`; the third field is render-only (corner animation) and the sim never reads it, but pair-unpacking anywhere breaks.
- **Fix:** index (`it[0]`, `it[1]`) or unpack with `v, p, *_`. `Belt.to_dict/from_dict` accept both shapes (old two-field saves load with entry BACK); tests that hand-append items may still append pairs.

## A short scripted run shows an "empty" belt line that is actually fine
- **Symptom:** a verification script places a miner + belts + bridge, runs 60 ticks, and the belts past the bridge carry nothing (looks like a broken link).
- **Cause:** a new miner's timer starts at the BASE period (40 ticks) even if `invested` is raised right after placement, and level-1 belts move 1 tile/s (0.05 tiles/tick), so nothing reaches tile 5 of a line inside 60 ticks.
- **Fix:** run 200+ ticks before judging a line (or set `miner.timer = 0`); check `stats["mined"]` and the items on the FIRST belt before suspecting the links.

## A second Combat on the same Factory silently takes over its ticks
- **Symptom:** in a test, a unit stops moving right after a save round-trip check that built `Combat(f, ..., units=records)` on the same factory.
- **Cause:** `Combat.__init__` sets `factory.combat = self`; `Factory.tick()` ticks whatever `combat` points at, so the original Combat (and its units) is no longer simulated.
- **Fix:** restore `f.combat = c` after building a throwaway Combat, or build the twin on its own Factory (tests/test_combat.py does the former).

## Long Bash heredocs silently fail in this tool
- **Symptom:** "unexpected EOF while looking for matching quote" from a multi-file heredoc command; nothing written.
- **Cause:** suspected tool-side length limit (~8 KB) on a single Bash command; large heredocs get cut mid-line.
- **Fix:** write big files with the Write tool; keep Bash heredocs short (patch scripts, small files).

