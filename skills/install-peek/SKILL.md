---
name: install-peek
description: Install, update, check or uninstall Peek (self-hosted dashboard + phone alerts for a Windows/Mac/Linux computer, reached through Tailscale). Use when the user says "install Peek", "install <github link to pc-guardian>", "set up Peek", "update Peek", "Peek isn't working", or "uninstall Peek".
---

# Install Peek

Peek runs on the user's own computer, records system stats and events in a local SQLite file,
and serves a password-protected dashboard on `127.0.0.1:8765`. The phone reaches it privately through
`tailscale serve` (HTTPS), and alerts arrive as Web Push notifications. Everything is free.

Work through the steps in order, telling the user in one line what each step is doing. Use the
shell that fits the OS (PowerShell on Windows, bash on macOS/Linux).

## Rules

- **Never ask for, read, or type the dashboard password.** The user sets it themselves in their own
  terminal (step 5). Don't put it in a command, file, or chat message.
- Ask before installing anything system-wide (Python, Tailscale, Docker). The setup scripts only touch
  the project folder, plus one start-at-login entry for the current user.
- If other people use this computer, remind the user once that they should be told it's monitored.

## 1. Get the code

- If the current folder already contains `guardian.py` and `pcguardian/`, use it.
- Otherwise clone the repo the user gave (or this plugin's repo) into a folder they agree to. Suggest
  `%USERPROFILE%\pc-guardian` on Windows and `~/peek` on macOS/Linux:
  `git clone <repo-url> <folder>`. If `git` is missing, download the repo's ZIP from GitHub instead.
- Updating an existing install: `git pull` in that folder, then re-run the setup script (step 4); it
  keeps the password, data and config.

## 2. Pick the install type

| Computer | Install | Notes |
|---|---|---|
| Windows 10/11 | `setup.bat` | Task Scheduler "At log on", `pythonw.exe`, no console window |
| macOS 12+ | `setup.sh` | launchd LaunchAgent in `~/Library/LaunchAgents` |
| Linux desktop | `setup.sh` | systemd `--user` service |
| Linux server / NAS / Pi | Docker (step 4b) | no screenshots, lock or idle detection |

Do **not** use Docker on Windows or macOS: Docker Desktop runs containers in a Linux VM that can't see
the host's apps, screen or input, so the app would only report on the VM.

## 3. Check Python

Needs Python 3.10+ (3.12+ recommended).
- Windows: `py -3 --version` or `python --version`. If missing, ask the user to install it from
  https://www.python.org/downloads/ with "Add python.exe to PATH" ticked (or `winget install Python.Python.3.12`
  if they agree).
- macOS: `python3 --version`. If missing/old: https://www.python.org/downloads/macos/ or `brew install python`.
- Linux: `python3 --version` and the `python3-venv` package.

## 4. Run setup (non-interactive)

- Windows (PowerShell, in the project folder): `cmd /c setup.bat --no-prompt`
- macOS/Linux: `bash setup.sh --no-prompt`

The script creates `.venv`, installs `requirements.txt`, registers start-at-login, starts the app, and
runs `tailscale serve --bg 8765` if Tailscale is installed. Read its output and fix any error before
going on. If Windows says the task couldn't be registered, ask the user to run `setup.bat` once from
an Administrator terminal.

### 4b. Docker (Linux hosts only)

```bash
docker compose up -d --build
```
Then in step 5 the password command is `docker compose exec guardian python guardian.py --set-password`.

## 5. Dashboard password (the user does this)

Tell the user to open **their own terminal window** in the project folder and run:
- Windows: `set-password.bat` (or double-click it in Explorer)
- macOS/Linux: `./set-password.sh`

It asks for the password twice with hidden typing (8+ characters). Wait until they say it's done,
then confirm without seeing it:
- Windows: `.venv\Scripts\python.exe guardian.py --has-password` (exit code 0 = set)
- macOS/Linux: `.venv/bin/python guardian.py --has-password`

## 6. Verify it's running

- Fetch `http://127.0.0.1:8765/login` (e.g. `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/login`,
  or `Invoke-WebRequest` on Windows). Expect `200`.
- If not, read the last 50 lines of `guardian.log` in the project folder and fix the cause.
  Common ones: port 8765 in use (change `port` in `config.json`, re-run setup), missing packages
  (re-run setup), "Another copy is already running" (fine - it's already up).
- macOS: tell the user to run `./mac-permissions.sh` in their own Terminal. It opens Privacy &
  Security pages: allow Screen Recording (screenshots), Camera (photos) and Automation → System Events
  (shutdown/restart). macOS also shows Allow pop-ups the first time each feature is used.

## 7. Phone access

Two options; ask which the user prefers.

**A. ngrok (default — nothing to install on the phone).** Check ngrok is installed (`ngrok version`);
if not, ask before installing: macOS `brew install ngrok/ngrok/ngrok`, Windows
`winget install Ngrok.Ngrok` then `ngrok update`. Then the user runs, **in their own terminal**
(it asks for the ngrok token with hidden input — never ask for the token in chat):
- macOS/Linux: `./setup-remote.sh`   Windows: `setup-remote.bat`

It asks for: the authtoken (dashboard.ngrok.com → Your Authtoken), their free domain
(dashboard.ngrok.com → Domains), and the Gmail address(es) allowed past Google sign-in. It saves
`config.json` and restarts Peek. Verify: `curl -s -o /dev/null -w "%{http_code}" -H "ngrok-skip-browser-warning: 1" https://<domain>/about`
→ `200`, and `https://<domain>/` → `302` (Google sign-in in front).

**B. Tailscale (most private).** Check `tailscale` (Windows: `C:\Program Files\Tailscale\tailscale.exe`;
macOS App Store: `/Applications/Tailscale.app/Contents/MacOS/Tailscale`). User installs it from
https://tailscale.com/download, signs in, enables MagicDNS + HTTPS Certificates at
https://login.tailscale.com/admin/dns; then run `tailscale serve --bg 8765` and read `Self.DNSName`
from `tailscale status --json`.

## 8. Extra locks (recommended) — the user runs these in their own terminal

- `setup-2fa` (.bat/.sh): authenticator-app code at every login. Shows a QR code; they type one code.
- `set-pin` (.bat/.sh): PIN for screenshot, camera, power actions.
- `screen-key` (.bat/.sh): end-to-end key for screenshots/photos; they type it into the phone app
  (Settings → Screenshot encryption). Never read their terminal output back: it shows secrets.

## 9. Finish on the phone

1. Open the address (ngrok: tap **Visit Site**, then Google sign-in), log in.
2. Add to Home Screen (iPhone: Share → Add to Home Screen; iOS 16.4+. Android Chrome: ⋮ → Install app).
3. Open from the icon → Settings → Notifications → Turn on → Send test.

Exams: tell students to run `pause-peek` before Safe Exam Browser / proctored exams and
`resume-peek` after. Testers: point them to `TESTING.md`.

## Uninstall

- Windows: `powershell -ExecutionPolicy Bypass -File uninstall.ps1` (add `-ResetTailscale -Yes` only if
  the user wants all `tailscale serve` settings removed).
- macOS/Linux: `bash uninstall.sh` (or `bash uninstall.sh --reset-tailscale`).
- Docker: `docker compose down`.
Ask before deleting the project folder: its `data/` folder holds the history, sessions and push keys.
