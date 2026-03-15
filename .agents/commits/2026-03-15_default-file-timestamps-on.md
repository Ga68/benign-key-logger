## Goal

Follow up on the previous plaintext timestamp work by making file timestamps the default behavior instead of opt-in.

The conversation explicitly changed direction after the prior commit: the user decided that plaintext file timestamps should be on by default. This commit applies that narrower policy change without revisiting the broader logging-scope decisions from the previous step.

## Files Changed And Why

### `key_logger.py`

Updates the plaintext timestamp default and preserves an explicit way to disable it:

- change `DEFAULT_TIMESTAMP_FILE_LOGS` from `False` to `True`
- add `--no-file-timestamps` so users can still get the older bare-entry plaintext format
- set the parser default for `file_timestamps` explicitly so help/default reporting matches runtime behavior

### `README.md`

Updates the user-facing docs so they match the new default:

- plaintext file timestamps are described as on by default
- examples now use `--file` for the timestamped case
- `--no-file-timestamps` is documented as the way to restore the old format
- the audit checklist now describes timestamps as default-on rather than opt-in

## Behavior Changes

- Plaintext file logging now prepends UTC timestamps by default whenever `--file` is enabled.
- Users who want bare plaintext entries can opt out with `--no-file-timestamps`.
- The CLI default/help behavior now matches the new runtime default.

## Approach

Keep the change intentionally small:

- do not alter the timestamp format
- do not revisit the modifier-side work
- do not revisit any deferred OS-overhaul work

This is a policy/default change layered directly on top of the prior implementation.

## Alternatives Considered

### Leave timestamps opt-in

Rejected because the user explicitly asked to default them on.

### Remove the opt-out path entirely

Rejected because preserving `--no-file-timestamps` keeps the older plaintext format available and avoids making the file output behavior irreversible from the CLI.

## Assumptions

- The timestamped plaintext format is now considered the more useful default.
- Some users may still want the previous simpler format, which is why the opt-out flag remains.

## Shortcuts Or Tradeoffs

- The commit updates only the default and docs; it does not try to rename or reorganize the existing timestamp flag pair.

## Known Limitations

- The project still imports `pynput` at startup, so CLI runtime verification remains environment-dependent when that dependency is missing.

## Key Decisions

- Make plaintext timestamps default-on.
- Keep `--no-file-timestamps` as the explicit escape hatch.
