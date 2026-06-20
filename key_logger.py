#!/usr/bin/env python3

# ######### ######### ######## ##########
# ######### Execution Overview ##########
# ######### ######### ######## ##########

# Listen for every key-down and key-up event
# For each key-press, check it against of list of ignored keys, and, if
#   needed, remap it prior to further processing (e.g. <ctrl-r> to
#   <ctrl>, since I don't care about which <ctrl> key was used)
# On each key-down event, if it's not a modifier, then log it. If it's
#   a modifier, then keep track of what's being held down so we can log
#   the key-combo later.
# On each key-up event, clear the key from the list of what's being
#   held down

import atexit
import argparse
import logging
import os
import sqlite3
import stat
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from pynput.keyboard import Key, KeyCode, Listener


# ######### #### ######## ##########
# ######### User Settings ##########
# ######### #### ######## ##########

# SQLite is the master switch for using the database at all. Beneath it,
# the aggregate count tables (the private default), the exact per-keystroke
# `key_log` table, and the full up/down event log are independent sinks.
DEFAULT_SEND_LOGS_TO_SQLITE = True
DEFAULT_SEND_COUNTS_TO_SQLITE = True
DEFAULT_SEND_RAW_EVENTS_TO_SQLITE = False
DEFAULT_SEND_TRIGRAM_COUNTS = False
DEFAULT_SEND_ALL_EVENTS_TO_SQLITE = False
DEFAULT_SEND_LOGS_TO_FILE = False
DEFAULT_ECHO_KEYS_TO_STDOUT = False
DEFAULT_DEBUG = False
DEFAULT_LOG_PHYSICAL_KEYS = False
DEFAULT_TIMESTAMP_FILE_LOGS = True
DEFAULT_DISTINGUISH_MODIFIER_SIDES = False

# Keystrokes are aggregated into counts grouped by this many minutes, so the
# exact typed sequence (passwords included) is never stored, only per-bucket
# tallies. See bucket_label() and the long comment in log().
DEFAULT_BUCKET_MINUTES = 10

DEFAULT_LOG_FILE_NAME = 'key_log.txt'
DEFAULT_SQLITE_FILE_NAME = 'key_log.sqlite'
DEFAULT_ENABLE_SQLITE_WAL = False

OWNER_ONLY_FILE_MODE = 0o600
SQLITE_COMMIT_EVERY_N_EVENTS = 50
SQLITE_COMMIT_EVERY_SECONDS = 5.0

# A bigram is only counted when two keys are pressed within this many seconds
# of each other; a longer pause breaks the chain so unrelated typing sessions
# aren't stitched into spurious adjacency data.
BIGRAM_IDLE_RESET_SECONDS = 2.0

# UPSERT (INSERT ... ON CONFLICT ... DO UPDATE) requires SQLite 3.24+ (2018).
MINIMUM_SQLITE_VERSION_FOR_UPSERT = (3, 24, 0)

# ######### ####### ##### ##########
# ######### Logging Setup ##########
# ######### ####### ##### ##########

