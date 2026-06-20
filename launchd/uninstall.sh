#!/bin/sh
#
# uninstall.sh -- stop and remove the benign-key-logger LaunchAgent.
#
# It unloads the agent and deletes the installed plist. It does NOT delete your
# captured data (the SQLite database is left exactly where it is), and it does
# not change any System Settings permissions.

set -eu

LABEL="local.benign-key-logger"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

# Unload if currently loaded (ignore the error if it is not).
launchctl bootout "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null || true

if [ -f "$PLIST_DEST" ]; then
  rm -f "$PLIST_DEST"
  echo "Removed $PLIST_DEST and unloaded $LABEL."
else
  echo "$LABEL was not installed (no plist at $PLIST_DEST); nothing to remove."
fi

echo ""
echo "Your captured data was left untouched."
echo "To fully revoke keyboard access, remove the python interpreter from"
echo "System Settings > Privacy & Security > Input Monitoring (and Accessibility)."
