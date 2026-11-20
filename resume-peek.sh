#!/usr/bin/env bash
# Start Peek again after it was turned off (dashboard or pause-peek.sh).
if [[ "$(uname -s)" == "Darwin" ]]; then
  L="gui/$(id -u)/com.pcguardian.agent"
  launchctl enable "$L"
  launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.pcguardian.agent.plist" 2>/dev/null || launchctl kickstart -k "$L"
else
  systemctl --user enable --now pc-guardian.service
fi
echo "Peek is running again."
