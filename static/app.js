// Peek dashboard. Plain JS, no build step.

const $ = (id) => document.getElementById(id);

// The wordmark font loads after the page, so it never delays the first screen.
const peekFont = document.createElement("link");
peekFont.rel = "stylesheet";
peekFont.href = "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700&display=swap";
document.head.append(peekFont);

async function api(path, opts = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15000);
  let res;
  try {
    res = await fetch(path, {
      credentials: "same-origin",
      signal: ctrl.signal,
      ...opts,
      headers: opts.body ? { "Content-Type": "application/json", ...(opts.headers || {}) } : opts.headers,
    });
  } finally { clearTimeout(timer); }
  if (["ERR_NGROK_3200", "ERR_NGROK_3004", "ERR_NGROK_8012"].includes(res.headers.get("ngrok-error-code"))) {
    location.replace("/offline");
    throw new Error("PC offline");
  }
  if (res.status === 401) {
    location.replace("/login");
    throw new Error("not logged in");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || data.error || `Error ${res.status}`);
  }
  return res;
}
const getJSON = async (path) => (await api(path)).json();
const postJSON = async (path, body = {}) => (await api(path, { method: "POST", body: JSON.stringify(body) })).json();

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// ---------------------------------------------------------------- formatting

function dur(s) {
  s = Math.max(0, Math.floor(s));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m`;
  return `${s}s`;
}
function bytes(n) {
  if (n == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
}
const rate = (n) => (n == null ? "—" : bytes(n) + "/s");
const time = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
function dayLabel(ts) {
  const d = new Date(ts * 1000), today = new Date();
  const y = new Date(); y.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === y.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
}

function meter(id, pct) {
  const m = $(id);
  if (pct == null) { m.firstElementChild.style.width = "0"; return; }
  m.firstElementChild.style.width = Math.min(100, pct) + "%";
  m.classList.toggle("warn", pct >= 75 && pct < 90);
  m.classList.toggle("bad", pct >= 90);
}

// ---------------------------------------------------------------- routing

const pages = ["overview", "charts", "timeline", "actions", "settings"];
let current = null;
let overviewTimer = null;

function route() {
  const page = pages.includes(location.hash.slice(1)) ? location.hash.slice(1) : "overview";
  current = page;
  for (const p of pages) $("page-" + p).classList.toggle("active", p === page);
  for (const a of document.querySelectorAll("nav.tabs a")) a.classList.toggle("on", a.dataset.page === page);
  window.scrollTo(0, 0);
  clearInterval(overviewTimer);
  if (page === "overview") { loadOverview(); overviewTimer = setInterval(loadOverview, 10000); }
  if (page === "charts") loadCharts();
  if (page === "timeline") loadEvents(true);
  if (page === "settings") loadSettings();
  if (page === "actions") loadIntruders();
}
window.addEventListener("hashchange", route);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && current) route();
  else clearInterval(overviewTimer);
});

// ---------------------------------------------------------------- overview

// A blocked redirect to Google looks like a network error. If Peek itself is online, reload into sign-in.
async function recoverIfSignedOut(err) {
  if (!(err instanceof TypeError)) return;
  try {
    const res = await fetch("/about", { cache: "no-store", headers: { "ngrok-skip-browser-warning": "1" } });
    if (!res.ok || !res.headers.get("X-Peek")) return;
    const last = Number(sessionStorage.getItem("peek-recover") || 0);
    if (Date.now() - last < 30000) return;
    sessionStorage.setItem("peek-recover", String(Date.now()));
    location.reload();
  } catch { /* still offline */ }
}

async function loadOverview() {
  let o;
  try { o = await getJSON("/api/overview"); } catch (e) {
    $("subtitle").textContent = e.name === "AbortError" ? "Connection timed out — retrying…" : "PC not reachable";
    recoverIfSignedOut(e); return;
  }
  try { localStorage.setItem("peek-last-seen", String(Date.now())); } catch { /* optional */ }
  applyFeatures(o);
  $("hostname").textContent = o.hostname;
  $("subtitle").textContent = `Up for ${dur(o.uptime)} · since ${new Date(o.boot * 1000).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })}`;
  document.title = `${o.hostname} · Peek`;

  const st = $("status");
  st.classList.toggle("active", o.active);
  if (o.locked) {
    st.classList.remove("active");
    $("status-big").textContent = "PC is locked";
    $("status-small").textContent = o.idle != null ? `No input for ${dur(o.idle)} · lock screen showing` : "Lock screen showing";
  } else if (o.idle == null) {
    $("status-big").textContent = "Activity unknown";
    $("status-small").textContent = `Idle detection isn't available on ${o.os}`;
  } else if (o.active) {
    $("status-big").textContent = "Someone is using it now";
    $("status-small").textContent = "Mouse or keyboard used in the last minute";
  } else {
    $("status-big").textContent = `Idle for ${dur(o.idle)}`;
    $("status-small").textContent = `Last input at ${time(o.now - o.idle)}`;
  }

  const L = o.live || {};
  $("cpu").textContent = L.cpu != null ? Math.round(L.cpu) + "%" : "—";
  meter("cpu-m", L.cpu);
  $("ram").textContent = L.ram != null ? Math.round(L.ram) + "%" : "—";
  $("ram-d").textContent = `${bytes(o.ram_used)} of ${bytes(o.ram_total)}`;
  meter("ram-m", L.ram);
  $("disk-drive").textContent = o.disk_drive ? o.disk_drive.replace("\\", "") : "";
  $("disk").textContent = L.disk != null ? Math.round(L.disk) + "%" : "—";
  $("disk-d").textContent = o.disk_free != null ? `${bytes(o.disk_free)} free` : "";
  meter("disk-m", L.disk);
  if (L.battery != null) {
    $("bat").textContent = Math.round(L.battery) + "%";
    $("bat-d").textContent = L.plugged ? "Plugged in" : "On battery";
    meter("bat-m", L.battery);
    $("bat-m").classList.remove("warn", "bad");
    if (L.battery < 20 && !L.plugged) $("bat-m").classList.add("bad");
  } else {
    $("bat").textContent = "—";
    $("bat-d").textContent = "No battery";
    meter("bat-m", null);
  }
  $("net-up").textContent = rate(L.net_up);
  $("net-down").textContent = rate(L.net_down);

  const wo = $("watched-open");
  wo.replaceChildren();
  if (!o.watched_open.length) wo.append(el("div", "empty", "None of your watched apps are open."));
  for (const a of o.watched_open) {
    const c = el("span", "chip on", a.name);
    c.append(el("span", "since", "for " + dur(o.now - a.since)));
    wo.append(c);
  }

  const ta = $("top-apps");
  ta.replaceChildren();
  for (const a of o.top_apps) {
    const li = el("li");
    li.append(el("span", "name", a.name), el("span", "meta", (a.count > 1 ? `${a.count} × · ` : "") + bytes(a.mem)));
    ta.append(li);
  }
  $("about").textContent = `Peek ${o.version} on ${o.hostname}`;
}

