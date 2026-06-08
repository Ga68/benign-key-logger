## Goal

Make continuous background logging safe to leave running by changing the default
storage model from exact per-keystroke rows to **aggregate counts grouped into
time buckets**, so the exact typed sequence (passwords included) is never written
to disk. Add the bigram counting that the user wanted but which the old
view-based design could not provide once per-keystroke rows go away.

The user's stated plan was "round each keystroke's timestamp to the nearest 10
minutes." The important correction baked into this commit: rounding the timestamp
alone protects nothing, because one row per keystroke remains recoverable in
insertion (`rowid`) order regardless of its timestamp. The real protection is
collapsing keystrokes into per-bucket counts, which destroys ordering.

## Files Changed And Why

### `key_logger.py`

- **New default sink: aggregate count tables.** `key_counts_agg(bucket_utc,
  key_code, count)` and `bigram_counts_agg(bucket_utc, key1, key2, count)` are
  created and incremented via SQLite UPSERT (`ON CONFLICT ... DO UPDATE SET count
  = count + 1`). An optional `trigram_counts_agg` is created only with
  `--trigrams`. The composite PRIMARY KEY on each table is the UPSERT conflict
  target.
- **Tables are `WITHOUT ROWID` — load-bearing for privacy, not an optimization.**
  An ordinary SQLite table keeps an implicit `rowid` in insertion order, so
  reading the aggregate rows `ORDER BY rowid` would replay the order keys (and
  bigrams) were first seen in a bucket — and the bigram rows alone trivially
  reconstruct a quiet-bucket password (`(p,a),(a,s),(s,s),(s,w),... → password`).
  `WITHOUT ROWID` removes that column entirely; rows exist only in PRIMARY KEY
  (lexicographic) order, so nothing about typing order survives. Without this,
  aggregation would *not* actually destroy ordering, defeating the whole point.
- **Capture-time n-grams.** Bigrams (and optional trigrams) can no longer be
  rebuilt from stored rows, so `update_ngram_chain()` forms them live from the
  last one/two logged "plain" entries. The chain resets across modifier combos,
  pauses longer than `BIGRAM_IDLE_RESET_SECONDS`, and bucket boundaries, so each
  stored bigram is internally consistent (never spans two buckets) and unrelated
  typing sessions aren't stitched together.
- **`bucket_label()`** — new top-level pure helper that floors a UTC datetime to
  its bucket start and returns an ISO string. Floor (not round-to-nearest) keeps
  buckets contiguous and each event in exactly one bucket. Lives with the other
  pure helpers for easy testing.
- **Views rewritten** to read the aggregate tables (`SUM(count)` instead of
  `count(*)`/`LAG()`), preserving the same output columns (`count`, `frequency`,
  `cumulative_frequency`) so existing analysis queries still work.
- **New flags:** `--counts/--no-counts` (default follows `--sqlite`),
  `--raw-events/--no-raw-events` (opt-in exact per-keystroke `key_log`, off),
  `--trigrams/--no-trigrams` (off), `--bucket-minutes` (default 10).
  `--sqlite/--no-sqlite` is now the master DB switch; `Config.uses_sqlite`
  derives whether any DB sink is active. `parse_args()` validates bucket size,
  that DB sinks require SQLite, that trigrams require counts, and that at least
  one output sink is enabled.
- **`datetime.utcnow()` → `datetime.now(timezone.utc)`** in both timestamp paths,
  fixing the Python 3.12+ deprecation while keeping the stored ISO format
  unchanged (no `+00:00` suffix).

### `README.md`

Rewrote the Output Storage section to describe aggregation as the default and the
privacy reasoning (timestamp-rounding alone is insufficient; bigram/trigram
tradeoff; Secure Input Mode coverage), updated the SQLite-views and batching
notes, added usage examples for the new flags, and expanded the Audit Checklist
and Local Data Safety notes.

## Behavior Changes

- Default storage is now per-bucket counts, not per-keystroke rows. The default
  database has no recoverable sequence and no `key_log` table.
- Bigrams are counted at capture time and exposed through the same
  `bigram_counts` view; trigrams require `--trigrams`.
- `--raw-events` restores the old exact per-keystroke `key_log` table (opt-in).
- A literally-typed `+` (Shift+=) is now counted in bigrams; the old views'
  `NOT LIKE '%+%'` filter wrongly excluded it. Combo entries (`<ctrl> + c`) still
  break the n-gram chain, matching the old intent.
- Startup config summary reports `counts`, `bucket_minutes`, `trigrams`,
  `raw_events`, and `full_events`.

## Approach

Keep aggregation a shallow extension of the existing `log()` call site (which
already fires exactly once per logged non-modifier keystroke) and reuse the
already-computed `log_entry` as the n-gram unit, so the new counts match the
granularity the old views operated on. Keep all new invasive capabilities
(trigrams, exact rows) opt-in and off, consistent with the project's benign
ethos — the only default that changed is toward *more* privacy, which the user
explicitly requested.

## Alternatives Considered

### Round the timestamp but keep one row per keystroke
Rejected: does not protect anything; the sequence is still recoverable via
`rowid` order. This was the user's initial idea and the main thing this commit
corrects.

### Keep per-keystroke rows and run a periodic rollup/prune job
Rejected: still writes exact keystrokes to disk (a leak window), and needs a
scheduler or timer — more moving parts, less auditable.

### One wide n-gram table with an order column / nullable keys
Rejected: messier PRIMARY KEY (SQLite treats NULLs as distinct) and uglier views.
Three explicit tables are more auditable.

### Purge count-1 n-grams at bucket close (extra hardening)
Considered and explicitly declined by the user for now; left as a documented
future option. It would better protect a one-off secret typed in a quiet window
but biases rare-key stats and adds runtime DML.

## Assumptions

- SQLite ≥ 3.24 (UPSERT). The `keylogger` env ships 3.53; a startup guard errors
  clearly if an older engine is ever used with counts on.
- The user wants bigram frequency for layout work and accepts the residual,
  situational bigram-reconstruction risk (trigrams left off).

## Shortcuts Or Tradeoffs

- Bigrams that straddle a bucket boundary are dropped rather than attributed to
  one side — at most one lost pair per boundary crossing, negligible for
  frequency study, in exchange for internally consistent per-bucket rows.
- Old data is not migrated (see Known Limitations).
- A keystroke now issues up to a few writes (unigram + bigram [+ trigram]), so
  commits batch slightly more often. Harmless.

## Known Limitations

- Opening a pre-existing old-schema `key_log.sqlite` leaves the old table and
  rows untouched but does not migrate them into the aggregate tables; the views
  reflect only newly captured data. A manual `INSERT ... SELECT` backfill is
  possible but intentionally not run automatically.
- In raw-only mode (`--no-counts --raw-events`) the convenience views are not
  created; that mode is for users who query the raw table directly.
- Residual bigram-reconstruction risk remains for a short secret typed in an
  otherwise-quiet bucket; mitigated by bucket mixing, chain breaks, and Secure
  Input Mode, but not eliminated.

## Key Decisions

- Aggregate counts are the default; exact per-keystroke logging and trigrams are
  opt-in and off.
- Aggregate tables are `WITHOUT ROWID` so insertion order (and thus typing
  order) is not recoverable — counts are all that remain.
- Bigrams are computed at capture time; views read the aggregate tables.
- `--sqlite` becomes the master DB switch; counts default to following it.
- Floor-to-bucket timestamps; break n-gram chains across combos, pauses, and
  bucket boundaries.
