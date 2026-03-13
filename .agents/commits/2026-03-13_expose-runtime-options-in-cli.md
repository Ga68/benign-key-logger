## Goal

Expose the main runtime configuration switches through the command line so users no longer have to edit the script to choose storage backends, file names, full-event logging, or WAL behavior.

## Files Changed And Why

### `key_logger.py`

Expands the existing `argparse` CLI to cover the operational settings that were still buried as module-level constants:

- SQLite on/off
- plaintext file logging on/off
- full event logging on/off
- stdout echo
- SQLite filename
- text log filename
- WAL on/off

It also validates that `--full-events` is only used when SQLite logging is enabled.

### `README.md`

Updates the usage documentation so the project page reflects the real public interface, points users to `--help`, and provides common command examples instead of telling them to edit the script for routine configuration.

## Behavior Changes

- Users can now choose the main output modes and filenames at invocation time.
- `python3 key_logger.py --help` now documents the full operational CLI.
- Invalid combinations such as `--full-events --no-sqlite` fail immediately with a parser error instead of silently producing confusing behavior.

## Approach

Promote only the operational knobs to the CLI and leave lower-level tuning values, such as batching thresholds and key remapping internals, as code settings. This keeps the command surface useful without turning a small script into a fully generalized configuration system.

## Alternatives Considered

- Continue requiring source edits for all configuration. Rejected because the operational options are common enough that hiding them in code is unnecessary friction.
- Expose every setting through the CLI, including batching thresholds and internal key-processing constants. Rejected because that would enlarge the interface without much day-to-day value for typical use.
- Move everything to environment variables or a config file. Rejected because the project already has a simple CLI and this change can stay much smaller by extending it.

## Assumptions

- The most useful public options are the storage/output choices and file paths.
- Advanced tuning such as remapping and batching thresholds can remain source-level configuration for now.

## Shortcuts Or Tradeoffs

The implementation keeps the current module-level constants as defaults and uses CLI parsing to override them at runtime rather than restructuring the script around a dedicated configuration object.

## Known Limitations

- Low-level tuning knobs are still code-only.
- The CLI remains intentionally minimal and does not include configuration-file support.

## Key Decisions

- Promote the main runtime switches to CLI flags.
- Keep `--help` as the primary discoverability surface.
- Add argument validation for `--full-events` without SQLite.
- Update the README examples to match the CLI-driven workflow.