// ---------------------------------------------------------------- charts

const charts = {};
let rangeHours = 24;

$("range").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  rangeHours = Number(b.dataset.h);
  for (const x of $("range").children) x.classList.toggle("on", x === b);
  loadCharts();
});

function makeChart(id, datasets, yOpts) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart($(id), {
    type: "line",
    data: { labels: [], datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      elements: { point: { radius: 0 }, line: { borderWidth: 2, tension: 0.25 } },
      plugins: { legend: { display: datasets.length > 1, labels: { color: "#8b97b0", boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: "#8b97b0", maxTicksLimit: 6, maxRotation: 0 }, grid: { color: "#1a2540" } },
        y: { beginAtZero: true, ticks: { color: "#8b97b0" }, grid: { color: "#1a2540" }, ...yOpts },
      },
    },
  });
  return charts[id];
}

let chartLibrary = null;
function loadChartLibrary() {          // only downloaded when the Charts page is opened
  if (typeof Chart !== "undefined") return Promise.resolve();
  chartLibrary = chartLibrary || new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js";
    s.onload = resolve;
    s.onerror = () => { chartLibrary = null; reject(new Error("chart library")); };
    document.head.append(s);
  });
  return chartLibrary;
}

async function loadCharts() {
  $("chart-msg").textContent = typeof Chart === "undefined" ? "Loading charts…" : "";
  try { await loadChartLibrary(); }
  catch { $("chart-msg").textContent = "Chart library didn't load (no internet on the phone?)."; return; }
  const { rows } = await getJSON(`/api/metrics?hours=${rangeHours}`);
  $("chart-msg").textContent = rows.length ? "" : "No data yet — samples are recorded every 30 seconds.";
  const labels = rows.map((r) => {
    const d = new Date(r.t * 1000);
    return rangeHours > 24 ? d.toLocaleDateString([], { weekday: "short" }) + " " + d.toLocaleTimeString([], { hour: "2-digit" })
                           : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  });
  const ds = (label, data, color, fill = true) => ({ label, data, borderColor: color, backgroundColor: color + "22", fill });
  const pct = { max: 100, ticks: { color: "#8b97b0", callback: (v) => v + "%" } };
  const cpu = makeChart("chart-cpu", [ds("CPU", rows.map((r) => r.cpu), "#22c55e")], pct);
  const ram = makeChart("chart-ram", [ds("Memory", rows.map((r) => r.ram), "#60a5fa")], pct);
  const net = makeChart("chart-net", [ds("Down", rows.map((r) => r.down), "#a78bfa"), ds("Up", rows.map((r) => r.up), "#f59e0b", false)],
                        { ticks: { color: "#8b97b0", callback: (v) => bytes(v) + "/s" } });
  for (const c of [cpu, ram, net]) { c.data.labels = labels; c.update(); }
}

