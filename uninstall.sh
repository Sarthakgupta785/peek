#!/usr/bin/env bash
# Removes the Peek launch agent (macOS) or systemd user service (Linux). Data is kept.
#   ./uninstall.sh [--reset-tailscale]
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

RESET="${1:-}"
if [[ "$RESET" != "--reset-tailscale" && -t 0 ]]; then
  read -r -p "Also run 'tailscale serve reset'? This removes ALL tailscale serve settings (y/N) " a
  [[ "$a" =~ ^[yY] ]] && RESET="--reset-tailscale"
fi
if [[ "$RESET" == "--reset-tailscale" ]]; then
  TS="$(command -v tailscale || echo /Applications/Tailscale.app/Contents/MacOS/Tailscale)"
  "$TS" serve reset && echo "tailscale serve reset done."
fi
echo "Done. Delete this folder to remove everything (the 'data' folder holds your history)."
