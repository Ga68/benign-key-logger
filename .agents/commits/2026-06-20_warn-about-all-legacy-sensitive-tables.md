## Goal

Make the counts-only privacy default honest for users with *existing* databases.
The startup legacy-data warning previously only flagged a leftover `key_log`
table, but two other sensitive sinks can sit in the same file and go unmentioned:
`full_key_log` (exact key up/down events + timestamps, from a prior
`--full-events` run) and `trigram_counts_agg` (higher reconstruction risk than
the default bigrams, from a prior `--trigrams` run). Reopening such a DB under
the aggregate defaults leaves that exact/higher-risk history on disk silently.
Warn about all three. (Addresses upstream PR review feedback.)

## Files Changed And Why

### `key_logger.py`

- Replaced `warn_if_legacy_key_log_table()` with `warn_about_legacy_sensitive_tables()`,
  which sweeps a small table of `(table_name, is_intentional_flag, what_it_leaks)`:
  `key_log` ↔ `send_raw_events_to_sqlite`, `full_key_log` ↔
  `send_all_events_to_sqlite`, `trigram_counts_agg` ↔ `send_trigram_counts`. For
  each table whose opt-in flag is OFF and which exists in `sqlite_master`, it logs
  a warning naming the table, what it leaks, and the exact `DROP TABLE <name>;` to
  remove it. No migration, no deletion — the user stays in control of their data.
- **Dropped the previous `if not send_counts_to_sqlite: return` gate.** Each
  table is now gated only on its own flag. The method is only reached when a
  SQLite sink is active (`run()` calls `setup_sqlite_database()` only when
  `config.uses_sqlite`), so gating on counts mode was both unnecessary and wrong:
  under `--no-counts --raw-events`, a leftover `full_key_log`/`trigram_counts_agg`
  would have been skipped — exactly the blind spot the review flagged.
- Added `sqlite_table_exists(name)`, a parameterized existence check, so table
  names are bound as parameters rather than spliced into the SQL string.
- Updated the call site in `setup_sqlite_database()` to the new method name.

### `README.md`

Added one Audit Checklist bullet: startup warns when the DB still holds a
`key_log`, `full_key_log`, or `trigram_counts_agg` table the current run isn't
writing, and prints the exact `DROP TABLE …;` rather than migrating or deleting
anything.

## Behavior Changes

- On startup with a SQLite sink, the logger now warns about every pre-existing
  sensitive table not active this run, not just `key_log`.
- Fresh databases and runs that legitimately enable a table (its flag ON) are
  unaffected — no warning for an intentional table.
- No table is ever migrated or dropped automatically; behavior is warn-only.

## Approach

Keep the existing warn-only, user-in-control philosophy and the single-message
format, and generalize from one hard-coded table to a data-driven list keyed by
each sink's own opt-in flag. Tailor each message to what that table actually
leaks (the `*_log` tables hold exact sequences; `trigram_counts_agg` is aggregate
counts but a higher reconstruction risk than the default bigrams).

## Alternatives Considered

### Keep the counts-mode gate and just add `full_key_log`
Rejected: it would still miss leftover sensitive tables under `--no-counts
--raw-events`, which is precisely the case the reviewer raised. Per-table flag
gating is both simpler and strictly more correct.

### Auto-drop or migrate the legacy tables
Rejected: silently deleting a user's data is exactly the kind of surprise this
project avoids. Warn and hand the user the precise `DROP TABLE` instead.

### One combined warning listing all leftover tables
Rejected: a separate line per table gives each its own copy-pasteable
`DROP TABLE <name>;` and reads clearly in the log.

## Assumptions

- The three named tables are the only sinks that retain exact-sequence or
  higher-risk history; `key_counts_agg`/`bigram_counts_agg` are the always-on
  aggregate defaults and are not flagged.
- The method runs only when a SQLite connection is open (guaranteed by
  `config.uses_sqlite` gating the call site).

## Shortcuts Or Tradeoffs

- The warning fires every run while a flagged table remains, which is mildly
  repetitive but is the point — it keeps nagging until the user drops the data or
  re-enables the corresponding mode.

## Known Limitations

- Detection is by table name only; a user who renamed a sensitive table won't be
  warned.
- Still warn-only by design: leftover data persists until the user runs the
  printed `DROP TABLE`.

## Key Decisions

- Gate each sensitive table on its own opt-in flag, not on counts mode.
- Warn-only, never migrate or delete; print the exact `DROP TABLE <name>;`.
- Parameterized `sqlite_table_exists()` helper instead of inlining table names.
