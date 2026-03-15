## Goal

Implement the two concrete logging improvements that remained clearly in-scope after the conversation review:

- optional plaintext file timestamps
- optional left/right modifier distinction

At the same time, explicitly avoid folding in the larger OS-overhaul ideas that were discussed later in the thread:

- Linux `evdev` backend work
- hotplug rescanning
- cross-platform backend/event-model refactors
- layout-aware translation across OSes

This commit is intentionally scoped to user-facing logging behavior that can be added cleanly on top of the existing `pynput`-based implementation while keeping current defaults intact.

## Files Changed And Why

### `key_logger.py`

Adds two new opt-in configuration flags and threads them through the existing logging paths:

- `--file-timestamps`
- `--modifier-sides`

Main behavior changes in the code:

- the main `log()` path now captures a single UTC timestamp per logged keystroke and reuses it for SQLite plus optional plaintext file output
- plaintext file logging can now prepend that timestamp when `--file-timestamps` is enabled
- key canonicalization now accepts a `distinguish_modifier_sides` option so left/right modifier remapping can be disabled when requested
- the main log path, full-event SQLite log path, preprocessing path, and startup summary all honor the new modifier-side option
- the Ctrl/Shift normalization helpers still treat left/right variants as the same underlying modifier for formatting behavior, so enabling side distinction does not accidentally break existing shortcut or shifted-symbol normalization

### `README.md`

Documents both features, adds example invocations, and updates the audit checklist to make it clear that both behaviors are opt-in.

## Behavior Changes

- Default behavior is preserved.
- With `--file-timestamps`, plaintext file entries are written as `UTC_ISO_TIMESTAMP,log_entry`.
- With `--modifier-sides`, left/right variants of Shift, Control, Alt, and Command remain distinct in the logged output instead of being remapped together.
- When `--modifier-sides` is off, the logger preserves the historical remapped behavior.
- Startup logging now reports the active `file_timestamps` and `modifier_sides` settings.

## Approach

Keep both changes as shallow extensions of the existing implementation:

- do not redesign the input backend
- do not change the default log format unexpectedly
- do not change the default modifier-remapping behavior

This keeps the commit aligned with the parts of the conversation that were concrete and requested, while leaving the larger cross-platform architecture discussion for later work.

## Alternatives Considered

### Change plaintext file logging to always include timestamps

Rejected because the conversation had already raised the concern that stable behavior and file format changes should be explicit. Making file timestamps opt-in avoids silently changing existing plaintext logs.

### Make left/right modifier distinction the new default

Rejected because the user explicitly asked for this as an optional CLI flag while keeping the default behavior the same.

### Fold in `evdev` or backend/interface work here

Rejected because the user later clarified that those ideas belonged in the larger OS-specific discussion rather than in the concrete implementation set for this round.

## Assumptions

- Existing users may depend on the current plaintext log format and current modifier-remapping behavior.
- Users who need better plaintext analysis or more precise modifier auditing are willing to opt into those behaviors explicitly.

## Shortcuts Or Tradeoffs

- Plaintext timestamps use a simple comma separator rather than introducing a richer structured format.
- Modifier-side distinction is limited to the existing remapped modifier set; it does not attempt a broader key-identity redesign.

## Known Limitations

- The logger still relies on `pynput`; broader OS-specific capture and translation concerns remain deferred.
- Full-event logging still stores one key string rather than separate raw/logical/physical columns.

## Key Decisions

- Keep both new behaviors opt-in.
- Preserve the historical default remapping and plaintext format.
- Defer backend/OS-overhaul work to a later discussion and implementation sequence.