// ---------------------------------------------------------------- timeline

const ICONS = {
  boot: ["⏻", "good"], guardian_start: ["🛡", "good"], wake: ["☀", "good"],
  app_opened: ["▶", ""], app_closed: ["■", ""], app_already_open: ["•", ""],
  login_failed: ["⚠", "alert"], intruder: ["📸", "alert"], exam: ["🎓", ""], power: ["⏻", "alert"], turnoff_failed: ["⚠", "alert"], code_failed: ["⚠", "alert"], camera: ["📷", ""], pin_failed: ["⚠", "alert"], visitor: ["👀", "alert"], login: ["🔑", ""], lock: ["🔒", ""], screenshot: ["📷", ""],
  settings: ["⚙", ""], push_on: ["🔔", ""], logout_all: ["🚪", ""],
};
let oldestId = null;
let lastDay = null;

async function loadEvents(reset) {
  const box = $("events");
  if (reset) { oldestId = null; lastDay = null; box.replaceChildren(); }
  const { events } = await getJSON(`/api/events?limit=50${oldestId ? "&before=" + oldestId : ""}`);
  if (reset && !events.length) box.append(el("div", "empty", "Nothing has happened yet."));
  for (const ev of events) {
    const day = dayLabel(ev.ts);
    if (day !== lastDay) { box.append(el("div", "day", day)); lastDay = day; }
    const [icon, tone] = ICONS[ev.kind] || ["•", ""];
    const row = el("div", "event " + tone);
    const text = el("div");
    text.append(el("div", "t", ev.title));
    if (ev.body) text.append(el("div", "b", ev.body));
    text.append(el("div", "w", time(ev.ts)));
    row.append(el("div", "ico", icon), text);
    box.append(row);
    oldestId = ev.id;
  }
  $("more").hidden = events.length < 50;
}
$("more").addEventListener("click", () => loadEvents(false));

// ---------------------------------------------------------------- actions

let needPin = false;

/** Ask for the PIN if one is set. Returns {pin} body, or null if the user cancelled. */
function pinBody(action) {
  if (!needPin) return {};
  const pin = prompt(`Enter your PIN to ${action}:`);
  return pin === null ? null : { pin: pin.trim() };
}

/** Image bytes from the PC, decrypting them here if they were sent end-to-end encrypted. */
async function imageFromResponse(res, fallbackType) {
  if (!res.headers.get("X-PCG-Encrypted")) return res.blob();
  const key = await shotKey();
  if (!key) throw new Error("images are encrypted - add the screenshot key in Settings first");
  if (key.id !== res.headers.get("X-PCG-Key-Id")) throw new Error("this device has an old screenshot key - enter the new one in Settings");
  const buf = new Uint8Array(await res.arrayBuffer());
  const plain = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: buf.slice(0, 12), additionalData: new TextEncoder().encode("pcg-shot") },
    key.aes, buf.slice(12));
  return new Blob([plain], { type: res.headers.get("X-PCG-Type") || fallbackType });
}

// ---------------------------------------------------------------- camera photo on demand

