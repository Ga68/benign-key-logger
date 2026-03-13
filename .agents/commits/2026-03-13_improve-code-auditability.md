## Goal

Make the implementation easier to inspect for benignness and correctness by improving the internal legibility of `key_logger.py` without changing the public CLI or runtime behavior.

## Files Changed And Why

### `key_logger.py`

Restructures the SQLite setup path into smaller named helpers and moves the long SQL view definitions into top-level constants. It also adds short explanatory comments around the `Config` and `KeyLoggerApp` roles so a reader can understand the object split quickly.

## Behavior Changes

This change is intended to be readability-only. The public behavior remains the same:

- same CLI flags and defaults
- same batching policy
- same WAL behavior
- same permission hardening
- same shutdown behavior
- same key handling and modifier logic

## Approach

Reduce the amount of code a reviewer has to hold in their head at once:

- extract long SQL view bodies into named constants
- split SQLite setup into distinct steps with explicit method names
- add small comments that explain the config/runtime object roles

This keeps the single-file design but makes the trust-relevant pieces easier to scan.

## Alternatives Considered

- Leave the file as-is after the runtime-state refactor. Rejected because the SQLite setup path was still too dense for the project’s “easy to audit” goal.
- Split into multiple Python files immediately. Rejected because one-file inspectability is still valuable for this repository.

## Assumptions

- A single file is still preferred as long as the internal sections are explicit enough.
- Named steps such as `create_sqlite_tables()` and `create_sqlite_views()` are easier for auditors to reason about than one large setup method.

## Shortcuts Or Tradeoffs

The SQL view definitions are still embedded as strings in the same file rather than moved into separate `.sql` assets. That preserves the one-file audit path at the cost of some file length.

## Known Limitations

- The file is still fairly long.
- There is still no automated test suite.
- Some advanced tuning constants remain top-level and undocumented in the CLI.

## Key Decisions

- Keep the single-file layout.
- Split the dense SQLite setup flow into clearly named helpers.
- Move long SQL into named constants rather than leaving it embedded in the middle of runtime logic.
- Add minimal comments only where they materially help a code auditor orient themselves.
