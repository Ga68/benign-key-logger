## Goal

Add a `--debug` CLI flag that exposes the existing internal debug logging without changing the keystroke-echo privacy behavior.

## Files Changed And Why

### `key_logger.py`

Adds a `debug` field to `Config`, introduces a `--debug` flag in the CLI parser, and raises the root logger level to `DEBUG` at runtime when that flag is enabled. The startup summary also now includes whether debug mode is on.

### `README.md`

Documents what `--debug` is for, explains that it is separate from `--stdout`, and adds example invocations plus a note in the audit checklist.

## Behavior Changes

- `--debug` enables internal debug logging such as remapping, key state transitions, batching, and permission-related messages.
- `--debug` does not imply `--stdout`; keystroke echo remains a separate opt-in behavior.
- The startup summary now reports whether debug logging is active.

## Approach

Keep the feature intentionally small by reusing the debug logging statements that already exist in the codebase. The flag only changes the logging level and does not introduce a separate debugging subsystem.

## Alternatives Considered

- Fold debug behavior into `--stdout`. Rejected because internal diagnostics and keystroke echo have different privacy implications and should remain separate.
- Add multiple debug levels or categories. Rejected because the existing logger-level split is sufficient for this tool.

## Assumptions

- Users mainly want `--debug` to inspect internal behavior without dumping typed content to the terminal.

## Shortcuts Or Tradeoffs

The implementation sets the root logger level directly at startup rather than introducing a custom logger hierarchy.

## Known Limitations

- Debug logging still depends on the existing log messages already present in the code; this commit does not add new categories of instrumentation.

## Key Decisions

- Add `--debug` as a simple logger-level switch.
- Keep it separate from `--stdout`.
- Document the distinction clearly in the README and startup summary.
