## Goal

Correct modifier tracking when both left and right variants of the same modifier are pressed so that releasing one physical key does not clear the logical modifier state too early.

## Files Changed And Why

### `key_logger.py`

Adds a small canonicalization helper and changes preprocessing/logging responsibilities so physical keys remain distinct in `keys_currently_down` while emitted log entries continue to normalize left/right modifiers to a single logical name.

## Behavior Changes

- `preprocess()` still applies remapping for ignore checks and output normalization, but no longer remaps the key object before handing it to `key_down()` or `key_up()`.
- `keys_currently_down` now preserves separate physical left/right modifier entries, which prevents a release of one side from incorrectly clearing the other.
- `log()` canonicalizes modifiers only when building the output string and de-duplicates repeated logical modifiers so pressing both Control keys still logs as `<ctrl> + key`.
- `full_log()` now records canonicalized key names consistently with the main log output.

## Approach

Move canonicalization to the edges of the system:

- keep raw event identity for state transitions
- use canonicalized values for ignore matching and log formatting

This preserves the original human-readable output while fixing the state machine.

## Alternatives Considered

- Keep the old preprocessing flow and add reference counts per remapped modifier. This would have been more invasive and harder to reason about than preserving the original physical key identity.
- Stop remapping entirely. That would fix the bug but would regress the intended output format by exposing left/right-specific modifier names.

## What Was Tried And Did Not Work

The first pass fixed the state bug but caused duplicate logical modifier output when both physical modifiers were held at once, for example `<ctrl> + <ctrl> + a`. The final version de-duplicates canonicalized modifiers during log formatting.

## Assumptions

- The intended output remains logical modifiers (`<ctrl>`, `<shift>`, `<cmd>`) rather than left/right-specific names.
- Ignored-key configuration should continue to operate on canonicalized keys.

## Shortcuts Or Tradeoffs

No automated test suite was added because the repository does not currently contain one. Verification was done with focused runtime probes in the project virtualenv using `pynput` objects.

## Known Limitations

- The repository still lacks repeatable automated tests for keyboard-state edge cases.
- The logger still has separate privacy and performance concerns not addressed by this commit.

## Key Decisions

- Preserve raw physical keys for state.
- Canonicalize only for ignore checks and emitted output.
- De-duplicate canonical modifiers at formatting time to keep logs stable and compact.
