# Peek

Self-hosted dashboard + phone push alerts for a Windows/macOS/Linux computer, reached via ngrok (with Google sign-in) or Tailscale. Beta testers: see TESTING.md.

- **Installing, updating, checking or uninstalling for a user:** follow
  [skills/install-peek/SKILL.md](skills/install-peek/SKILL.md) exactly. Never ask for or
  type the dashboard password - the user runs `set-password.bat` / `./set-password.sh` themselves.
- Entry point: `guardian.py`. Package: `pcguardian/` (`monitor.py` background loops, `web.py` FastAPI,
  `push.py` Web Push, `auth.py` scrypt + sessions, `platforms/` per-OS code with one shared interface).
- Frontend: `static/` - plain HTML/CSS/JS PWA, no build step. CSP forbids inline scripts/styles.
- Private files never committed: `config.json`, `data/` (SQLite, VAPID key), `guardian.log`.
- Run in a console for development: `python guardian.py` (logs to the console and `guardian.log`).
