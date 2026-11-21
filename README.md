# Peek

See what your computer is doing from your phone, especially while you're away. Get an alert when it
turns on, wakes up, or when someone opens WhatsApp, or types the wrong dashboard password.

- **Free.** Python, Tailscale's free Personal plan and the browser's own push service.
- **Private.** It runs on your computer, the data stays in a SQLite file there, and the dashboard
  is only reachable on your own Tailscale network.
- **Windows, macOS and Linux.** Docker works for Linux servers.

> If other people use this computer, tell them it's monitored.

> **New here?** Follow the easy [install guide](INSTALL.md).
> **Beta testers:** after installing, use [TESTING.md](TESTING.md).
> **Claude Code / AI assistants installing this:** follow [skills/install-peek/SKILL.md](skills/install-peek/SKILL.md).

## What it does (v1)

| | |
|---|---|
| **Overview** | Computer name, uptime, "someone is using it now" or "idle for X", CPU, RAM, disk and battery, top 5 apps by memory, which watched apps are open |
| **Charts** | CPU, RAM and network for the last 6 hours, 24 hours or 7 days (sampled every 30 seconds) |
| **Timeline** | Every event, newest first |
| **Actions** | Screenshot of all monitors, lock the screen |
| **Settings** | Edit the watched apps, search running processes, turn phone notifications on or off |
| **Alerts** | Turned on (plus how it was last shut down: normal, restart by whom, or power cut/crash), woke from sleep (and how long it slept), watched app opened or closed, wrong password, new login |

Idle detection only reads *the time since* the last key press or mouse move. It never records what
was typed.

### Feature support by platform

| Feature | Windows | macOS | Linux desktop | Docker (Linux) |
|---|:-:|:-:|:-:|:-:|
| Stats, charts, watched apps, wake and boot alerts, push | ✅ | ✅ | ✅ | ✅ |
| Idle detection | ✅ | ✅ | — | — |
| Camera photo / intruder photos | ✅ | ✅ (intruder photos experimental) | — | — |
| Shut down / restart (with cancel) | ✅ | ✅ | — | — |
| Secrets encrypted at rest | ✅ DPAPI | ✅ Keychain | — | — |
| Screenshot | ✅ | ✅ (needs Screen Recording permission) | — | — |
| Lock screen | ✅ | ✅ (sleeps the display) | — | — |
| Why it last shut down | ✅ (Event Log) | ✅ (shutdown cause) | — | — |

**Why not Docker on Windows or Mac?** Docker Desktop runs containers inside a hidden Linux VM. A
container there sees the VM, not your computer, so it can't see your apps, screen or keyboard
activity. Use the normal install on those systems.

---

## Install with Claude Code (easiest)

In Claude Code, type:

```
install https://github.com/Sarthakgupta785/peek
```

Claude clones the repo and follows [the install skill](skills/install-peek/SKILL.md). It
will ask you to type the dashboard password yourself in a terminal window. Claude never sees it.

You can also add it as a plugin so "install Peek", "update Peek" and "Peek
isn't working" work from any folder:

```
/plugin marketplace add Sarthakgupta785/peek
/plugin install peek@peek
```

---

## Install by hand

### 1. Install Python

- **Windows:** download Python 3.12 or newer from <https://www.python.org/downloads/>. On the first
  installer screen, tick **"Add python.exe to PATH"**.
