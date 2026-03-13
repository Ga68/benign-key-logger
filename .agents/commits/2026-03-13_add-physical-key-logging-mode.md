## Goal

Implement the broader feature request from the issue `#15` discussion by adding an opt-in mode that logs physical key plus modifiers instead of the resulting character, while keeping the current character/result-oriented behavior as the default.

## Files Changed And Why

### `key_logger.py`

Adds:

- a `log_physical_keys` field to `Config`
- a `--physical-keys` CLI flag
- formatting helpers that normalize shifted characters back to their physical base key when the new mode is enabled

The main log path now supports two modes:

- default mode: log the resulting character/combo
- physical-key mode: log the base key plus any active modifiers

### `README.md`

Documents the new mode, explains how it differs from the default behavior, and adds example commands plus an audit-checklist note.

## Behavior Changes

- Default behavior is unchanged: `Shift+a` logs as `A`, and `Shift+1` logs as `!`.
- With `--physical-keys`, `Shift+a` logs as `<shift> + a`, and `Shift+1` logs as `<shift> + 1`.
- The startup summary now reports whether physical-key mode is active.

## Approach

Implement the feature as a formatting-mode switch rather than a full redesign of key tracking:

- keep the same underlying event/state model
- reuse the existing modifier tracking
- only change how the final log entry string is constructed when the mode is enabled

This keeps the feature smaller and preserves the current default semantics for existing users.

## Alternatives Considered

- Replace the default logging model entirely. Rejected because the repository currently documents and expects the result-oriented behavior.
- Redesign the whole logger around raw physical key tracking internally. Rejected because the user asked for a CLI option, not a full internal rewrite.

## Assumptions

- Users who care about keyboard mechanics more than inserted characters will prefer the physical-key mode.
- Existing users should not have their historical/default logging model changed implicitly.

## Shortcuts Or Tradeoffs

The implementation changes only the final formatting path. It does not redesign key-state storage around a separate physical-key abstraction.

## Known Limitations

- The alternate mode is focused on common shifted ASCII keys and alphabetic case, not a full keyboard-layout abstraction.
- Full-event logging still records the event key representation rather than introducing a second physical/raw schema.

## Key Decisions

- Make physical-key logging opt-in through `--physical-keys`.
- Keep the current result-oriented logging as the default.
- Implement the feature at formatting time rather than through a broader internal model rewrite.