let camUrl = null;
$("btn-cam").addEventListener("click", async () => {
  const body = pinBody("take a camera photo");
  if (!body) return;
  const b = $("btn-cam"), m = $("cam-msg");
  b.disabled = true; b.textContent = "Taking photo…"; m.textContent = "";
  try {
    const res = await api("/api/camera", { method: "POST", body: JSON.stringify(body) });
    const blob = await imageFromResponse(res, "image/jpeg");
    if (camUrl) URL.revokeObjectURL(camUrl);
    camUrl = URL.createObjectURL(blob);
    $("cam-img").src = camUrl;
    $("cam-link").href = camUrl;
    const fallback = res.headers.get("X-PCG-Fallback");
    $("cam-time").textContent = fallback
      ? `Couldn't take a camera photo: ${fallback}. Showing a screenshot instead (${new Date().toLocaleTimeString()}).`
      : `Taken at ${new Date().toLocaleTimeString()} · tap to open full size`;
    $("cam").hidden = false;
  } catch (e) {
    m.className = "msg err"; m.textContent = "Camera photo failed: " + e.message;
  } finally {
    b.disabled = false; b.textContent = "Take camera photo";
  }
});

// ---------------------------------------------------------------- power: shut down / restart

let powerTimer = null;
async function powerAction(action) {
  const word = action === "shutdown" ? "shut down" : "restart";
  if (!confirm(`${word[0].toUpperCase() + word.slice(1)} the PC?`)) return;
  const body = pinBody(`${word} the PC`);
  if (!body) return;
  const code = prompt("Enter the 6-digit code from your authenticator app:");
  if (code === null) return;
  const m = $("power-msg");
  try {
    const r = await postJSON("/api/power", { ...body, action, code: code.trim() });
    let left = r.delay;
    $("btn-power-cancel").hidden = false;
    clearInterval(powerTimer);
    const tick = () => {
      m.className = "msg ok";
      m.textContent = left > 0 ? `The PC will ${word} in ${left}s. Tap Cancel to stop it.` : `The PC is ${word === "restart" ? "restarting" : "shutting down"}.`;
      if (left-- <= 0) { clearInterval(powerTimer); $("btn-power-cancel").hidden = true; }
    };
    tick(); powerTimer = setInterval(tick, 1000);
  } catch (e) { m.className = "msg err"; m.textContent = `Couldn't ${word}: ` + e.message; }
}
$("btn-restart").addEventListener("click", () => powerAction("restart"));
$("btn-shutdown").addEventListener("click", () => powerAction("shutdown"));
$("btn-power-cancel").addEventListener("click", async () => {
  const body = pinBody("cancel");
  if (!body) return;
  const m = $("power-msg");
  try {
    const r = await postJSON("/api/power", { ...body, action: "cancel" });
    clearInterval(powerTimer);
    $("btn-power-cancel").hidden = true;
    m.className = r.ok ? "msg ok" : "msg err";
    m.textContent = r.ok ? "Cancelled. The PC stays on." : "Nothing to cancel (too late, or already cancelled).";
  } catch (e) { m.className = "msg err"; m.textContent = "Couldn't cancel: " + e.message; }
});

// ---------------------------------------------------------------- turn off Peek

$("btn-off").addEventListener("click", async () => {
  if (!confirm("Turn off Peek?\n\nYou will NOT be able to reach this computer from your phone until you run resume-peek (.bat on Windows, .sh on Mac) on the computer itself.")) return;
  const code = prompt("Enter the 6-digit code from your authenticator app:");
  if (code === null) return;
  const m = $("off-msg");
  try {
    await postJSON("/api/turn-off", { code: code.trim() });
    m.className = "msg ok";
    m.textContent = "Peek is turning off. Run resume-peek (.bat on Windows, .sh on Mac) on the PC to turn it back on.";
    $("btn-off").disabled = true;
  } catch (e) { m.className = "msg err"; m.textContent = "Not turned off: " + e.message; }
});

// ---------------------------------------------------------------- intruder photos

async function loadIntruders() {
  const box = $("intr-list"), st = $("intr-state");
  let data;
  try { data = await getJSON("/api/intruders"); } catch { return; }
  const s = data.status || {};
  if (!s.supported) { $("intr-panel").hidden = true; $("intr-h").hidden = true; return; }
  st.textContent = s.watching
    ? "On: a wrong password or PIN typed on this PC's lock screen takes a webcam photo and alerts your phone."
    : s.error ? `Not active yet: ${s.error}.` : "Starting…";
  box.replaceChildren();
  if (!data.photos.length) { box.append(el("li", "empty", "No photos yet.")); return; }
  for (const p of data.photos) {
    const li = el("li");
    const when = new Date(p.ts * 1000).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    li.append(el("span", "name", when), el("span", "meta", p.who.replace(/^Wrong password\/PIN on the Windows /, "")));
    const b = el("button", "btn", "View");
    b.addEventListener("click", () => viewIntruder(p, b));
    li.append(b);
    box.append(li);
  }
}

