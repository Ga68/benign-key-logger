## Goal

Fix the dropped-keystroke bug from issue `#15`, where a mismatched shifted/unshifted key-up sequence could leave a stale capital or shifted symbol in `keys_currently_down` and cause a later press of that same key to be ignored.

## Files Changed And Why

### `key_logger.py`

Adds:

- a map of common shifted/unshifted symbol pairs
- a helper to compute shifted/unshifted equivalents for a key
- a reconciliation step in `key_up()` that clears a lingering equivalent key before treating the event as an ordinary unpaired key-up

## Behavior Changes

- In “hasty shift” sequences such as `shift-down`, `A-down`, `shift-up`, `a-up`, the final `a-up` now clears the lingering `A` entry instead of leaving it stuck in `keys_currently_down`.
- The same reconciliation also works for common shifted symbols such as `!` / `1`.
- Later capitalized or shifted presses of that same key are no longer lost because of the stale entry.

## Approach

Implement the narrow bug fix requested in the issue thread rather than changing the project’s overall logging model:

- when a key-up arrives without a direct match
- check whether the shifted or unshifted equivalent is still held
- if so, clear that equivalent and treat the mismatch as reconciled

This preserves the current “log inserted character/combo” design while fixing the stale-held-key bug.

## Alternatives Considered

- Rework the whole logger to track physical key plus modifier separately. Rejected for this commit because that is a larger feature/model change discussed in the issue comments, not the minimal fix for the dropped-keystroke bug itself.
- Leave cleanup to the existing garbage-collection threshold. Rejected because it allows real keystrokes to be lost before cleanup happens.

## Assumptions

- The main bug is the stale held-key entry, not the broader choice of logging inserted characters rather than raw physical key presses.
- Common shifted ASCII symbol pairs are enough to cover the practical cases discussed in the issue thread.

## Shortcuts Or Tradeoffs

The symbol reconciliation uses an explicit map of common shifted/unshifted ASCII pairs rather than attempting a platform-specific keyboard-layout abstraction.

## Known Limitations

- This does not implement the broader feature request to always log physical keys separately from modifiers.
- Non-ASCII or layout-specific shifted pairs are not generalized beyond the common ASCII symbols.

## Key Decisions

- Fix the stale-held-key bug in `key_up()` rather than redesigning the whole logging model.
- Reconcile letters and common shifted ASCII symbol pairs.
- Only suppress the warning when a real shifted/unshifted equivalent was successfully reconciled.
