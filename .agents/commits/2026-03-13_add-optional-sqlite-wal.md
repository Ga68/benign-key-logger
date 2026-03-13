## Goal

Add optional SQLite WAL support for users who want to inspect the database while the logger is actively writing to it, without changing the default file model for everyone else.

## Files Changed And Why

### `key_logger.py`

Adds an `ENABLE_SQLITE_WAL` setting and applies `PRAGMA journal_mode=WAL` during SQLite setup when the setting is enabled.

### `README.md`

Documents the new setting, explains that it is disabled by default, and describes the concurrency benefit and expected sidecar files.

## Behavior Changes

- Default behavior is unchanged: SQLite continues to use the standard journal mode unless explicitly configured otherwise.
- When `ENABLE_SQLITE_WAL = True`, the logger enables SQLite write-ahead logging during setup.
- WAL mode may create `-wal` and `-shm` sidecar files while the database is active.

## Approach

Keep WAL as a single module-level setting rather than broadening the CLI surface. This keeps the change small and lets users opt into WAL only if their workflow benefits from concurrent reads during logging.

## Alternatives Considered

- Enable WAL by default. Rejected because the project currently prefers the simplest file model unless the user specifically needs better concurrent inspection behavior.
- Leave WAL out entirely. Rejected because it is a useful option for database-browser workflows and inexpensive to support.

## Assumptions

- Most users of this repo still prefer the simpler default file layout.
- Users enabling WAL are comfortable with the presence of sidecar files while the database is active.

## Shortcuts Or Tradeoffs

The implementation only adds a module-level setting and README guidance. It does not add CLI control or runtime auto-detection of external readers.

## Known Limitations

- This commit does not change checkpoint behavior beyond SQLite defaults.
- WAL mode remains opt-in and must be toggled by editing the script.

## Key Decisions

- Keep WAL off by default.
- Document the “inspect while logging” use case directly in the README.
- Reuse the existing SQLite sidecar permission hardening rather than adding WAL-specific file handling paths.
