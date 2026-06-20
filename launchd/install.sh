#!/bin/sh
#
# install.sh -- generate and load the benign-key-logger macOS LaunchAgent so the
# logger starts automatically at login.
#
# What it does, in plain terms (read before running):
#   1. Fills the absolute paths into the .plist.template next to this script.
#   2. Writes the result to ~/Library/LaunchAgents/<Label>.plist.
#   3. Validates it with `plutil -lint`.
#   4. Loads it with `launchctl bootstrap` (and unloads any previous copy first).
#
# It does NOT touch key_logger.py, does NOT grant any permission for you, and
# sends nothing anywhere. Re-running it is safe (idempotent re-install).
#
# Override the interpreter with PYTHON_OVERRIDE=/path/to/python if your env
# lives somewhere other than the default conda location below.

set -eu

# --- Configuration (edit if you want a different label) ---------------------
LABEL="local.benign-key-logger"
DEFAULT_PYTHON="$HOME/opt/miniconda3/envs/keylogger/bin/python"

# --- Resolve locations ------------------------------------------------------
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
TEMPLATE="$SCRIPT_DIR/$LABEL.plist.template"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/benign-key-logger"
DB="$REPO_DIR/key_log.sqlite"

PYTHON="${PYTHON_OVERRIDE:-$DEFAULT_PYTHON}"

# --- Sanity checks ----------------------------------------------------------
if [ ! -f "$TEMPLATE" ]; then
  echo "error: template not found at $TEMPLATE" >&2
  exit 1
fi
if [ ! -x "$PYTHON" ]; then
  echo "error: python interpreter not found/executable at: $PYTHON" >&2
  echo "       set PYTHON_OVERRIDE=/path/to/python and re-run." >&2
  exit 1
fi

# The TCC (Input Monitoring / Accessibility) grant attaches to the RESOLVED real
# binary, not the symlink we invoke -- report that path so the user grants the
# right thing.
REAL_PYTHON=$("$PYTHON" -c 'import os, sys; print(os.path.realpath(sys.executable))')

# --- Generate the concrete plist from the template --------------------------
# Fill the template with plutil (already used for -lint below), NOT raw sed.
# plutil writes through the plist serializer, so values containing characters
# that are significant to XML or to sed (& < > " | \) are stored literally and
# escaped correctly -- raw `sed` substitution would corrupt the XML or mangle
# the replacement on such a path. Scalars go in by key; the whole
# ProgramArguments array is replaced in one shot via a JSON value built by the
# resolved interpreter, so every argv element is escaped safely too. (Note:
# `plutil -replace ProgramArguments.<N>` would INSERT at N, not overwrite it.)
mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
cp "$TEMPLATE" "$PLIST_DEST"
chmod 0644 "$PLIST_DEST"

plutil -replace Label             -string "$LABEL"                    "$PLIST_DEST"
plutil -replace WorkingDirectory  -string "$REPO_DIR"                 "$PLIST_DEST"
plutil -replace StandardOutPath   -string "$LOG_DIR/launchd.out.log"  "$PLIST_DEST"
plutil -replace StandardErrorPath -string "$LOG_DIR/launchd.err.log"  "$PLIST_DEST"

PA_JSON=$("$PYTHON" -c 'import json, sys; print(json.dumps([sys.argv[1], sys.argv[2], "--sqlite-file", sys.argv[3]]))' \
  "$PYTHON" "$REPO_DIR/key_logger.py" "$DB")
plutil -replace ProgramArguments -json "$PA_JSON" "$PLIST_DEST"

# A mistyped keypath would leave a placeholder behind that `plutil -lint` still
# accepts (it's valid XML), shipping a broken agent silently. Fail loud instead.
if grep -q '__[A-Z_]*__' "$PLIST_DEST"; then
  echo "error: unsubstituted placeholder remains in $PLIST_DEST" >&2
  exit 1
fi

# --- Validate ---------------------------------------------------------------
plutil -lint "$PLIST_DEST"

# --- (Re)load ---------------------------------------------------------------
# Unload any previous copy first so this is a clean, repeatable install.
launchctl bootout "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"

# --- Report + the one manual step we cannot do for you ----------------------
echo ""
echo "Installed and loaded: $LABEL"
echo "  plist : $PLIST_DEST"
echo "  db    : $DB"
echo "  logs  : $LOG_DIR/launchd.{out,err}.log"
echo ""
echo "REQUIRED MANUAL STEP -- grant keyboard access, or it captures nothing:"
echo "  System Settings > Privacy & Security > Input Monitoring  (and, if that"
echo "  alone does not work, also Accessibility) > click '+' > press Cmd+Shift+G"
echo "  and paste this exact path, then enable the toggle:"
echo ""
echo "    $REAL_PYTHON"
echo ""
echo "macOS does NOT prompt for this automatically when launchd starts the agent,"
echo "and pynput fails silently without it. Verify capture by typing for a bit,"
echo "then checking the database grows:"
echo "  sqlite3 \"$DB\" \"SELECT COALESCE(SUM(count),0) FROM key_counts_agg;\""
echo ""
echo "Status:   launchctl print \"gui/$(id -u)/$LABEL\""
echo "Stop it:  sh \"$SCRIPT_DIR/uninstall.sh\""
