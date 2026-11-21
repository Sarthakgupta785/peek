// Peek's offline screen: keeps checking and returns to the app as soon as the PC is back.

const statusEl = document.getElementById("offline-status");
const retry = document.getElementById("offline-retry");

function ago(ms) {
  const m = Math.floor(ms / 60000);
  if (m < 1) return "less than a minute ago";
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m ago`;
  return `${Math.floor(h / 24)}d ${h % 24}h ago`;
}

try {
  const seen = Number(localStorage.getItem("peek-last-seen"));
  if (seen) document.getElementById("offline-seen").textContent = `Last connected ${ago(Date.now() - seen)}.`;
} catch { /* storage can be unavailable; the default text is fine */ }

async function check(manual) {
  retry.disabled = true;
  statusEl.textContent = "Checking…";
  try {
    const res = await fetch("/about", { cache: "no-store", headers: { "ngrok-skip-browser-warning": "1" } });
    if (res.ok && res.headers.get("X-Peek")) {
      statusEl.textContent = "Back online. Opening Peek…";
      if (location.pathname === "/offline") location.replace("/");
      else location.reload();
      return;
    }
  } catch { /* still offline, or this phone has no internet */ }
  retry.disabled = false;
  statusEl.textContent = manual ? "Still offline. Checking again automatically…" : "Checking automatically…";
}

retry.addEventListener("click", () => check(true));
setInterval(() => { if (document.visibilityState === "visible") check(false); }, 8000);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") check(false); });
check(false);