let intrUrl = null;
async function viewIntruder(p, btn) {
  const body = pinBody("see this photo");
  if (!body) return;
  btn.disabled = true;
  const m = $("intr-msg");
  m.textContent = "";
  try {
    const res = await api("/api/intruders/" + encodeURIComponent(p.id), { method: "POST", body: JSON.stringify(body) });
    const blob = await imageFromResponse(res, "image/jpeg");
    if (intrUrl) URL.revokeObjectURL(intrUrl);
    intrUrl = URL.createObjectURL(blob);
    $("intr-img").src = intrUrl;
    $("intr-link").href = intrUrl;
    $("intr-view").hidden = false;
    $("intr-view").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (e) { m.className = "msg err"; m.textContent = "Couldn't open the photo: " + e.message; }
  finally { btn.disabled = false; }
}

let shotUrl = null;
$("btn-shot").addEventListener("click", async () => {
  const body = pinBody("take a screenshot");
  if (!body) return;
  const b = $("btn-shot");
  b.disabled = true; b.textContent = "Capturing…"; $("shot-msg").textContent = "";
  try {
    const res = await api("/api/screenshot", { method: "POST", body: JSON.stringify(body) });
    const blob = await imageFromResponse(res, res.headers.get("X-PCG-Fallback") ? "image/jpeg" : "image/png");
    if (shotUrl) URL.revokeObjectURL(shotUrl);
    shotUrl = URL.createObjectURL(blob);
    $("shot-img").src = shotUrl;
    $("shot-link").href = shotUrl;
    const fb = res.headers.get("X-PCG-Fallback");
    $("shot-time").textContent = fb
      ? `No screenshot: ${fb} (${new Date().toLocaleTimeString()}).`
      : `Taken at ${new Date().toLocaleTimeString()} · ${bytes(blob.size)} · tap to open full size`;
    $("shot").hidden = false;
  } catch (e) {
    $("shot-msg").className = "msg err"; $("shot-msg").textContent = "Screenshot failed: " + e.message;
  } finally {
    b.disabled = false; b.textContent = "Take screenshot";
  }
});

$("btn-lock").addEventListener("click", async () => {
  if (!needPin && !confirm("Lock the PC now?")) return;
  const body = pinBody("lock the PC");
  if (!body) return;
  const m = $("lock-msg");
  try { await postJSON("/api/lock", body); m.className = "msg ok"; m.textContent = "PC locked."; }
  catch (e) { m.className = "msg err"; m.textContent = "Couldn't lock: " + e.message; }
});

// ---------------------------------------------------------------- end-to-end screenshot key
// Must match pcguardian/shotcrypt.py. The AES key is stored non-extractable in IndexedDB.

function idb() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open("pc-guardian", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("keys");
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
async function idbDo(mode, fn) {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const req = fn(db.transaction("keys", mode).objectStore("keys"));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
const shotKey = () => idbDo("readonly", (s) => s.get("shot")).catch(() => null);

function b32decode(text) {
  const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const s = text.toUpperCase().replace(/[^A-Z2-7]/g, "");
  let bits = 0, val = 0;
  const out = [];
  for (const c of s) {
    val = (val << 5) | A.indexOf(c); bits += 5;
    if (bits >= 8) { out.push((val >>> (bits - 8)) & 255); bits -= 8; }
  }
  return { bytes: new Uint8Array(out), chars: s.length };
}

async function deriveShotKey(text) {
  const { bytes, chars } = b32decode(text);
  if (chars !== 32) throw new Error("the key should be 32 letters and digits");
  const base = await crypto.subtle.importKey("raw", bytes, "HKDF", false, ["deriveKey", "deriveBits"]);
  const salt = new TextEncoder().encode("PC Guardian");
  const aes = await crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt, info: new TextEncoder().encode("screenshot v1") },
    base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
  const idBits = await crypto.subtle.deriveBits(
    { name: "HKDF", hash: "SHA-256", salt, info: new TextEncoder().encode("key id v1") }, base, 64);
  const id = [...new Uint8Array(idBits)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return { aes, id };
}

async function refreshShotKey() {
  const state = $("skey-state"), form = $("skey-form"), rm = $("skey-remove");
  if (!window.crypto || !crypto.subtle) { state.textContent = "This browser can't decrypt screenshots (needs HTTPS)."; return; }
  const server = await getJSON("/api/shot-key-id");
  const local = await shotKey();
  form.hidden = rm.hidden = true;
  if (!server.enabled) {
    state.textContent = "Screenshot encryption is OFF on the PC. Run screen-key (.bat or .sh) on the PC to turn it on.";
  } else if (local && local.id === server.key_id) {
    state.textContent = "✓ This device has the screenshot key. Screenshots are end-to-end encrypted.";
    rm.hidden = false;
  } else {
    state.textContent = local ? "This device has an OLD key. Enter the current one:" : "Enter the screenshot key to view screenshots on this device:";
    form.hidden = false;
  }
}

$("skey-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const m = $("skey-msg");
  try {
    const key = await deriveShotKey($("skey-input").value);
    const server = await getJSON("/api/shot-key-id");
    if (key.id !== server.key_id) throw new Error("that key doesn't match the PC's key - check for typos");
    await idbDo("readwrite", (s) => s.put(key, "shot"));
    $("skey-input").value = "";
    m.className = "msg ok"; m.textContent = "Key saved on this device.";
  } catch (err) { m.className = "msg err"; m.textContent = "Couldn't save: " + err.message; }
  refreshShotKey();
});

$("skey-remove").addEventListener("click", async () => {
  if (!confirm("Remove the screenshot key from this device? You'll need to type it again to see screenshots.")) return;
  await idbDo("readwrite", (s) => s.delete("shot"));
  refreshShotKey();
});

// ---------------------------------------------------------------- settings: watched apps

let watched = [];

function renderWatched() {
  const box = $("watch-list");
  box.replaceChildren();
  if (!watched.length) box.append(el("div", "empty", "No apps watched."));
  for (const name of watched) {
    const c = el("span", "chip", name);
    const x = el("button", "", "×");
    x.type = "button";
    x.setAttribute("aria-label", "Stop watching " + name);
    x.addEventListener("click", () => saveWatched(watched.filter((w) => w !== name)));
    c.append(x);
    box.append(c);
  }
}

async function saveWatched(list) {
  const m = $("watch-msg");
  try {
    watched = (await postJSON("/api/settings", { watched_apps: list })).watched_apps;
    renderWatched();
    m.className = "msg ok"; m.textContent = "Saved.";
    setTimeout(() => (m.textContent = ""), 2000);
  } catch (e) { m.className = "msg err"; m.textContent = "Couldn't save: " + e.message; }
}

$("watch-add").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("watch-input").value.trim();
  if (!v) return;
  $("watch-input").value = "";
  if (!watched.some((w) => w.toLowerCase() === v.toLowerCase())) saveWatched([...watched, v]);
});

