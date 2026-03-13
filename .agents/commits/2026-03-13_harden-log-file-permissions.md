## Goal

Reduce local disclosure risk by ensuring the logger stores sensitive keystroke data in owner-only files rather than relying on the ambient process umask.

## Files Changed And Why

### `key_logger.py`

Adds file-permission helpers that create log files with `0600`, tighten existing files if they are more permissive, and apply the same tightening to common SQLite sidecar files (`-journal`, `-wal`, and `-shm`) when they exist.

### `README.md`

Documents that the logger now enforces owner-only permissions for local output files and explains why the stored data should be treated as sensitive even though it never leaves the machine.

## Behavior Changes

- New text log files are created with owner-only permissions.
- New SQLite database files are created with owner-only permissions before connecting.
- Existing log files with broader permissions are tightened to `0600` and a warning is emitted.
- After SQLite setup and commits, the logger also tightens known SQLite sidecar files if they are present.

## Approach

Introduce small permission helpers near the top of the module and reuse them in the text log and SQLite write paths. The SQLite setup path pre-creates the database file with `0600` before opening it through `sqlite3.connect()`, then re-checks the main database file and common sidecars after setup and after commits.

## Alternatives Considered

- Rely only on a README warning about `umask`. Rejected because the safer behavior can be enforced directly and cheaply in code.
- Chmod only the main SQLite file once during setup. Rejected because SQLite may create sidecar files later during write activity.
- Tighten permissions only when files are newly created. Rejected because existing files may already be too permissive and should not be silently trusted.

## Assumptions

- Owner-only (`0600`) is the right default for all persisted keystroke output.
- Warning when tightening an existing file is preferable to silently changing it.

## Shortcuts Or Tradeoffs

The implementation checks and potentially chmods the SQLite file set after commits, which adds a small amount of filesystem overhead in exchange for straightforward coverage of sidecar creation.

## Known Limitations

- This commit does not batch SQLite commits or change durability behavior.
- The logger still depends on the host environment for broader filesystem protections such as encrypted disks and backup policies.

## Key Decisions

- Enforce `0600` in code instead of documenting it only.
- Tighten existing files instead of merely warning.
- Include SQLite sidecar files in the hardening pass because they can contain the same sensitive data.
