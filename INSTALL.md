# Install Peek: the easy guide

Peek lets you check on **your own computer** from **your phone**. It's free and takes about **20 minutes**.

Your data stays on your computer. Nobody else, including the person who shared Peek with you, can see it.

> If other people use this computer, tell them it is monitored.

---

## Before you start

Have these ready:

- [ ] Your computer and phone
- [ ] A **Google account**
- [ ] A free **ngrok account**: [sign up here](https://dashboard.ngrok.com/signup) with "Continue with Google"
- [ ] **Google Authenticator** or **Microsoft Authenticator** installed on your phone

---

## Easiest way: let Claude Code do it

Open Claude Code and paste:

```
install https://github.com/Sarthakgupta785/peek
```

Claude installs Peek and tells you exactly what to do next, one step at a time. You will only need to type your own passwords and click **Allow** when asked.

**Prefer to do it yourself?** Follow the steps for your computer below.

---

## Install on Mac

### Step 1: Install the tools

Open **Terminal** (press `Cmd + Space`, type `Terminal`, press Enter), then paste:

```bash
brew install python ngrok/ngrok/ngrok
```

If it says `brew: command not found`, install [Homebrew](https://brew.sh) first, then run the line again.

### Step 2: Download Peek

1. Open [the Peek page](https://github.com/Sarthakgupta785/peek).
2. Click the green **Code** button, then **Download ZIP**.
3. Open the ZIP from Downloads.
4. Rename the new folder from `peek-main` to `peek`.
5. Move it into your **Home** folder (the one with your name).

### Step 3: Set up Peek

Paste these in Terminal:

```bash
cd ~/peek
bash setup.sh
```

Choose a **dashboard password** when asked. Nothing appears while you type; that's normal. You can ignore any message about Tailscale.

### Step 4: Connect your phone

```bash
./setup-remote.sh
```

It asks for three things:

1. **Token:** copy it from [your ngrok token page](https://dashboard.ngrok.com/get-started/your-authtoken).
2. **Domain:** copy it from [your ngrok domains page](https://dashboard.ngrok.com/domains).
3. **Gmail:** the Google account you will use on your phone.

### Step 5: Add the security locks

Run these one at a time:

```bash
./setup-2fa.sh
```

Scan the QR code with your authenticator app, then type the 6-digit code.

```bash
./set-pin.sh
```

Choose a 4 to 8 digit PIN.

```bash
./screen-key.sh
```

Keep this window open. You will type this key into your phone in the last step.

### Step 6: Allow screen and camera

```bash
./mac-permissions.sh
```

Follow what it says on screen, and click **Allow** whenever macOS asks.

Now go to **[Finish on your phone](#finish-on-your-phone)**.

---

## Install on Windows

### Step 1: Install the tools

1. Install [Python](https://www.python.org/downloads/). On the first screen, tick **Add python.exe to PATH**.
2. Open **PowerShell** from the Start menu and paste:

   ```powershell
   winget install Ngrok.Ngrok
   ```

3. **Close PowerShell, open it again**, and paste:

   ```powershell
   ngrok update
   ```

### Step 2: Download Peek

1. Open [the Peek page](https://github.com/Sarthakgupta785/peek).
2. Click the green **Code** button, then **Download ZIP**.
3. Right-click the ZIP and choose **Extract All**.
4. Rename the new folder from `peek-main` to `peek`.
5. Move it somewhere permanent, like `C:\peek`.

### Step 3: Set up Peek

Open the `peek` folder and double-click **`setup.bat`**.

Choose a **dashboard password** when asked. Nothing appears while you type; that's normal. You can ignore any message about Tailscale.

If it can't create the startup task, right-click `setup.bat` and choose **Run as administrator**.

### Step 4: Connect your phone

Double-click **`setup-remote.bat`**. It asks for three things:

1. **Token:** copy it from [your ngrok token page](https://dashboard.ngrok.com/get-started/your-authtoken). Right-click pastes it.
2. **Domain:** copy it from [your ngrok domains page](https://dashboard.ngrok.com/domains).
3. **Gmail:** the Google account you will use on your phone.

### Step 5: Add the security locks

Double-click these one at a time:

1. **`setup-2fa.bat`**: scan the QR code with your authenticator app, then type the 6-digit code.
2. **`set-pin.bat`**: choose a 4 to 8 digit PIN.
3. **`screen-key.bat`**: keep this window open. You will type this key into your phone in the last step.

### Step 6 (optional): Turn on intruder photos

Right-click **`enable-intruder-photos.bat`**, choose **Run as administrator**, then sign out of Windows and back in.

Now continue below.

---

## Finish on your phone

1. Open your `https://....ngrok-free.dev` address. Use **Safari** on iPhone or **Chrome** on Android.
2. Tap **Visit Site**, sign in with Google, then enter your Peek password and 6-digit code.
3. Add Peek to your home screen:
   - **iPhone:** tap Share, then **Add to Home Screen**.
   - **Android:** tap the three dots, then **Install app**.
4. **Open Peek from the new icon** and sign in again if asked.
5. Go to **Settings**, then **Notifications**, tap **Turn on**, then **Send test**.
6. In **Settings**, then **Screenshot encryption**, type your key and save it.

**You're done.** Peek now starts by itself whenever you sign in to your computer.

---

## Everyday use

| I want to | On Mac | On Windows |
|---|---|---|
| **Pause before an online exam** | `./pause-peek.sh` | Double-click `pause-peek.bat` |
| **Turn Peek back on** | `./resume-peek.sh` | Double-click `resume-peek.bat` |
| Change my password | `./set-password.sh` | Double-click `set-password.bat` |
| Change my PIN | `./set-pin.sh` | Double-click `set-pin.bat` |
| Remove Peek | `bash uninstall.sh` | Run `uninstall.ps1` with PowerShell |

---

## If something goes wrong

| Problem | Fix |
|---|---|
| `python` or `ngrok` not found | Close the terminal, open it again, and retry |
| Phone says "Your PC is offline" | Make sure the computer is on, signed in and connected to the internet |
| Wrong 6-digit code | Wait for a new code and try again |
| No notification on iPhone | Open Peek from the **home-screen icon**, not Safari (needs iOS 16.4+) |
| Mac screenshot or camera fails | Run `./mac-permissions.sh` and allow Peek |
| Still stuck | Ask Claude Code: `Peek isn't working, please check it` |

Never share your password, PIN, authenticator code, ngrok token or screenshot key with anyone.
