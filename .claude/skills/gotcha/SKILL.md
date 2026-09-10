---
name: gotcha
description: Log a newly discovered trap into docs/GOTCHAS.md in Symptom/Cause/Fix format
---

# Log a gotcha

## 1. Confirm it's new
Read docs/GOTCHAS.md — if the trap is already listed, update that entry instead of duplicating.

## 2. Write the entry
Append in this exact shape:

```markdown
## <short title of the trap>
- **Symptom:** what you observed
- **Cause:** the actual root cause (verified, not guessed)
- **Fix:** what prevents or resolves it
```

## 3. Keep it honest
Only log root causes that were verified. If the cause is still a hypothesis, say so in the entry ("suspected: …") so a future session doesn't treat it as settled.
