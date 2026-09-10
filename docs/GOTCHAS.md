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

## Long Bash heredocs silently fail in this tool
- **Symptom:** "unexpected EOF while looking for matching quote" from a multi-file heredoc command; nothing written.
- **Cause:** suspected tool-side length limit (~8 KB) on a single Bash command; large heredocs get cut mid-line.
- **Fix:** write big files with the Write tool; keep Bash heredocs short (patch scripts, small files).

