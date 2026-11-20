#!/usr/bin/env bash
# Stop Peek and ngrok completely (e.g. before an online exam). Undo: ./resume-peek.sh
if [[ "$(uname -s)" == "Darwin" ]]; then
  L="gui/$(id -u)/com.pcguardian.agent"
  launchctl disable "$L"; launchctl bootout "$L" 2>/dev/null
else
  systemctl --user disable --now pc-guardian.service
fi
pkill -f "ngrok-policy.yml" 2>/dev/null
echo "Peek is PAUSED until you run ./resume-peek.sh"