let procTimer = null;
$("proc-q").addEventListener("input", () => {
  clearTimeout(procTimer);
  procTimer = setTimeout(searchProcs, 250);
});

async function searchProcs() {
  const q = $("proc-q").value.trim();
  const list = $("proc-list");
  if (!q) { list.replaceChildren(); return; }
  const { processes } = await getJSON("/api/processes?q=" + encodeURIComponent(q));
  list.replaceChildren();
  if (!processes.length) list.append(el("li", "empty", "No running process matches."));
  for (const p of processes) {
    const li = el("li");
    li.append(el("span", "name", p.exe), el("span", "meta", (p.count > 1 ? p.count + " × · " : "") + bytes(p.mem)));
    const already = watched.some((w) => w.toLowerCase() === p.suggest.toLowerCase());
    const b = el("button", "btn", already ? "Watching" : "Watch");
    b.disabled = already;
    b.addEventListener("click", () => { saveWatched([...watched, p.suggest]).then(searchProcs); });
    li.append(b);
    list.append(li);
  }
}

// ---------------------------------------------------------------- settings: push

function b64ToBytes(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;

async function pushRegistration() {
  if (!("serviceWorker" in navigator)) return null;
  return navigator.serviceWorker.register("/sw.js");
}

async function refreshPush() {
  const state = $("push-state"), on = $("push-on"), off = $("push-off"), test = $("push-test");
  on.hidden = off.hidden = test.hidden = true;
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    state.textContent = isIOS && !standalone
      ? "On iPhone: tap Share → “Add to Home Screen”, then open Peek from the home-screen icon and come back here. (Needs iOS 16.4 or newer.)"
      : "This browser can't receive push notifications.";
    return;
  }
  if (!window.isSecureContext) { state.textContent = "Notifications need HTTPS — open your https://….ngrok-free.dev address."; return; }
  if (Notification.permission === "denied") {
    state.textContent = "Notifications are blocked for this site. Allow them in the browser/phone settings, then reload.";
    return;
  }
  const reg = await pushRegistration();
  await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  let status = { subscribed: false, devices: 0 };
  if (sub) status = await postJSON("/api/push/status", { endpoint: sub.endpoint });
  if (sub && status.subscribed) {
    state.textContent = `Notifications are ON for this device. ${status.devices} device(s) subscribed in total.`;
    off.hidden = test.hidden = false;
  } else {
    state.textContent = "Notifications are OFF for this device.";
    on.hidden = false;
  }
}

