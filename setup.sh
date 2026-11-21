#!/usr/bin/env bash
# Peek setup for macOS (launchd) and Linux desktops (systemd --user).
#   ./setup.sh              normal interactive setup
#   ./setup.sh --no-prompt  skip the password question (set it later with ./set-password.sh)
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
chmod +x ./*.sh 2>/dev/null || true
NOPROMPT=""
[[ "${1:-}" == "--no-prompt" ]] && NOPROMPT=1
OS="$(uname -s)"

echo
echo "=== Peek setup ($OS) ==="
echo

# ---- 1. Python 3.10+
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY="$c"; break
  fi
done
if [[ -z "$PY" ]]; then
  echo "Python 3.10+ not found."
  [[ "$OS" == "Darwin" ]] && echo "Install it from https://www.python.org/downloads/macos/ (or: brew install python), then run ./setup.sh again."
  [[ "$OS" == "Linux" ]] && echo "Install it with your package manager (e.g. sudo apt install python3 python3-venv), then run ./setup.sh again."
  exit 1
fi

# ---- 2. Virtual environment + packages
if [[ ! -x .venv/bin/python ]]; then
  echo "Creating virtual environment..."
  "$PY" -m venv .venv
fi
echo "Installing packages (this can take a minute)..."
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt

# ---- 3. Dashboard password
if .venv/bin/python guardian.py --has-password; then
  echo "A dashboard password is already set. Run ./set-password.sh to change it."
elif [[ -n "$NOPROMPT" ]]; then
  echo "NOTE: no dashboard password yet. Run ./set-password.sh to choose one."
else
  .venv/bin/python guardian.py --set-password
fi

# ---- 4. Start at log in
if [[ "$OS" == "Darwin" ]]; then
  LABEL="com.pcguardian.agent"
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/.venv/bin/python</string>
    <string>$ROOT/guardian.py</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>ProcessType</key><string>Interactive</string>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
  <key>StandardOutPath</key><string>/dev/null</string>
  <key>StandardErrorPath</key><string>/dev/null</string>
</dict>
</plist>
EOF
  launchctl enable "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  STARTED=""
  for _ in 1 2 3 4 5 6 7 8; do        # bootout can take a moment to finish
    if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then STARTED=1; break; fi
    sleep 1
  done
  if [[ -z "$STARTED" ]]; then
    echo "macOS could not start Peek. Sign out and back in, then run: bash setup.sh"
    exit 1
  fi
  echo "Registered launch agent $LABEL (starts when you log in, restarts if it stops)."
  echo
  echo "macOS will ask for permission the first time you take a screenshot:"
  echo "  System Settings > Privacy & Security > Screen Recording > allow 'python'."
else
  UNIT_DIR="$HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/pc-guardian.service" <<EOF
[Unit]
Description=Peek
After=network-online.target

[Service]
WorkingDirectory=$ROOT
ExecStart=$ROOT/.venv/bin/python $ROOT/guardian.py
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now pc-guardian.service
  echo "Registered systemd user service pc-guardian (starts when you log in)."
fi

# ---- 5. Tailscale
PORT="$(.venv/bin/python -c 'from pcguardian import config; print(config.load()["port"])')"
TS=""
if command -v tailscale >/dev/null 2>&1; then TS="tailscale"
elif [[ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]]; then TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
fi
echo
echo "--- Phone access with Tailscale (free) ---"
if [[ -z "$TS" ]]; then
  echo "Tailscale is not installed yet. To finish:"
  echo " 1. Install Tailscale on this computer: https://tailscale.com/download and sign in."
  echo " 2. In https://login.tailscale.com/admin/dns turn on MagicDNS and HTTPS Certificates."
  echo " 3. Run ./setup.sh again (or: tailscale serve --bg $PORT)."
  echo " 4. Install Tailscale on your phone and sign in with the same account."
else
  if "$TS" serve --bg "$PORT"; then
    DNS="$("$TS" status --json 2>/dev/null | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"
    [[ -n "$DNS" ]] && echo "Open this on your phone (with Tailscale on):  https://$DNS"
  else
    echo "tailscale serve failed. Sign in, enable MagicDNS + HTTPS Certificates in the admin console, then run:"
    echo "   $TS serve --bg $PORT"
  fi
fi

echo
echo "=== Done ==="
echo "Local test address (this computer only): http://127.0.0.1:$PORT"
echo "Logs: $ROOT/guardian.log"
echo
echo "Next steps:"
echo "  1. Remote access from your phone:  ./setup-remote.sh"
echo "  2. Extra locks (recommended):      ./setup-2fa.sh   ./set-pin.sh   ./screen-key.sh"
if [[ "$OS" == "Darwin" ]]; then
  echo "  3. Allow screen + camera on macOS: ./mac-permissions.sh"
fi
echo "  Before an online exam:            ./pause-peek.sh   (after:  ./resume-peek.sh)"
