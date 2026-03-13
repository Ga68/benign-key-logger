## Goal

Finish the SQLite cleanup path so clean process exits explicitly close the database connection instead of only flushing pending writes.

## Files Changed And Why

### `key_logger.py`

Adds explicit `db_connection` and `db_cursor` globals initialized to `None`, introduces a `close_sqlite_connection()` helper, and registers that helper with `atexit` instead of registering a flush-only lambda.

## Behavior Changes

- Clean shutdown now forces a final SQLite flush and then closes the database connection.
- The connection and cursor globals are reset to `None` after close, making the lifecycle state explicit and easier to test.

## Approach

Keep the existing shutdown hook structure but replace the write-flush lambda with a dedicated close helper that:

- no-ops if SQLite was never set up
- forces a final commit for any pending batched writes
- closes the connection
- clears the connection globals

## Alternatives Considered

- Leave cleanup to interpreter teardown after the `atexit` flush. Rejected because explicit close makes connection lifecycle clearer and more predictable, especially with WAL and batched writes.
- Add a broader teardown framework. Rejected because the immediate issue is narrow and can be fixed cleanly with a small dedicated helper.

## Assumptions

- The logger still uses module-level SQLite state for now, so an explicit close helper is the correct incremental fix.

## Shortcuts Or Tradeoffs

The change keeps the current global-state structure rather than doing the larger refactor into explicit config/runtime objects discussed separately.

## Known Limitations

- This commit does not refactor the broader global-state design.
- Abrupt termination such as `kill -9` still bypasses `atexit`.

## Key Decisions

- Treat SQLite close as part of normal shutdown, not just best-effort interpreter cleanup.
- Flush pending batched writes before closing.
- Clear the connection globals after close so post-close state is unambiguous.
