// The wordmark font loads after the page, so it never delays the first screen.
const peekFont = document.createElement("link");
peekFont.rel = "stylesheet";
peekFont.href = "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700&display=swap";
document.head.append(peekFont);

const form = document.getElementById("form");
const msg = document.getElementById("msg");
const go = document.getElementById("go");
const codeInput = document.getElementById("code");

fetch("/api/login-info").then((r) => r.json()).then((info) => {
  if (info.totp) { document.getElementById("code-field").hidden = false; codeInput.required = true; }
}).catch(() => {});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = "";
  go.disabled = true;
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: document.getElementById("password").value, code: codeInput.value }),
    });
    if (res.ok) {
      location.replace("/");
      return;
    }
    const data = await res.json().catch(() => ({}));
    msg.textContent = data.error || "Login failed.";
    codeInput.value = "";
  } catch {
    msg.textContent = "Can't reach the PC. Is it on and connected to the internet?";
  } finally {
    go.disabled = false;
  }
});

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