$("push-on").addEventListener("click", async () => {
  const m = $("push-msg");
  m.textContent = "";
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") throw new Error("permission was not granted");
    const reg = await pushRegistration();
    await navigator.serviceWorker.ready;
    const { key } = await getJSON("/api/push/key");
    let sub = await reg.pushManager.getSubscription();
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key) });
    await postJSON("/api/push/subscribe", sub.toJSON());
    m.className = "msg ok"; m.textContent = "Done — you should get a confirmation notification in a few seconds.";
  } catch (e) { m.className = "msg err"; m.textContent = "Couldn't turn on notifications: " + e.message; }
  refreshPush();
});

$("push-off").addEventListener("click", async () => {
  const reg = await pushRegistration();
  const sub = await reg.pushManager.getSubscription();
  if (sub) { await postJSON("/api/push/unsubscribe", { endpoint: sub.endpoint }); await sub.unsubscribe(); }
  $("push-msg").className = "msg ok"; $("push-msg").textContent = "Notifications turned off for this device.";
  refreshPush();
});

$("push-test").addEventListener("click", async () => {
  await postJSON("/api/push/test");
  $("push-msg").className = "msg ok"; $("push-msg").textContent = "Test sent.";
});

// ---------------------------------------------------------------- settings: account

$("logout").addEventListener("click", async () => { await postJSON("/api/logout"); location.replace("/login"); });
$("logout-all").addEventListener("click", async () => {
  if (!confirm("Log out every phone and browser, including this one?")) return;
  await postJSON("/api/logout-all");
  location.replace("/login");
});

async function loadSettings() {
  watched = (await getJSON("/api/settings")).watched_apps;
  renderWatched();
  refreshPush().catch((e) => ($("push-state").textContent = "Couldn't check notifications: " + e.message));
  refreshShotKey().catch((e) => ($("skey-state").textContent = "Couldn't check the screenshot key: " + e.message));
}

// ---------------------------------------------------------------- start

function applyFeatures(o) {
  needPin = !!o.pin;
  const t = o.tunnel || {};
  $("security").textContent = [
    `2FA code at login: ${o.totp ? "ON" : "off"}`,
    `PIN for screenshot/lock: ${o.pin ? "ON" : "off"}`,
    t.enabled ? `Remote access (ngrok): ${t.running ? "online" : "offline"}${t.google_signin ? " · Google sign-in ON" : ""}${t.url ? " · " + t.url : ""}${t.error ? " · " + t.error : ""}` : "Remote access (ngrok): not enabled",
  ].join("\n");
  const f = o.features || {};
  for (const e of document.querySelectorAll(".need-shot")) e.hidden = !f.screenshot;
  for (const e of document.querySelectorAll(".need-lock")) e.hidden = !f.lock;
  for (const e of document.querySelectorAll(".need-power")) e.hidden = !f.power;
  for (const e of document.querySelectorAll(".need-cam")) e.hidden = !(o.intruder && o.intruder.supported);
  $("no-actions").hidden = !!(f.screenshot || f.lock);
}

pushRegistration().catch(() => {});
route();
if (current !== "overview") getJSON("/api/overview").then(applyFeatures).catch(() => {});
