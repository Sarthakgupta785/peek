# Testing Peek (beta) — guide for testers

Thanks for helping! Peek runs on **your own computer** and lets **you** check on it from **your
phone**. Nothing you test is sent to the person who invited you — your data stays on your machine.

> **Mac testers:** Peek has been written for macOS but **never run on a Mac before**. Expect a few
> rough edges — finding them is the whole point. Please report anything odd (see the end).

## 1. Install (about 15 minutes)

**Easiest — with Claude Code:** in Claude Code type

```
install https://github.com/Sarthakgupta785/peek
```

Claude follows `skills/install-peek/SKILL.md`. It will stop and ask you to do the few things only
you should do (type your password, paste your ngrok token, click Allow on macOS pop-ups).

**By hand (Mac):**

```bash
git clone https://github.com/Sarthakgupta785/peek.git ~/peek
cd ~/peek
bash setup.sh            # Python environment, password, starts at login
./setup-remote.sh        # phone access: free ngrok account + your Gmail
./setup-2fa.sh           # authenticator-app code at login (recommended)
./set-pin.sh             # PIN for screenshot / camera / power
./screen-key.sh          # end-to-end encryption key - type it into the phone app once
./mac-permissions.sh     # allow Screen Recording + Camera for Peek
```

Needs Python 3.10+ (`brew install python` or python.org) and ngrok (`brew install ngrok/ngrok/ngrok`).

**Windows:** `setup.bat`, then `setup-remote.bat`, `setup-2fa.bat`, `set-pin.bat`, `screen-key.bat`.

## 2. On your phone

1. Open your `https://….ngrok-free.dev` address → **Visit Site** → sign in with Google →
   Peek password (+ 6-digit code).
2. Add to Home Screen (iPhone: Share → Add to Home Screen; Android Chrome: ⋮ → Install app),
   open it from the icon.
3. **Settings → Notifications → Turn on → Send test.**
4. **Settings → Screenshot encryption** → type the key from `screen-key`.

## 3. What to try (tick what works, note what doesn't)

| # | Test | Expected |
|---|---|---|
| 1 | Overview | Name, uptime, CPU/RAM/disk/battery, "someone is using it" vs "idle" |
| 2 | Charts (after ~10 min) | CPU / memory / network lines |
| 3 | Open & close a watched app (e.g. Chrome) | "opened" / "closed (open for X)" alerts on the phone |
| 4 | Actions → Take screenshot | Your screen (Mac: allow Screen Recording first) |
| 5 | Actions → Take camera photo | Webcam photo (Mac: allow Camera); try again during a FaceTime/Zoom call |
| 6 | Lock the computer, then Overview + Take screenshot | "PC is locked"; you get a camera photo instead |
| 7 | **(Mac, experimental)** lock the Mac, type a **wrong** password on the lock screen | Phone alert + "Intruder photos" in Actions |
| 8 | Actions → Restart PC → then **Cancel** within 30 s | Countdown on the computer, cancel works, nothing restarts |
| 9 | Sleep the computer for a few minutes, wake it | "PC woke up, asleep for X" alert |
| 10 | Shut down and start again | "PC turned on" + how it was last shut down |
| 11 | Type a wrong dashboard password | Phone alert with IP + device |
| 12 | Actions → Turn off Peek (needs 2FA code) | Stops; comes back only with `resume-peek` |

## 4. Reporting a problem

Send the invite-er:
- which test number, what you expected, what happened (a screenshot helps);
- your OS version (Mac: Apple menu → About This Mac);
- the last ~50 lines of `guardian.log` in the Peek folder — **check it first** and remove anything
  you consider private (it contains app names, times and IP addresses, never passwords).

**Mac test 7 especially:** in `guardian.log`, lines containing `Mac auth-failure log line` show what
your macOS printed — please include them even if no alert arrived.

## 5. Before an online exam / to uninstall

- Exams (Safe Exam Browser, proctoring): `./pause-peek.sh` (Windows `pause-peek.bat`) before,
  `./resume-peek.sh` after. Peek also steps aside automatically if it sees an exam app.
- Uninstall: `bash uninstall.sh` (Windows: `uninstall.ps1`), then delete the folder.