logging.basicConfig(
    # level=logging.DEBUG,
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d : %(levelname)-5s : %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ######### ###### ######### ##########
# ######### Global Constants ##########
# ######### ###### ######### ##########

# This can be changed, but I'm not sure there's much value to tinkering
# with it. You can read more about why it exists in the key_up()
# function.
LOCKED_IN_GARBAGE_COLLECTION_LIMIT = 5

MODIFIER_KEYS = [
    Key.alt,
    Key.alt_r,
    Key.alt_l,
    Key.cmd,
    Key.cmd_r,
    Key.cmd_l,
    Key.ctrl,
    Key.ctrl_r,
    Key.ctrl_l,
    Key.shift,
    Key.shift_r,
    Key.shift_l,
]

IGNORED_KEYS = []

REMAP = {
    Key.alt_r: Key.alt,
    Key.alt_l: Key.alt,
    Key.ctrl_r: Key.ctrl,
    Key.ctrl_l: Key.ctrl,
    Key.cmd_r: Key.cmd,
    Key.cmd_l: Key.cmd,
    Key.shift_r: Key.shift,
    Key.shift_l: Key.shift,
}

SHIFTED_KEY_EQUIVALENTS = {
    '`': '~',
    '1': '!',
    '2': '@',
    '3': '#',
    '4': '$',
    '5': '%',
    '6': '^',
    '7': '&',
    '8': '*',
    '9': '(',
    '0': ')',
    '-': '_',
    '=': '+',
    '[': '{',
    ']': '}',
    '\\': '|',
    ';': ':',
    "'": '"',
    ',': '<',
    '.': '>',
    '/': '?',
}

# Aggregate count tables. Each holds per-bucket tallies rather than one row
# per keystroke, so the exact typed sequence is never recoverable. The
# composite PRIMARY KEY is the conflict target the UPSERTs below increment.
#
# WITHOUT ROWID is load-bearing for privacy, not an optimization: an ordinary
# table keeps an implicit rowid in INSERTION order, so reading the rows in
# rowid order would replay the order keys/bigrams were first seen in a bucket
# (the bigram rows alone trivially reconstruct a quiet-bucket password). A
# WITHOUT ROWID table has no such column; rows live only in PRIMARY KEY
# (lexicographic) order, which reveals nothing about typing order. Counts are
# all that remain.
KEY_COUNTS_AGG_TABLE_SQL = """
  CREATE TABLE IF NOT EXISTS key_counts_agg (
    bucket_utc TEXT NOT NULL,
    key_code TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (bucket_utc, key_code)
  ) WITHOUT ROWID
"""

BIGRAM_COUNTS_AGG_TABLE_SQL = """
  CREATE TABLE IF NOT EXISTS bigram_counts_agg (
    bucket_utc TEXT NOT NULL,
    key1 TEXT NOT NULL,
    key2 TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (bucket_utc, key1, key2)
  ) WITHOUT ROWID
"""

TRIGRAM_COUNTS_AGG_TABLE_SQL = """
  CREATE TABLE IF NOT EXISTS trigram_counts_agg (
    bucket_utc TEXT NOT NULL,
    key1 TEXT NOT NULL,
    key2 TEXT NOT NULL,
    key3 TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (bucket_utc, key1, key2, key3)
  ) WITHOUT ROWID
"""

INSERT_KEY_COUNT_SQL = (
    'INSERT INTO key_counts_agg (bucket_utc, key_code, count) VALUES (?, ?, 1) '
    'ON CONFLICT(bucket_utc, key_code) DO UPDATE SET count = count + 1'
)

INSERT_BIGRAM_COUNT_SQL = (
    'INSERT INTO bigram_counts_agg (bucket_utc, key1, key2, count) '
    'VALUES (?, ?, ?, 1) '
    'ON CONFLICT(bucket_utc, key1, key2) DO UPDATE SET count = count + 1'
)

INSERT_TRIGRAM_COUNT_SQL = (
    'INSERT INTO trigram_counts_agg (bucket_utc, key1, key2, key3, count) '
    'VALUES (?, ?, ?, ?, 1) '
    'ON CONFLICT(bucket_utc, key1, key2, key3) DO UPDATE SET count = count + 1'
)

# The views below summarize the aggregate tables across all buckets. They keep
# the same output columns (count, frequency, cumulative_frequency) the old
# key_log-based views had, so existing analysis queries keep working. Combo
# filtering (the old `NOT LIKE '%+%'`) now happens at capture time, so it isn't
# repeated here.
KEY_COUNTS_VIEW_SQL = """
  CREATE VIEW IF NOT EXISTS key_counts AS
  WITH frequencies AS (
      SELECT key_code, SUM(count) AS count,
          (SUM(count) * 1.0) / (SELECT SUM(count) FROM key_counts_agg)
              AS frequency
      FROM key_counts_agg
      GROUP BY key_code
  )
  SELECT *, SUM(frequency) OVER (
      ORDER BY frequency DESC ROWS UNBOUNDED PRECEDING
  ) AS cumulative_frequency
  FROM frequencies
  ORDER BY frequency DESC, key_code
"""

BIGRAM_COUNTS_VIEW_SQL = """
  CREATE VIEW IF NOT EXISTS bigram_counts AS
  WITH bigram_totals AS (
      SELECT key1 || ' ' || key2 AS bigram, SUM(count) AS count
      FROM bigram_counts_agg
      GROUP BY key1, key2
  )
  , bigram_frequencies AS (
      SELECT bigram, count,
          (1.0 * count) / (SELECT SUM(count) FROM bigram_totals) AS frequency
      FROM bigram_totals
  )
  SELECT *, SUM(frequency) OVER (
      ORDER BY frequency DESC ROWS UNBOUNDED PRECEDING
  ) AS cumulative_frequency
  FROM bigram_frequencies
  ORDER BY cumulative_frequency, count DESC, bigram
"""

TRIGRAM_COUNTS_VIEW_SQL = """
  CREATE VIEW IF NOT EXISTS trigram_counts AS
  WITH trigram_totals AS (
      SELECT key1 || ' ' || key2 || ' ' || key3 AS trigram, SUM(count) AS count
      FROM trigram_counts_agg
      GROUP BY key1, key2, key3
  )
  , trigram_frequencies AS (
      SELECT trigram, count,
          (1.0 * count) / (SELECT SUM(count) FROM trigram_totals) AS frequency
      FROM trigram_totals
  )
  SELECT *, SUM(frequency) OVER (
      ORDER BY frequency DESC ROWS UNBOUNDED PRECEDING
  ) AS cumulative_frequency
  FROM trigram_frequencies
  ORDER BY cumulative_frequency, count DESC, trigram
"""


@dataclass
class Config:
  send_counts_to_sqlite: bool = DEFAULT_SEND_COUNTS_TO_SQLITE
  send_raw_events_to_sqlite: bool = DEFAULT_SEND_RAW_EVENTS_TO_SQLITE
  send_trigram_counts: bool = DEFAULT_SEND_TRIGRAM_COUNTS
  send_all_events_to_sqlite: bool = DEFAULT_SEND_ALL_EVENTS_TO_SQLITE
  send_logs_to_file: bool = DEFAULT_SEND_LOGS_TO_FILE
  timestamp_file_logs: bool = DEFAULT_TIMESTAMP_FILE_LOGS
  echo_keys_to_stdout: bool = DEFAULT_ECHO_KEYS_TO_STDOUT
  debug: bool = DEFAULT_DEBUG
  log_physical_keys: bool = DEFAULT_LOG_PHYSICAL_KEYS
  distinguish_modifier_sides: bool = DEFAULT_DISTINGUISH_MODIFIER_SIDES
  log_file_name: str = DEFAULT_LOG_FILE_NAME
  sqlite_file_name: str = DEFAULT_SQLITE_FILE_NAME
  enable_sqlite_wal: bool = DEFAULT_ENABLE_SQLITE_WAL
  bucket_interval_seconds: int = DEFAULT_BUCKET_MINUTES * 60

  @property
  def uses_sqlite(self):
    # True when any SQLite-backed sink is on, so the database is opened and
    # commits are flushed. The --sqlite/--no-sqlite master switch is resolved
    # into these fields in parse_args().
    return (
        self.send_counts_to_sqlite
        or self.send_raw_events_to_sqlite
        or self.send_all_events_to_sqlite
    )


# `Config` holds the user-selected runtime settings derived from CLI flags.
def build_parser():
  parser = argparse.ArgumentParser(
      formatter_class=argparse.ArgumentDefaultsHelpFormatter,
      description=(
          'Track your own key usage locally with configurable SQLite, text, '
          'stdout, and WAL options.'
      )
  )
  parser.add_argument(
      '--sqlite',
      dest='send_logs_to_sqlite',
      action='store_true',
      help='use the SQLite database (master switch for all DB sinks)'
  )
  parser.add_argument(
      '--no-sqlite',
      dest='send_logs_to_sqlite',
      action='store_false',
      help='disable the SQLite database entirely'
  )
  parser.add_argument(
      '--counts',
      dest='send_counts_to_sqlite',
      action='store_true',
      help='write aggregate key/bigram counts bucketed by time (default: follows --sqlite)'
  )
  parser.add_argument(
      '--no-counts',
      dest='send_counts_to_sqlite',
      action='store_false',
      help='disable the aggregate count tables'
  )
  parser.add_argument(
      '--raw-events',
      dest='send_raw_events_to_sqlite',
      action='store_true',
      help='also store exact per-keystroke rows in key_log (less private; off by default)'
  )
  parser.add_argument(
      '--no-raw-events',
      dest='send_raw_events_to_sqlite',
      action='store_false',
      help='disable the exact per-keystroke key_log table'
  )
  parser.add_argument(
      '--trigrams',
      dest='send_trigram_counts',
      action='store_true',
      help='also aggregate trigram counts (off by default; increases reconstruction risk)'
  )
  parser.add_argument(
      '--no-trigrams',
      dest='send_trigram_counts',
      action='store_false',
      help='disable trigram aggregation'
  )
  parser.add_argument(
      '--bucket-minutes',
      dest='bucket_minutes',
      type=int,
      default=DEFAULT_BUCKET_MINUTES,
      help='size in minutes of the aggregation time bucket'
  )
  parser.add_argument(
      '--file',
      dest='send_logs_to_file',
      action='store_true',
      help='write captured keys to a plaintext log file'
  )
  parser.add_argument(
      '--no-file',
      dest='send_logs_to_file',
      action='store_false',
      help='disable the plaintext log file'
  )
  parser.add_argument(
      '--full-events',
      dest='send_all_events_to_sqlite',
      action='store_true',
      help='record every key up/down event in the SQLite full_key_log table'
  )
  parser.add_argument(
      '--no-full-events',
      dest='send_all_events_to_sqlite',
      action='store_false',
      help='disable the SQLite full event log table'
  )
  parser.add_argument(
      '--file-timestamps',
      action='store_true',
      help='prepend UTC timestamps to plaintext log file entries'
  )
  parser.add_argument(
      '--no-file-timestamps',
      dest='file_timestamps',
      action='store_false',
      help='write plaintext log file entries without timestamps'
  )
  parser.add_argument(
      '--physical-keys',
      action='store_true',
      help='log the physical key plus modifiers instead of the resulting character'
  )
  parser.add_argument(
      '--modifier-sides',
      action='store_true',
      help='keep left/right modifier keys distinct instead of remapping them'
  )
  parser.add_argument(
      '--debug',
      action='store_true',
      help='show internal debug logging without implying key echo'
  )
  parser.add_argument(
      '--stdout',
      action='store_true',
      help='echo captured keys to stdout while logging'
  )
  parser.add_argument(
      '--sqlite-file',
      default=DEFAULT_SQLITE_FILE_NAME,
      help='path to the SQLite database file'
  )
  parser.add_argument(
      '--log-file',
      default=DEFAULT_LOG_FILE_NAME,
      help='path to the plaintext log file'
  )
  parser.add_argument(
      '--wal',
      dest='enable_sqlite_wal',
      action='store_true',
      help='enable SQLite write-ahead logging'
  )
  parser.add_argument(
      '--no-wal',
      dest='enable_sqlite_wal',
      action='store_false',
      help='disable SQLite write-ahead logging'
  )
  parser.set_defaults(
      send_logs_to_sqlite=DEFAULT_SEND_LOGS_TO_SQLITE,
      # None means "follow the --sqlite master switch"; resolved in parse_args.
      send_counts_to_sqlite=None,
      send_raw_events_to_sqlite=DEFAULT_SEND_RAW_EVENTS_TO_SQLITE,
      send_trigram_counts=DEFAULT_SEND_TRIGRAM_COUNTS,
      send_logs_to_file=DEFAULT_SEND_LOGS_TO_FILE,
      send_all_events_to_sqlite=DEFAULT_SEND_ALL_EVENTS_TO_SQLITE,
      file_timestamps=DEFAULT_TIMESTAMP_FILE_LOGS,
      enable_sqlite_wal=DEFAULT_ENABLE_SQLITE_WAL,
  )
  return parser


def parse_args(argv=None):
  parser = build_parser()
  args = parser.parse_args(argv)

  # Counts default to following the --sqlite master switch unless the user
  # explicitly passed --counts/--no-counts.
  send_counts = args.send_counts_to_sqlite
  if send_counts is None:
    send_counts = args.send_logs_to_sqlite

  if args.bucket_minutes <= 0:
    parser.error('--bucket-minutes must be a positive integer')

  db_sinks_on = (
      send_counts
      or args.send_raw_events_to_sqlite
      or args.send_all_events_to_sqlite
  )
  if db_sinks_on and not args.send_logs_to_sqlite:
    parser.error(
        'count/raw-event/full-event logging requires SQLite; remove --no-sqlite'
    )

  if args.send_trigram_counts and not send_counts:
    parser.error('--trigrams requires count aggregation; enable counts')

  if not (db_sinks_on or args.send_logs_to_file or args.stdout):
    parser.error(
        'no output sink enabled; enable counts, --raw-events, --full-events, '
        '--file, or --stdout'
    )

  return Config(
      send_counts_to_sqlite=send_counts,
      send_raw_events_to_sqlite=args.send_raw_events_to_sqlite,
      send_trigram_counts=args.send_trigram_counts,
      send_all_events_to_sqlite=args.send_all_events_to_sqlite,
      send_logs_to_file=args.send_logs_to_file,
      timestamp_file_logs=args.file_timestamps,
      echo_keys_to_stdout=args.stdout,
      debug=args.debug,
      log_physical_keys=args.physical_keys,
      distinguish_modifier_sides=args.modifier_sides,
      log_file_name=args.log_file,
      sqlite_file_name=args.sqlite_file,
      enable_sqlite_wal=args.enable_sqlite_wal,
      bucket_interval_seconds=args.bucket_minutes * 60,
  )


def key_is_a_symbol(key):
  return str(key)[0:4] != 'Key.'


def canonicalize_key(key, distinguish_modifier_sides=False):
  if distinguish_modifier_sides:
    return key
  if key in REMAP:
    return REMAP[key]
  return key


def canonicalized_modifiers(modifiers_down):
  return {
      canonicalize_key(modifier)
      for modifier in modifiers_down
  }


def key_to_str(key):
  """
  The string representation pynput's Key.* objects isn't my preferred
  output, so this function standardizes how they're "stringified". The
  gist is that symbols (for example: a, b, Z, !, 3) are presented as-is,
  and other keys (for example: shift, control, command) are enclosed in
  brackets: '<' and '>'.

  There's a slightly more involved process for the symbols, only
  because the string representation includes the surrounding quotes of
  character (for example: "'a'") and it escapes backslashes, so that part
  undoes those two items.
  """
  s = str(key)
  if not key_is_a_symbol(key):
    s = f'<{s[4:]}>'
  else:
    s = s.encode('latin-1', 'backslashreplace').decode('unicode-escape')
    s = s[1:-1]  # trim the leading and trailing quotes
  return s


def normalize_ctrl_character(key, modifiers_down):
  if Key.ctrl not in canonicalized_modifiers(modifiers_down):
    return key

  key_str = key_to_str(key)
  if len(key_str) != 1:
    return key

  codepoint = ord(key_str)
  if codepoint < 1 or codepoint > 26:
    return key

  return KeyCode.from_char(chr(ord('a') + codepoint - 1))


def normalize_shifted_key_for_physical_logging(key, modifiers_down):
  if Key.shift not in canonicalized_modifiers(modifiers_down):
    return key

  key_str = key_to_str(key)
  if len(key_str) != 1:
    return key

  if key_str.isalpha():
    return KeyCode.from_char(key_str.lower())

  for unshifted, shifted in SHIFTED_KEY_EQUIVALENTS.items():
    if key_str == shifted:
      return KeyCode.from_char(unshifted)

  return key


def format_logged_key(
    key,
    modifiers_down,
    log_physical_keys,
    distinguish_modifier_sides=False,
):
  normalized_key = normalize_ctrl_character(
      canonicalize_key(key, distinguish_modifier_sides),
      modifiers_down
  )
  if log_physical_keys:
    normalized_key = normalize_shifted_key_for_physical_logging(
        normalized_key,
        modifiers_down
    )
  return key_to_str(normalized_key)


def equivalent_shifted_keys(key):
  key_str = key_to_str(key)
  if len(key_str) != 1:
    return set()

  equivalents = set()
  if key_str.isalpha():
    equivalents.add(key_str.swapcase())

  shifted_pair = SHIFTED_KEY_EQUIVALENTS.get(key_str)
  if shifted_pair is not None:
    equivalents.add(shifted_pair)

  for unshifted, shifted in SHIFTED_KEY_EQUIVALENTS.items():
    if key_str == shifted:
      equivalents.add(unshifted)

  return equivalents


def bucket_label(dt, interval_seconds=600):
  """
  Floor a UTC datetime down to the start of its time bucket and return it as
  an ISO-8601 string. interval_seconds defaults to 600 (10 minutes).

  Flooring (not rounding to the nearest boundary) means a bucket label is a
  real timestamp marking the inclusive start of the window it covers, buckets
  never overlap, and every event maps to exactly one bucket deterministically.
  This is the grouping key the aggregate count tables use, so individual
  keystroke timings are discarded — only per-bucket tallies remain.
  """
  epoch = int(dt.replace(tzinfo=timezone.utc).timestamp())
  floored = epoch - (epoch % interval_seconds)
  return (
      datetime.fromtimestamp(floored, timezone.utc)
      .replace(tzinfo=None)
      .isoformat()
  )


class KeyLoggerApp:
  # `KeyLoggerApp` owns the mutable state and side effects of a single run.
  def __init__(self, config):
    self.config = config
    self.keys_currently_down = []
    self.pending_sqlite_writes = 0
    self.last_sqlite_commit_time = None
    self.db_connection = None
    self.db_cursor = None
    self._close_registered = False
    # Capture-time n-gram chain. Bigrams/trigrams are formed from the last
    # one/two logged "plain" entries, then stored as counts. The chain resets
    # across modifier combos, long pauses, and bucket boundaries (see log()).
    self.previous_logged_entry = None
    self.previous_logged_monotonic = None
    self.previous_logged_bucket = None
    self.second_previous_logged_entry = None

  def get_file_mode(self, path):
    return stat.S_IMODE(os.stat(path).st_mode)

  def ensure_owner_only_permissions(self, path):
    if not os.path.exists(path):
      return

    current_mode = self.get_file_mode(path)
    if current_mode != OWNER_ONLY_FILE_MODE:
      logging.warning(
          f'tightening file permissions for {path}: '
          f'{oct(current_mode)} -> {oct(OWNER_ONLY_FILE_MODE)}'
      )
      os.chmod(path, OWNER_ONLY_FILE_MODE)

  def ensure_sqlite_files_are_owner_only(self):
    for path in [
        self.config.sqlite_file_name,
        f'{self.config.sqlite_file_name}-journal',
        f'{self.config.sqlite_file_name}-wal',
        f'{self.config.sqlite_file_name}-shm',
    ]:
      self.ensure_owner_only_permissions(path)

  def open_owner_only_log_file(self, path):
    fd = os.open(
        path,
        os.O_APPEND | os.O_CREAT | os.O_WRONLY,
        OWNER_ONLY_FILE_MODE
    )
    self.ensure_owner_only_permissions(path)
    return os.fdopen(fd, 'a')

  def commit_sqlite_if_needed(self, force=False):
    if not self.config.uses_sqlite or self.pending_sqlite_writes == 0:
      return

    elapsed_since_last_commit = (
        time.monotonic() - self.last_sqlite_commit_time
    )
    should_commit = force
    should_commit = should_commit or (
        self.pending_sqlite_writes >= SQLITE_COMMIT_EVERY_N_EVENTS
    )
    should_commit = should_commit or (
        elapsed_since_last_commit >= SQLITE_COMMIT_EVERY_SECONDS
    )

    if not should_commit:
      return

    self.db_connection.commit()
    self.ensure_sqlite_files_are_owner_only()
    logging.debug(
        'committed SQLite writes: '
        f'{self.pending_sqlite_writes} pending rows flushed'
    )
    self.pending_sqlite_writes = 0
    self.last_sqlite_commit_time = time.monotonic()

  def note_pending_sqlite_write(self):
    self.pending_sqlite_writes += 1
    self.commit_sqlite_if_needed()

  def close_sqlite_connection(self):
    if self.db_connection is None:
      return

    self.commit_sqlite_if_needed(force=True)
    self.db_connection.close()
    self.db_connection = None
    self.db_cursor = None

  def reconcile_shift_mismatch(self, key):
    for equivalent_key_str in equivalent_shifted_keys(key):
      equivalent_key = KeyCode.from_char(equivalent_key_str)
      if equivalent_key in self.keys_currently_down:
        self.keys_currently_down.remove(equivalent_key)
        logging.debug(
            'reconciled shifted key mismatch: '
            f'{key_to_str(equivalent_key)} cleared by {key_to_str(key)} up event'
        )
        return True
    return False

  def prepare_sqlite_file(self):
    if not os.path.exists(self.config.sqlite_file_name):
      with self.open_owner_only_log_file(self.config.sqlite_file_name):
        pass

  def open_sqlite_connection(self):
    self.db_connection = sqlite3.connect(
        self.config.sqlite_file_name,
        check_same_thread=False,
        # The same thread check is off since the keyboard listener works
        # in a spawned thread (a decision of the pynput library) separate
        # from this python script.
    )
    self.ensure_sqlite_files_are_owner_only()
    self.db_cursor = self.db_connection.cursor()
    self.pending_sqlite_writes = 0
    self.last_sqlite_commit_time = time.monotonic()
    if not self._close_registered:
      atexit.register(self.close_sqlite_connection)
      self._close_registered = True
    logging.debug('SQLite connection and cursor created')

  def configure_sqlite_journal_mode(self):
    if not self.config.enable_sqlite_wal:
      return

    self.db_cursor.execute('PRAGMA journal_mode=WAL')
    self.ensure_sqlite_files_are_owner_only()
    logging.info('SQLite WAL mode enabled')

  def create_sqlite_tables(self):
    if self.config.send_counts_to_sqlite:
      self.db_cursor.execute(KEY_COUNTS_AGG_TABLE_SQL)
      self.db_cursor.execute(BIGRAM_COUNTS_AGG_TABLE_SQL)
      logging.debug('SQLite key_counts_agg and bigram_counts_agg tables created')
      if self.config.send_trigram_counts:
        self.db_cursor.execute(TRIGRAM_COUNTS_AGG_TABLE_SQL)
        logging.debug('SQLite trigram_counts_agg table created')

    if self.config.send_raw_events_to_sqlite:
      self.db_cursor.execute("""
          CREATE TABLE IF NOT EXISTS key_log
          (time_utc TEXT, key_code TEXT)
      """)
      logging.debug('SQLite key_log table created')

    if self.config.send_all_events_to_sqlite:
      self.db_cursor.execute("""
          CREATE TABLE IF NOT EXISTS full_key_log
          (time_utc TEXT, key_code TEXT, event_type TEXT)
      """)
      logging.debug('SQLite full_key_log table created')

  def sqlite_table_exists(self, name):
    # Parameterized existence check so a table name is never spliced into SQL.
    self.db_cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    return self.db_cursor.fetchone() is not None

  def warn_about_legacy_sensitive_tables(self):
    # Some sink tables hold history the current run neither writes nor protects:
    # key_log (exact per-keystroke rows), full_key_log (exact up/down events +
    # timestamps), and trigram_counts_agg (higher reconstruction risk than the
    # default bigrams). When the matching opt-in flag is OFF, such a table is
    # leftover from an older run -- not migrated, not read by the views, just
    # sitting in the file and keeping that history reconstructable. The privacy
    # default doesn't cover data written before the switch, so warn and point at
    # the DROP. When the flag is ON the table is intentional this run, so skip
    # it. Each table is gated only on its own flag (NOT on counts mode), so a
    # leftover full_key_log/trigram table is still flagged under, e.g.,
    # --no-counts --raw-events.
    legacy_tables = (
        ('key_log', self.config.send_raw_events_to_sqlite,
         'exact per-keystroke rows; the exact typed sequence is recoverable'),
        ('full_key_log', self.config.send_all_events_to_sqlite,
         'exact key up/down events with timestamps'),
        ('trigram_counts_agg', self.config.send_trigram_counts,
         'trigram counts, a higher reconstruction risk than the default bigrams'),
    )
    for name, intentional, what_it_leaks in legacy_tables:
      if intentional or not self.sqlite_table_exists(name):
        continue
      logging.warning(
          f"legacy '{name}' table ({what_it_leaks}) found in "
          f'{self.config.sqlite_file_name}; it is not migrated and stays on '
          f'disk. Run "DROP TABLE {name};" against the file to remove it.'
      )

  def create_sqlite_views(self):
    # The convenience views summarize the aggregate count tables. Without
    # counts there's nothing for them to read, so skip them in raw-only mode.
    if not self.config.send_counts_to_sqlite:
      return

    self.db_cursor.execute('DROP VIEW IF EXISTS key_counts')
    self.db_cursor.execute(KEY_COUNTS_VIEW_SQL)
    logging.debug('SQLite key_counts view created')

    self.db_cursor.execute('DROP VIEW IF EXISTS bigram_counts')
    self.db_cursor.execute(BIGRAM_COUNTS_VIEW_SQL)
    logging.debug('SQLite bigram_counts view created')

    # Always drop the trigram view so an old one doesn't dangle; recreate it
    # only when trigram aggregation is enabled.
    self.db_cursor.execute('DROP VIEW IF EXISTS trigram_counts')
    if self.config.send_trigram_counts:
      self.db_cursor.execute(TRIGRAM_COUNTS_VIEW_SQL)
      logging.debug('SQLite trigram_counts view created')

  def finish_sqlite_setup(self):
    self.db_connection.commit()
    self.ensure_sqlite_files_are_owner_only()
    self.last_sqlite_commit_time = time.monotonic()
    logging.info(f'SQLite database set up: {self.config.sqlite_file_name}')

  def setup_sqlite_database(self):
    """
    This creates the Python objects and the initial table and views in
    the SQLite database (file). It's long, but that's primarily just
    because some of the SQL for the views is long. At it's most basic, it
    is pretty straight forward: (1) connect to the SQLite file, (2) create
    the table for storing key presses, and (3) create the views for
    looking at usage statistics

    If you already have a SQLite key-log (a file with the name
    sqlite_file_name), then the results of the session will be APPENDED to
    those. This is accomplished by running a CREATE TABLE IF NOT EXISTS
    statement, as opposed to the more simple CREATE TABLE statement. If
    you want to start from scratch you can (1) delete the existing file
    from your disk (the below will create a new one), (2) rename the
    existing file so you retain that prior sessions' data and a new file
    will be created, or (3) change the name of the file in the
    sqlite_file_name config value and a new one will be created.

    By default the database stores only AGGREGATE COUNTS grouped into time
    buckets (see DEFAULT_BUCKET_MINUTES and bucket_label): one row per
    (bucket, key) and (bucket, key1, key2), incremented in place. The exact
    typed sequence is never written, so passwords can't be read back out of
    the file. The convenience views (key_counts, bigram_counts, and, with
    --trigrams, trigram_counts) summarize those tallies for layout analysis.
    Trigrams and the exact per-keystroke `key_log` table (--raw-events) are
    opt-in and off by default because they leak more ordering information.
    """
    if (self.config.send_counts_to_sqlite
        and sqlite3.sqlite_version_info < MINIMUM_SQLITE_VERSION_FOR_UPSERT):
      raise SystemExit(
          f'SQLite {sqlite3.sqlite_version} is too old for count aggregation; '
          'need >= 3.24.0 for UPSERT. Upgrade Python/SQLite, or run with '
          '--no-counts --raw-events for the exact-sequence log instead.'
      )
    self.prepare_sqlite_file()
    self.open_sqlite_connection()
    self.warn_about_legacy_sensitive_tables()
    self.configure_sqlite_journal_mode()
    self.create_sqlite_tables()
    self.create_sqlite_views()
    self.finish_sqlite_setup()

  def log(self, key):
    """
    We're looking to see what modifiers are pressed, in addition to the
    key that triggered the log request, and then want to log that.

    If <shift> alone is the modifier pressed down we don't really need to
    track it when used with a symbol. For example, if you press 'a',
    you'll see that 'a' is logged, and when you press 'shift+a', 'A'
    is logged (similarly '1' and '!'). It's not important that shift
    was used to get there, only the final key, since, when setting up
    your own keyboard, it's possible that you choose to put a symbol,
    like '@' on a layer that doesn't require shift. The "alone" part here
    may look a bit more complicated than needed; however, it's to account
    for the case that you don't remap <shift_r> to <shift> and you then
    either do <shift_r> + a = A, or even <shift_r> + <shift_l> + a = A.
    The code there maps <shift>, <shift_r>, and <shift_l> to <shift>, and
    then removes duplicates (multi-shift key-downs) using the set(...)
    constructor.

    If you use shift with a non-symbol (like the right arrow), then
    you'd want to log it as normal, since this behavior (which is
    expanding the selection one character to the right usually)
    wouldn't be distinguishable from simple <right>.

    Additionally, when there are modifiers in addition to shift (like
    <ctrl> or <cmd>), you'll see that <ctrl> + <shift> + 'a' is logged
    like that and not like <ctrl> + A. So maintaining the <shift> as
    part of the combo, is important to distinguish between <ctrl> + a
    and <ctrl> + <shift> + a (and logging <ctrl> + A seems,
    conceptually, to miss the mark on logging combos).
    """
    modifiers_down = [
        canonicalize_key(k, self.config.distinguish_modifier_sides)
        for k in self.keys_currently_down
        if k in MODIFIER_KEYS
    ]
    modifiers_down = list(dict.fromkeys(modifiers_down))
    if (
        not self.config.log_physical_keys
        and list(set([
            Key.shift if k in [Key.shift, Key.shift_l, Key.shift_r] else k
            for k in modifiers_down
        ])) == [Key.shift]
        and key_is_a_symbol(key)
    ):
      modifiers_down = []
    log_entry = ' + '.join(
        sorted([key_to_str(k) for k in modifiers_down])
        + [format_logged_key(
            key,
            modifiers_down,
            self.config.log_physical_keys,
            self.config.distinguish_modifier_sides
        )]
    )
    if self.config.echo_keys_to_stdout:
      logging.info(f'key: {log_entry}')

    now_dt = datetime.now(timezone.utc)
    timestamp_utc = now_dt.replace(tzinfo=None).isoformat()

    if self.config.send_counts_to_sqlite:
      bucket = bucket_label(now_dt, self.config.bucket_interval_seconds)
      self.record_unigram_count(bucket, log_entry)
      self.update_ngram_chain(bucket, log_entry, time.monotonic())

    if self.config.send_raw_events_to_sqlite:
      row_values = (timestamp_utc, log_entry)
      self.db_cursor.execute(
          'INSERT INTO key_log VALUES (?, ?)',
          row_values
      )
      self.note_pending_sqlite_write()
      logging.debug(f'logged to SQLite:key_log {row_values}')

    if self.config.send_logs_to_file:
      with self.open_owner_only_log_file(self.config.log_file_name) as log_file:
        file_entry = log_entry
        if self.config.timestamp_file_logs:
          file_entry = f'{timestamp_utc},{log_entry}'
        log_file.write(f'{file_entry}\n')
        logging.debug(f'logged to file: {log_entry}')

  def record_unigram_count(self, bucket, key_str):
    self.db_cursor.execute(INSERT_KEY_COUNT_SQL, (bucket, key_str))
    self.note_pending_sqlite_write()

  def record_bigram_count(self, bucket, key1, key2):
    self.db_cursor.execute(INSERT_BIGRAM_COUNT_SQL, (bucket, key1, key2))
    self.note_pending_sqlite_write()

  def record_trigram_count(self, bucket, key1, key2, key3):
    self.db_cursor.execute(INSERT_TRIGRAM_COUNT_SQL, (bucket, key1, key2, key3))
    self.note_pending_sqlite_write()

  def update_ngram_chain(self, bucket, log_entry, now_monotonic):
    """
    Count the bigram (and, if enabled, trigram) ending at this keystroke, then
    advance the chain. This replaces the old SQL views that rebuilt n-grams
    from consecutive per-keystroke rows: since we no longer store those rows,
    adjacency has to be captured live.

    A pair is only counted when both keys are "plain" (no modifier combo, i.e.
    no ' + ' in the entry, mirroring the old views' NOT LIKE '%+%' filter),
    pressed within BIGRAM_IDLE_RESET_SECONDS of each other, and falling in the
    same time bucket. The bucket guard keeps each stored row internally
    consistent (a bigram never spans two buckets); a combo, a long pause, or a
    bucket flip simply breaks the chain and it reseeds on the next plain key.
    """
    current_is_plain = ' + ' not in log_entry
    bigram_emitted = False

    if (current_is_plain
        and self.previous_logged_entry is not None
        and (now_monotonic - self.previous_logged_monotonic)
            <= BIGRAM_IDLE_RESET_SECONDS
        and bucket == self.previous_logged_bucket):
      self.record_bigram_count(bucket, self.previous_logged_entry, log_entry)
      bigram_emitted = True
      if (self.config.send_trigram_counts
          and self.second_previous_logged_entry is not None):
        self.record_trigram_count(
            bucket,
            self.second_previous_logged_entry,
            self.previous_logged_entry,
            log_entry
        )

    if current_is_plain:
      # second_previous stays valid only when this step formed a real
      # consecutive pair; otherwise a trigram next step would span a break.
      self.second_previous_logged_entry = (
          self.previous_logged_entry if bigram_emitted else None
      )
      self.previous_logged_entry = log_entry
      self.previous_logged_monotonic = now_monotonic
      self.previous_logged_bucket = bucket
    else:
      self.second_previous_logged_entry = None
      self.previous_logged_entry = None
      self.previous_logged_monotonic = None
      self.previous_logged_bucket = None

  def full_log(self, key, event):
    if self.config.send_all_events_to_sqlite:
      row_values = (
          datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
          key_to_str(canonicalize_key(
              key,
              self.config.distinguish_modifier_sides
          )),
          event
      )
      self.db_cursor.execute(
          'INSERT INTO full_key_log VALUES (?, ?, ?)',
          row_values
      )
      self.note_pending_sqlite_write()
      logging.debug(f'logged to SQLite:full_key_log {row_values}')

  def key_down(self, key):
    """
    The goal here is to keep track of each key that's being pressed down
    and log when an action has taken place. By "action" I mean something
    that would be expected to send a keystroke to the computer (such as
    'a', as opposed to pressing just <shift>). If what's being pressed is
    only a modifier (the <cmd> in <cmd>-A), then we need to keep track
    that it's down, and wait until something else is pressed.

    First we only log the press if it's not already in the list, to avoid
    logging "sticky keys": pressing and holding a key and then seeing it
    typed many times. By exiting the function (stopping all processing)
    if it's in the keys_currently_down list (already being pressed), we
    ignore the repeats. This seems reasonable since in some places,
    holding the key will type the letter many times, and in others it
    will pop up a menu for selecting letters with diacritics. So it
    seems poorly defined as to what's actually happening on the screen
    anyways, during a hold-down. And the whole point of this program is
    to help you figure out what your fingers are doing, not necessarily
    what is going on in the computer.
    """
    if self.config.send_all_events_to_sqlite:
      self.full_log(key, 'DOWN')

    if key in self.keys_currently_down:
      return

    self.keys_currently_down.append(key)
    logging.debug(
        f'key down : {key_to_str(key)} : '
        f'{[key_to_str(k) for k in self.keys_currently_down]}'
    )
    if key not in MODIFIER_KEYS:
      self.log(key)

  def key_up(self, key):
    """
    The real action goes on when a key is pressed down, not up; however,
    this function needs to accomplish two key things: (1) registering that
    a key is no longer being pressed, which is especially important for
    the modifier keys, and (2) taking care of some routine clean up for
    keys that never get registered as having been released (up events,
    without a corresponding down event).

    It seems counter intuitive that a key could have been released, but
    never pressed; however, it seems to be the case. I don't know how
    general this case is, but it was consistent and repeatable for me.
    This seems to happen when you mix up the order of <shift> plus a
    symbol. For example, press down <shift>, then 'a', and what
    registers is a down-press of 'A' (which gets logged). If you then
    release the a-key, you're left with only <shift> being held down,
    which is an effectively "nothing" state. But instead, if you pick up
    <shift> first (while your finger is still holding down the a-key), the
    system registers <shift> up, and then 'a' (little a) down, but never
    'A' (big-A) up. And lastly when you pick up your finger from 'a', then
    the little-a gets cleared. In that sequence you'll see that big-A
    never got cleared (registered up). So now big-A is still in the
    keys_currently_down list, but you have no fingers on the keyboard.
    Another instance I've noticed is that as the system goes into and out
    of "secure input mode" (at least in macOS, the system locks down
    keyboard listening when you're in a password field), some key-up and
    key-down pairs don't match.

    In practice, this isn't actually that big of a deal because the
    logging event happens when a key is pressed down, and only the
    modifier keys (<ctrl>, <cmd>, etc.) plus the actual key that's being
    pressed, are being used to determine the combination. So a spurious
    'A' that's still in the keys_currently_down list, will have no effect
    when the 'w' is pressed in <cmd>-w (close a window).

    However, in the interest of good house-keeping, I like the idea of
    periodically clearing out these locked-in symbols from the
    keys_currently_down list. We accomplish this by waiting until two
    criteria have been met: (1) the length of the keys_currently_down list
    exceeds a threshold (LOCKED_IN_GARBAGE_COLLECTION_LIMIT; so it doesn't
    happen too often or prematurely), and (2) there are no modifier keys
    being pressed (so we don't clean things up when you're in the middle
    of a key-combo).
    """
    if self.config.send_all_events_to_sqlite:
      self.full_log(key, 'UP')

    try:
      self.keys_currently_down.remove(key)
    except ValueError:
      if self.reconcile_shift_mismatch(key):
        pass
      else:
        logging.warning(f'{key_to_str(key)} up event without a paired down event')
      if len(self.keys_currently_down) >= LOCKED_IN_GARBAGE_COLLECTION_LIMIT:
        logging.debug('key-down count is above locked-in limit')
        number_of_modifiers_down = len([
            k for k in self.keys_currently_down if k in MODIFIER_KEYS
        ])
        if number_of_modifiers_down == 0:
          logging.debug(
              'clearing locked-in keys-down: '
              f'{[key_to_str(k) for k in self.keys_currently_down]}'
          )
          self.keys_currently_down = []

    logging.debug(
        f'key up  : {key_to_str(key)} : '
        f'{[key_to_str(k) for k in self.keys_currently_down]}'
    )

  def preprocess(self, key, handler):
    """
    A simple wrapper to to do some preprocessing on the key press prior to
    sending it off for normal key-up/down handling.

    The remapping step helps simplify the logging. For example, I don't
    care to log whether the left or right Control key was used in a combo,
    just that Control was used. So the CTRL_R is remapped simply to CTRL.

    Ignoring comes after remapping so that the ignore list can take
    advantage of the remapping, for brevity. For example, you can
    ignore left and right shift, by remapping shift_r and shift_l to
    shift, and then ignoring shift.
    """
    canonical_key = canonicalize_key(
        key,
        self.config.distinguish_modifier_sides
    )
    if canonical_key != key:
      logging.debug(
          f'remapped key {key_to_str(key)} -> {key_to_str(canonical_key)}'
      )

    if canonical_key in IGNORED_KEYS:
      logging.debug(f'ignoring key: {key_to_str(canonical_key)}')
      return

    return handler(key)

  def run(self):
    if self.config.debug:
      logging.getLogger().setLevel(logging.DEBUG)

    logging.info('getting set up')
    logging.info(
        'effective config: '
        f'counts={"on" if self.config.send_counts_to_sqlite else "off"}, '
        f'bucket_minutes={self.config.bucket_interval_seconds // 60}, '
        f'trigrams={"on" if self.config.send_trigram_counts else "off"}, '
        f'raw_events={"on" if self.config.send_raw_events_to_sqlite else "off"}, '
        f'full_events={"on" if self.config.send_all_events_to_sqlite else "off"}, '
        f'file={"on" if self.config.send_logs_to_file else "off"}, '
        f'file_timestamps={"on" if self.config.timestamp_file_logs else "off"}, '
        f'debug={"on" if self.config.debug else "off"}, '
        f'physical_keys={"on" if self.config.log_physical_keys else "off"}, '
        f'modifier_sides={"on" if self.config.distinguish_modifier_sides else "off"}, '
        f'stdout={"on" if self.config.echo_keys_to_stdout else "off"}, '
        f'wal={"on" if self.config.enable_sqlite_wal else "off"}'
    )
    logging.info(
        'output paths: '
        f'sqlite={self.config.sqlite_file_name}, '
        f'file={self.config.log_file_name}'
    )
    if self.config.uses_sqlite:
      self.setup_sqlite_database()

    with Listener(
        on_press=(lambda key: self.preprocess(key, self.key_down)),
        on_release=(lambda key: self.preprocess(key, self.key_up)),
    ) as listener:
      logging.info('starting to listen for keyboard events')
      listener.join()


def main(argv=None):
  config = parse_args(argv)
  app = KeyLoggerApp(config)
  app.run()


if __name__ == '__main__':
  main()
