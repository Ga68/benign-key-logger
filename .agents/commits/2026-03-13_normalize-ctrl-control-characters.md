## Goal

Fix Windows-style Ctrl-letter logging so entries in `key_log` and `key_counts` remain human-readable instead of containing invisible ASCII control characters.

## Files Changed And Why

### `key_logger.py`

Adds a small helper that recognizes control-character key values when Control is held and converts them back to the corresponding lowercase letter before the log entry string is built.

## Behavior Changes

- Combinations such as Ctrl+A, Ctrl+C, Ctrl+V, and Ctrl+Z now log as `<ctrl> + a`, `<ctrl> + c`, `<ctrl> + v`, and `<ctrl> + z` even when the incoming `pynput` key object carries an ASCII control character like `\\x03`.
- This keeps `key_log` and the derived `key_counts` view readable in SQLite tools that would otherwise show many visually identical `<ctrl> + ` entries with hidden trailing bytes.

## Approach

Normalize only in the formatting path for the main log entry:

- detect that Control is among the active modifiers
- inspect the formatted key value
- if it is a single ASCII control character in the range 1-26, map it back to `a`-`z`

This keeps the fix tightly scoped to the user-facing logging problem reported in issue `#12`.

## Alternatives Considered

- Change broader key handling or remapping logic. Rejected because the reported problem is in the logged representation, not the modifier-state machine.
- Normalize all non-printable characters unconditionally. Rejected because the issue is specifically about Ctrl-modified alphabetic shortcuts, and a broader rewrite would risk changing unrelated key behavior.

## Assumptions

- The hidden-character behavior reported in issue `#12` is caused by platforms where `pynput` surfaces Ctrl-letter combinations as ASCII control characters.

## Shortcuts Or Tradeoffs

The normalization uses the already-formatted key string to detect the control-character range rather than introducing a deeper platform-specific keycode abstraction.

## Known Limitations

- The fix is targeted to Ctrl-letter control characters and does not attempt to reinterpret arbitrary non-printable key values.

## Key Decisions

- Keep the fix small and formatting-focused.
- Normalize only when Control is active.
- Favor readable logged output over preserving the raw control-byte representation in the main key log.