- **macOS:** get it from <https://www.python.org/downloads/macos/>, or run `brew install python`.
- **Linux:** `sudo apt install python3 python3-venv` (or your distro's equivalent).

### 2. Install Tailscale on the computer and on your phone

1. Install Tailscale from <https://tailscale.com/download> on the computer and on your phone. Sign
   in to both with the **same** account. The Personal plan is free.
2. Open <https://login.tailscale.com/admin/dns>. Turn on **MagicDNS**, then **HTTPS Certificates**.
   Phone notifications need HTTPS.

### 3. Download Peek and run setup

Download this repo (green **Code** button, then **Download ZIP**) and unzip it somewhere permanent,
for example `C:\pc-guardian` or `~/peek`.

- **Windows:** double-click **`setup.bat`**.
- **macOS / Linux:** open Terminal in the folder and run `bash setup.sh`.

Setup does these steps:
1. Creates a private Python environment (`.venv`) and installs the packages.
2. Asks you to choose a **dashboard password**, typed twice.
3. Makes Peek start when you log in, with no window, and restart if it stops:
   - **Windows:** a Task Scheduler task named "Peek".
   - **macOS:** a LaunchAgent (`~/Library/LaunchAgents/com.pcguardian.agent.plist`).
   - **Linux:** a systemd user service (`pc-guardian`).
4. Runs `tailscale serve --bg 8765` and prints your phone address, which looks like
   `https://my-pc.tail1234.ts.net`.

If Windows says it couldn't register the task, right-click `setup.bat` and choose **Run as
administrator**.

### 4. Open it on your phone

1. Make sure Tailscale is on, on the phone.
2. Open the `https://….ts.net` address and log in.
3. **Add to Home Screen:**
   - **iPhone:** in Safari, tap Share, then **Add to Home Screen**. Needs iOS 16.4 or newer.
     Notifications only work from the home-screen icon.
   - **Android (Chrome):** tap ⋮, then **Install app** or **Add to Home screen**.
4. Open Peek from the home-screen icon. Go to **Settings → Notifications → Turn on**, then
   tap **Send test**.

### Alternative: ngrok instead of Tailscale (nothing to install on the phone)

ngrok puts the dashboard on a public HTTPS address, and Google sign-in limited to your Gmail
stands in front of it. Anyone can find a public address, so use every layer:

1. Create a free account at <https://dashboard.ngrok.com/signup> and install ngrok
   (`winget install Ngrok.Ngrok`, then `ngrok update`; on a Mac, `brew install ngrok`).
2. Run `ngrok-token.bat` and paste your authtoken. Keep the token out of chats and files.
3. Copy your free dev domain from <https://dashboard.ngrok.com/domains>, then edit `config.json`:
   ```json
   "ngrok": { "enabled": true, "url": "https://your-domain.ngrok-free.dev",
              "allowed_emails": ["you@gmail.com"], "exe": "" }
   ```
4. Restart Peek. It starts ngrok itself, with no window, and restarts it if it stops.
5. Turn on the other locks: `setup-2fa.bat` (authenticator-app code at login), `set-pin.bat` (PIN
   for screenshot/lock) and a strong password (`set-password.bat`).

Free ngrok shows a one-time "You are about to visit…" page. Tap **Visit Site**, sign in with your
Google account, then log in to Peek.

### Docker (Linux servers only)

```bash
docker compose up -d --build
docker compose exec guardian python guardian.py --set-password
tailscale serve --bg 8765        # on the host
```

The compose file uses `network_mode: host` and `pid: host`, so the container sees the host's
network and processes. Data is kept in `./data`.

---

## Camera, intruder photos and exams (Windows)

- **Take camera photo** (Actions, needs your PIN): one webcam photo, end-to-end encrypted. If
  another app (Zoom, Teams…) has the camera, Peek reads it in Windows' shared mode; if even that
  fails, it sends a screenshot and says why.
- **Intruder photos:** a wrong password/PIN on the Windows lock screen triggers webcam photos and
  a phone alert. One-time setup: right-click `enable-intruder-photos.bat` → Run as administrator,
  then sign out and back in.
- **Online exams (Safe Exam Browser, proctoring):** before an exam run `pause-peek.bat` (or
  Actions → **Turn off Peek**, which asks for your authenticator code). Nothing of Peek or ngrok
  keeps running, even after a restart, until you run `resume-peek.bat` on the PC.
  As a safety net, if an exam app starts while Peek is running, Peek switches ngrok off and
  refuses screenshots/camera until it closes ("exam mode").

## Everyday use

| Task | Windows | macOS / Linux |
|---|---|---|
| Change password | `set-password.bat` | `./set-password.sh` |
| See logs | `guardian.log` in the folder | same |
| Run in a console (debug) | `.venv\Scripts\python guardian.py` | `.venv/bin/python guardian.py` |
| Uninstall | `powershell -ExecutionPolicy Bypass -File uninstall.ps1` | `bash uninstall.sh` |
| Update | `pause-peek.bat`, `git pull`, then `setup.bat` | `git pull`, `bash resume-peek.sh`, `bash setup.sh` on Mac (Linux: see [TESTING.md](TESTING.md)) |

Changing the password logs out every device.

### `config.json`

This file is created on the first run. Edit it, then restart Peek. On Windows, restart the
"Peek" task in Task Scheduler, or log out and back in.

| Key | Default | Meaning |
|---|---|---|
| `port` | `8765` | Local port. If you change it, also run `tailscale serve --bg <port>` |
| `watched_apps` | per OS | Apps that send open/close alerts. You can also edit this list in Settings |
| `metrics_interval_seconds` | `30` | How often stats are saved |
| `process_poll_seconds` | `3` | How often watched apps are checked |
| `startup_delay_seconds` | `20` | Wait time after boot before monitoring starts |
| `metrics_retention_days` / `events_retention_days` | `30` / `180` | How long history is kept |
| `startup_notice` | `true` | Shows "This PC is monitored" after sign-in (never during an exam app) |
| `push_contact` | `mailto:pc-guardian@example.com` | Contact sent to push services (VAPID). Your own email is fine |

**How app names match:** `whatsapp` matches `WhatsApp.exe` and `WhatsApp.Root.exe`. `chrome`
matches `chrome.exe` but **not** `chromedriver.exe`. On a Mac, names are like `google chrome` and
`safari`. To find the exact name, use **Settings → Find a running app**.

## Security

- The server listens on `127.0.0.1` only. Your devices reach it only through `tailscale serve`, over
  HTTPS and only inside your tailnet.
- The password is stored as a salted scrypt hash. Sessions use an HttpOnly, Secure, SameSite=Strict
  cookie, so your phone stays logged in across reboots.
- After 5 wrong passwords, logins lock for 5 minutes, and you get a push alert about each wrong try.
- `config.json`, `data/` (database and VAPID private key) and `guardian.log` are in `.gitignore`.
  Never commit them.

## Known limits

- **Windows Fast Startup:** a "shut down" with Fast Startup on is really hibernation. The boot time
  doesn't reset, so you get "Peek started (wasn't running for X)" instead of "PC turned on".
- Shutting down can't be alerted while it happens. You find out how it shut down on the next start.
- iPhone notifications need iOS 16.4+ and the home-screen app.
- Charts load Chart.js from a public CDN (jsDelivr). Only the library is downloaded. None of your
  data is sent.

## Roadmap

- **v2: analytics.** Daily and weekly reports, screen time per app, data usage per day, uptime history.
- **v3: away mode.** Flag any activity while you're away. Webcam photo on a failed Windows login.
  Alerts for USB devices, new Wi-Fi networks, unknown devices on Wi-Fi, changes in chosen folders,
  and new apps or startup programs.
- **v4: extras.** A local AI "while you were away" summary (Ollama), health score, SMART disk
  warnings, speed log, battery wear, remote shutdown, kill an app, volume control, short screen
  recordings, Wake-on-LAN, CSV export, several computers in one dashboard.

## License

MIT. See [LICENSE](LICENSE).
