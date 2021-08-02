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

import logging
from pynput.keyboard import Key, Listener


# ######### #### ######## ##########
# ######### User Settings ##########
# ######### #### ######## ##########

SEND_LOGS_TO_SQLITE = True
SEND_LOGS_TO_FILE = False

LOG_FILE_NAME = 'key_log.txt'
SQLITE_FILE_NAME = 'key_log.sqlite'

# ######### ####### ##### ##########
# ######### Logging Setup ##########
# ######### ####### ##### ##########

logging.basicConfig(
    # level=logging.DEBUG,
    level=logging.INFO,
    format='%(asctime)s : %(levelname)-5s : %(message)s',
    datefmt='%Y-%m-%d %H%M%S'
)

if SEND_LOGS_TO_SQLITE:
  from datetime import datetime
  import sqlite3

if SEND_LOGS_TO_FILE:
  logging.info(f'File used for logging: {LOG_FILE_NAME}')

# ######### ###### ######### ##########
# ######### Global Variables ##########
# ######### ###### ######### ##########

# This can be changed, but I'm not sure there's much value to tinkering
# with it. You can read more about why it exists in the key_up()
# function.
LOCKED_IN_GARBAGE_COLLECTION_LIMIT = 5

MODIFIER_KEYS = [
    Key.alt,
    Key.ctrl,
    Key.cmd,
    Key.shift,
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

keys_currently_down = []

# ######### ####### ######### ##########
# ######### Logging Functions ##########
# ######### ####### ######### ##########


def setup_sqlite_database():
  """
  This creates the Python objects and the initial table and views in
  the SQLite database (file). It's long, but that's primarily just
  because some of the SQL for the views is long. At it's most basic, it
  is pretty straight forward: (1) connect to the SQLite file, (2) create
  the table for storing key presses, and (3) create the views for looking at
  usage statistics

  If you already have a SQLite key-log (a file with the name
  SQLITE_FILE_NAME), then the results of the session will be APPENDED to
  those. This is accomplished by running a CREATE TABLE IF NOT EXISTS
  statement, as opposed to the more simple CREATE TABLE statement. If
  you want to start from scratch you can (1) delete the existing file
  from your disk (the below will create a new one), (2) rename the
  existing file so you retain that prior sessions' data and a new file
  will be created, or (3) change the name of the file in the
  SQLITE_FILE_NAME variable above and a new one will be created.

  There's a few views that are created, simply as a convenience, that
  will list your usage by key, bigram, and trigram. The main table keeps
  a single row for every key-stroke, which doesn't do much for the
  ultimate goal of understanding your aggregate key usage.
  """
  global db_connection
  global db_cursor
  db_connection = sqlite3.connect(
      SQLITE_FILE_NAME,
      check_same_thread=False,
      # The same thread check is off since the keyboard listener works
      # in a spawned thread (a decision of the pynput library) separate
      # from this python script.
  )
  db_cursor = db_connection.cursor()
  logging.debug('SQLite connection and cursor created')

  db_cursor.execute("""
      CREATE TABLE IF NOT EXISTS key_log
      (time_utc TEXT, key_code TEXT)
  """)
  logging.debug('SQLite logging table created')

  db_cursor.execute('DROP VIEW IF EXISTS key_counts')
  db_cursor.execute("""
    CREATE VIEW IF NOT EXISTS key_counts AS
    WITH frequencies AS (
        SELECT key_code, count(*) AS count,
            (count(*) * 1.0) / (SELECT count(*) FROM key_log) AS frequency
        FROM key_log
        GROUP BY 1
    )
    SELECT *, SUM(frequency) OVER (
        ORDER BY frequency DESC ROWS UNBOUNDED PRECEDING
    ) AS cumulative_frequency
    FROM frequencies
    ORDER BY frequency DESC, key_code
  """)
  logging.debug('SQLite key_counts view created')

  db_cursor.execute('DROP VIEW IF EXISTS bigram_counts')
  db_cursor.execute("""
    CREATE VIEW IF NOT EXISTS bigram_counts AS
    WITH raw_bigram_data AS
    (
      SELECT key_code, lag(key_code) OVER (ORDER BY time_utc) AS key_code_lag_1
      FROM key_log
    )
    , bigram_counts AS
    (
      SELECT key_code_lag_1 || ' ' || key_code AS bigram, count(*) AS count
      FROM raw_bigram_data
      WHERE true
        AND key_code IS NOT NULL
        AND key_code_lag_1 IS NOT NULL
        AND key_code NOT LIKE '%+%'
        AND key_code_lag_1 NOT LIKE '%+%'
      GROUP BY 1
    )
    , bigram_frequencies AS
    (
      SELECT *,
        (1.0* count ) / (SELECT sum(count) FROM bigram_counts) AS frequency
      FROM bigram_counts
    )
    SELECT *, SUM(frequency) OVER (
        ORDER BY frequency DESC ROWS UNBOUNDED PRECEDING
    ) AS cumulative_frequency
    FROM bigram_frequencies
    GROUP BY bigram
    ORDER BY cumulative_frequency, count DESC, bigram
  """)
  logging.debug('SQLite bigram_counts view created')

  db_cursor.execute('DROP VIEW IF EXISTS trigram_counts')
  db_cursor.execute("""
    CREATE VIEW IF NOT EXISTS trigram_counts AS
    WITH raw_trigram_data AS
    (
      SELECT
        key_code,
        lag(key_code) OVER (ORDER BY time_utc) AS key_code_lag_1,
        lag(key_code, 2) OVER (ORDER BY time_utc) AS key_code_lag_2
      FROM key_log
    )
    , trigram_counts AS
    (
      SELECT
        key_code_lag_2 || ' ' || key_code_lag_1 || ' ' || key_code AS trigram,
        count(*) AS count
      FROM raw_trigram_data
      WHERE true
        AND key_code IS NOT NULL
        AND key_code_lag_1 IS NOT NULL
        AND key_code_lag_2 IS NOT NULL
        AND key_code NOT LIKE '%+%'
        AND key_code_lag_1 NOT LIKE '%+%'
        AND key_code_lag_2 NOT LIKE '%+%'
      GROUP BY 1
    )
    , trigram_frequencies AS
    (
      SELECT *,
        (1.0* count ) / (SELECT sum(count) FROM trigram_counts) AS frequency
      FROM trigram_counts
    )
    SELECT *, SUM(frequency) OVER (
        ORDER BY frequency DESC ROWS UNBOUNDED PRECEDING
    ) AS cumulative_frequency
    FROM trigram_frequencies
    GROUP BY trigram
    ORDER BY cumulative_frequency, count DESC, trigram
  """)
  logging.debug('SQLite trigram_counts view created')

  db_connection.commit()
  logging.info(f'SQLite database set up: {SQLITE_FILE_NAME}')


def log(key):
  """
  We're looking to see what modifiers are pressed, in addition to the
  key that triggered the log request, and then want to log that.

  If <shift> alone is the modifier pressed down we don't really need to
  track it when used with a symbol. For example, if you press 'a',
  you'll see that 'a' is logged, and when you press 'shift+a', 'A'
  is logged (similarly '1' and '!'). It's not important that shift
  was used to get there, only the final key, since, when setting up
  your own keyboard, it's possible that you choose to put a symbol,
  like '@' on a layer that doesn't require shift.

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
  modifiers_down = [k for k in keys_currently_down if k in MODIFIER_KEYS]
  if modifiers_down == [Key.shift] and key_is_a_symbol(key):
    modifiers_down = []
  log_entry = ' + '.join(
      sorted([key_to_str(k) for k in modifiers_down])
      + [key_to_str(key)]
  )
  logging.info(f'key: {log_entry}')

  if SEND_LOGS_TO_SQLITE:
    row_values = (datetime.utcnow().isoformat(), log_entry)
    db_cursor.execute(
        'INSERT INTO key_log VALUES (?, ?)',
        row_values
    )
    db_connection.commit()
    logging.debug(f'logged to SQLite: {row_values}')

  if SEND_LOGS_TO_FILE:
    with open(LOG_FILE_NAME, 'a') as log_file:  # append mode
      log_file.write(f'{log_entry}\n')
      logging.debug(f'logged to file: {log_entry}')


# ######### ### ######### ##########
# ######### Key Functions ##########
# ######### ### ######### ##########


def key_is_a_symbol(key):
  return str(key)[0:4] != 'Key.'


def key_to_str(key):
  """
  The string representation pynput's Key.* objects isn't my preferred
  output, so this function standardizes how they're stringified. The
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


def key_down(key):
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
  if key in keys_currently_down:
    return

  keys_currently_down.append(key)
  logging.debug(
      f'key down : {key_to_str(key)} : '
      f'{[key_to_str(k) for k in keys_currently_down]}'
  )
  if key not in MODIFIER_KEYS:
    log(key)


def key_up(key):
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
  global keys_currently_down

  try:
    keys_currently_down.remove(key)
  except ValueError:
    logging.warning(f'{key_to_str(key)} up event without a paired down event')
    if len(keys_currently_down) >= LOCKED_IN_GARBAGE_COLLECTION_LIMIT:
      logging.debug('key-down count is above locked-in limit')
      number_of_modifiers_down = len([
          k for k in keys_currently_down if k in MODIFIER_KEYS
      ])
      if number_of_modifiers_down == 0:
        logging.debug(
            'clearing locked-in keys-down: '
            f'{[key_to_str(k) for k in keys_currently_down]}'
        )
        keys_currently_down = []

  logging.debug(
      f'key up  : {key_to_str(key)} : '
      f'{[key_to_str(k) for k in keys_currently_down]}'
  )


def preprocess(key, f):
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
  k = key
  if key in REMAP:
    k = REMAP[key]
    logging.debug(f'remapped key {key_to_str(key)} -> {key_to_str(k)}')

  if k in IGNORED_KEYS:
    logger.debug(f'ignoring key: {key_to_str(k)}')
    return

  return f(k)


# ######### ######### ##########
# ######### Execution ##########
# ######### ######### ##########


def main():
  logging.info('getting set up')
  if SEND_LOGS_TO_SQLITE:
    setup_sqlite_database()

  with Listener(
      on_press=(lambda key: preprocess(key, key_down)),
      on_release=(lambda key: preprocess(key, key_up)),
  ) as listener:
    logging.info('starting to listen for keyboard events')
    listener.join()


if __name__ == '__main__':
  main()
