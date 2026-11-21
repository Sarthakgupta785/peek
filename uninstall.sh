#!/usr/bin/env bash
# Removes the Peek launch agent (macOS) or systemd user service (Linux). Data is kept.
#   ./uninstall.sh
set -u
if [[ "$(uname -s)" == "Darwin" ]]; then
  LABEL="com.pcguardian.agent"
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && echo "Stopped $LABEL."
  rm -f "$HOME/Library/LaunchAgents/$LABEL.plist" && echo "Removed launch agent."
else
  systemctl --user disable --now pc-guardian.service 2>/dev/null && echo "Stopped pc-guardian service."
  rm -f "$HOME/.config/systemd/user/pc-guardian.service"
  systemctl --user daemon-reload 2>/dev/null || true
fi

echo "Done. Delete this folder to remove everything (the 'data' folder holds your history)."
