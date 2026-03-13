## Goal

Stop echoing captured keystrokes to stdout by default while preserving an explicit way to opt into the old live-terminal behavior.

## Files Changed And Why

### `key_logger.py`

Adds a small command-line interface using `argparse` and gates key echo behind a `--stdout` flag. The core logging path still records keystrokes to the configured sinks, but it no longer writes them to terminal output unless the user explicitly requests that behavior.

### `README.md`

Updates the documentation to explain that terminal scrollback is not reliably ephemeral, documents the safer default behavior, and shows how to re-enable live terminal echo with `--stdout`.

## Behavior Changes

- Running `python3 key_logger.py` no longer prints captured keystrokes to stdout.
- Running `python3 key_logger.py --stdout` restores the prior behavior of printing captured keys to the terminal while the logger runs.
- Operational log messages such as startup still use the Python logging module as before.

## Approach

Use a CLI flag rather than another module-level setting so the privacy-sensitive behavior is an explicit runtime choice. The implementation keeps the existing logging infrastructure and only gates the specific key-echo line in `log()`.

## Alternatives Considered

- A new module-level constant for stdout echo. Rejected because it keeps a privacy-sensitive switch buried in the source rather than making it an explicit invocation-time choice.
- Removing stdout echo entirely. Rejected because the previous behavior is still useful for transparency and debugging when the user deliberately wants it.

## Assumptions

- Users who want to observe the live key stream are comfortable opting in per run.
- Existing users relying on default stdout echo can adapt to `--stdout` without needing a compatibility shim.

## Shortcuts Or Tradeoffs

The flag is intentionally minimal and does not introduce broader CLI configuration for SQLite or file sinks. That keeps the change tightly scoped to the privacy issue being addressed.

## Known Limitations

- This commit does not harden file permissions for SQLite or text log output.
- This commit does not address SQLite write batching or shutdown flushing.

## Key Decisions

- Make live key echo opt-in instead of default.
- Expose the behavior through `--stdout`.
- Document the privacy rationale directly in the README so the changed default is understandable from the project page.
