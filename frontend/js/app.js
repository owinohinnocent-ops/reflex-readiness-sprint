import { ApiError, ReflexApi } from "./api.js";

const STORE_KEY = "reflex-session";
const POLL_MS = 20_000;
const REAL_STATUS_ORDER = ["OPEN", "ASSIGNED", "PICKED_UP", "DELIVERED"];
const DEMO_STATUS_ORDER = ["OPEN", "ASSIGNED", "PICKED_UP", "IN_TRANSIT", "DELIVERED"];
const STATUS_LABELS = { OPEN: "Open", ASSIGNED: "Assigned", PICKED_UP: "Picked up", IN_TRANSIT: "In transit", DELIVERED: "Delivered", FAILED: "Failed" };
const REAL_NEXT_STATUS = { ASSIGNED: "PICKED_UP", PICKED_UP: "DELIVERED" };
const DEMO_NEXT_STATUS = { ASSIGNED: "PICKED_UP", PICKED_UP: "IN_TRANSIT", IN_TRANSIT: "DELIVERED" };
const DEMO_RIDERS = ["Brian", "Kevin", "Samuel", "David"];
const DEMO_SEED = [
  { id: 1001, reference: "RF-1001", customer_name: "Jane Wanjiku", customer_phone: "+254 712 345 678", delivery_address: "Meru Town", pickup_address: "Kimathi Electronics, Meru", item_description: "Samsung Galaxy A15", assignedRiderName: "Brian", status: "ASSIGNED", created_at: "2026-08-30T08:15:00+03:00" },
  { id: 1002, reference: "RF-1002", customer_name: "Peter Mwangi", customer_phone: "+254 721 884 102", delivery_address: "Nkubu", pickup_address: "Kimathi Electronics, Meru", item_description: "HP Laptop", assignedRiderName: "Kevin", status: "PICKED_UP", created_at: "2026-08-30T08:35:00+03:00" },
  { id: 1003, reference: "RF-1003", customer_name: "Mary Njeri", customer_phone: "+254 790 143 226", delivery_address: "Makutano", pickup_address: "Meru Care Pharmacy", item_description: "Pharmacy order", assignedRiderName: "Samuel", status: "DELIVERED", created_at: "2026-08-29T16:10:00+03:00" },
  { id: 1004, reference: "RF-1004", customer_name: "Daniel Karanja", customer_phone: "+254 711 220 111", delivery_address: "Githongo", pickup_address: "Meru Hardware", item_description: "Electrical fittings", assignedRiderName: null, status: "OPEN", created_at: "2026-08-30T09:10:00+03:00" },
];
const TEST_ACCOUNTS = [
  { role: "Retailer — Mary", phone: "0712000001", password: "retailer123" },
  { role: "Dispatcher — John", phone: "0722000002", password: "dispatch123" },
  { role: "Rider — Brian", phone: "0733000003", password: "rider123" },
  { role: "Rider — Peter", phone: "0733000004", password: "rider123" },
];

let session = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
if (session && !session.mode) session.mode = "real";
let deliveries = [];
let demoDeliveries = [];
let riders = [];
let syncing = false;
let lastSynced = null;
let apiAvailability = "checking";
const app = document.querySelector("#app");
const api = new ReflexApi({ getToken: () => session?.mode === "real" ? session.token : null });

function escapeHtml(value = "") { return String(value).replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&gt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char])); }
function formatDate(value) { return value ? new Intl.DateTimeFormat("en-KE", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }
function showToast(message, type = "success") { const toast = document.createElement("div"); toast.className = `toast ${type}`; toast.textContent = message; document.querySelector("#toast-region").append(toast); setTimeout(() => toast.remove(), 5000); }
function friendlyError(error) { return error instanceof ApiError ? error.message : "Something went wrong. Please try again."; }
function isDemo() { return session?.mode === "demo"; }
function activeDeliveries() { return isDemo() ? demoDeliveries : deliveries; }
function deliveryReference(delivery) { return delivery.reference || `REF-${delivery.id}`; }
function statusBadge(status) { return `<span class="status status-${status}">${STATUS_LABELS[status] || escapeHtml(status)}</span>`; }

function progress(status) {
  const order = isDemo() ? DEMO_STATUS_ORDER : REAL_STATUS_ORDER;
  const current = order.indexOf(status);
  if (status === "FAILED") return `<p class="failed-note">This delivery was marked failed and can be reassigned by a dispatcher.</p>`;
  return `<ol class="progress" aria-label="Delivery progress">${order.map((step, index) => `<li class="${index < current ? "complete" : ""} ${index === current ? "current" : ""}"><span></span>${STATUS_LABELS[step]}</li>`).join("")}</ol>`;
}

function assignmentControl(delivery) {
  if (!["OPEN", "FAILED"].includes(delivery.status)) return "";
  if (isDemo()) return `<form class="assign-form" data-delivery-id="${delivery.id}"><label>Demo rider<select class="rider-select" name="riderName" required><option value="">Select rider</option>${DEMO_RIDERS.map(name => `<option value="${name}">${name}</option>`).join("")}</select></label><button class="button secondary" type="submit">Assign rider</button></form>`;
  if (riders.length) return `<form class="assign-form" data-delivery-id="${delivery.id}"><label>Assign rider<select class="rider-select" name="riderId" required><option value="">Select rider</option>${riders.map(rider => `<option value="${rider.id}" ${rider.availability_status !== "AVAILABLE" ? "disabled" : ""}>${escapeHtml(rider.user.name)} — ${escapeHtml(rider.vehicle_type || "vehicle unknown")}${rider.availability_status !== "AVAILABLE" ? " (busy)" : ""}</option>`).join("")}</select></label><button class="button secondary" type="submit">Assign rider</button></form>`;
  return `<form class="assign-form" data-delivery-id="${delivery.id}"><label>Available rider profile ID<input name="riderId" inputmode="numeric" min="1" required placeholder="e.g. 3" /></label><button class="button secondary" type="submit">Assign rider</button></form>`;
}

function riderActions(delivery) {
  const next = (isDemo() ? DEMO_NEXT_STATUS : REAL_NEXT_STATUS)[delivery.status];
  if (!next) return delivery.status === "DELIVERED" ? `<p class="success-copy">Delivery complete.</p>` : "";
  const action = next === "PICKED_UP" ? "Mark picked up" : next === "IN_TRANSIT" ? "Mark in transit" : "Mark delivered";
  const scanner = isDemo() && next === "DELIVERED" ? `<button class="button ghost" data-demo-scan="${delivery.id}">Use demo order</button>` : (!isDemo() && next === "DELIVERED" ? `<button class="button ghost" data-scanner="${delivery.id}">Scan confirmation</button>` : "");
  return `<div class="rider-actions"><button class="button" data-status-id="${delivery.id}" data-next-status="${next}">${action}</button>${scanner}</div>`;
}

function deliveryCard(delivery, { dispatcher = false, rider = false } = {}) {
  const riderLabel = isDemo() ? (delivery.assignedRiderName || "Unassigned") : (delivery.rider ? delivery.rider.name : "Unassigned");
  const riderDetailCard = (!isDemo() && delivery.rider) ? `<div class="assigned-rider-card"><strong>${escapeHtml(delivery.rider.name)}</strong> · ${escapeHtml(delivery.rider.vehicle_type || "Vehicle unknown")}${delivery.rider.plate_number ? ` (${escapeHtml(delivery.rider.plate_number)})` : ""}<br><a href="tel:${escapeHtml(delivery.rider.phone)}">${escapeHtml(delivery.rider.phone)}</a></div>` : "";
  return `<article class="delivery-card"><div class="card-heading"><div><p class="eyebrow">${escapeHtml(deliveryReference(delivery))}</p><h3>${escapeHtml(delivery.customer_name)}</h3></div>${statusBadge(delivery.status)}</div><p class="item">${escapeHtml(delivery.item_description)}</p><dl class="delivery-meta"><div><dt>Phone</dt><dd><a href="tel:${escapeHtml(delivery.customer_phone)}">${escapeHtml(delivery.customer_phone)}</a></dd></div><div><dt>Rider</dt><dd>${escapeHtml(riderLabel)}</dd></div><div><dt>Deliver to</dt><dd>${escapeHtml(delivery.delivery_address)}</dd></div><div><dt>Collect from</dt><dd>${escapeHtml(delivery.pickup_address)}</dd></div></dl>${riderDetailCard}${progress(delivery.status)}<p class="muted">Created ${formatDate(delivery.created_at)}</p>${dispatcher ? assignmentControl(delivery) : ""}${rider ? riderActions(delivery) : ""}</article>`;
}

function statistics() {
  const all = activeDeliveries();
  const metrics = isDemo()
    ? [{ label: "Pending", statuses: ["OPEN"] }, { label: "Unassigned", statuses: ["OPEN"] }, { label: "Assigned", statuses: ["ASSIGNED"] }, { label: "In transit", statuses: ["PICKED_UP", "IN_TRANSIT"] }, { label: "Delivered", statuses: ["DELIVERED"] }]
    : REAL_STATUS_ORDER.map(status => ({ label: STATUS_LABELS[status], statuses: [status] }));
  return `<section class="stats ${isDemo() ? "demo-stats" : ""}">${metrics.map(metric => `<div class="stat"><span>${metric.label}</span><strong>${all.filter(delivery => metric.statuses.includes(delivery.status)).length}</strong>${isDemo() ? `<p class="demo-stat-note">Demo data</p>` : ""}</div>`).join("")}</section>`;
}

function layout(content) {
  const role = session.user.role; const demo = isDemo();
  app.innerHTML = `<header class="topbar"><a class="brand" href="#"><span>R</span>Reflex</a><div class="topbar-meta">${demo ? `<span class="mode-pill">DEMO MODE</span>` : `<span class="mode-pill live">API CONNECTED</span>`}<div class="account"><div><strong>${escapeHtml(session.user.name)}</strong><small>${escapeHtml(role)}</small></div><button id="logout" class="text-button">Log out</button></div></div></header><div class="shell"><aside><p class="section-label">Workspace</p><h2>${role === "retailer" ? "Retailer desk" : role === "dispatcher" ? "Dispatch control" : "Rider route"}</h2><p>${demo ? "Demo data stays in this browser and is never sent to the Reflex API." : "Signed in securely. Deliveries refresh automatically while this tab is active."}</p><div class="sync-state ${syncing ? "syncing" : ""}"><i></i>${demo ? "Demo data — frontend only" : syncing ? "Synchronizing…" : lastSynced ? `Updated ${lastSynced.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "Waiting for data"}</div></aside><section class="workspace">${demo ? `<p class="demo-banner"><strong>DEMO MODE</strong><br>Backend authentication is unavailable. All delivery changes are temporary frontend demonstration data.</p>` : ""}${content}</section></div>`;
  bindCommonEvents();
}

function retailerView() {
  const all = activeDeliveries(); const active = all.filter(d => ["ASSIGNED", "PICKED_UP", "IN_TRANSIT"].includes(d.status)).length;
  layout(`<div class="page-heading"><div><p class="eyebrow">Delivery requests</p><h1>Keep every customer delivery visible.</h1></div><button id="refresh" class="button ghost">${isDemo() ? "Reset demo" : "Refresh"}</button></div>${isDemo() ? `<section class="stats"><div class="stat"><span>Total deliveries</span><strong>${all.length}</strong><p class="demo-stat-note">Demo data</p></div><div class="stat"><span>Pending</span><strong>${all.filter(d => d.status === "OPEN").length}</strong><p class="demo-stat-note">Demo data</p></div><div class="stat"><span>Active</span><strong>${active}</strong><p class="demo-stat-note">Demo data</p></div><div class="stat"><span>Delivered</span><strong>${all.filter(d => d.status === "DELIVERED").length}</strong><p class="demo-stat-note">Demo data</p></div></section>` : ""}<div class="retailer-grid"><section class="panel form-panel"><h2>Create a delivery</h2><p>${isDemo() ? "Create a temporary delivery to demonstrate the retailer workflow." : "Each request is sent straight to the Reflex delivery API."}</p><form id="delivery-form" class="stack-form"><label>Customer name<input name="customer_name" required /></label><label>Phone number<input name="customer_phone" type="tel" required pattern="[+0-9() -]{7,20}" placeholder="+254 712 345 678" /></label><label>Delivery address<textarea name="delivery_address" required></textarea></label><label>Item description<textarea name="item_description" required></textarea></label><label>Pickup address<textarea name="pickup_address" required></textarea></label><button class="button" type="submit">Create delivery</button></form></section><section><div class="section-heading"><h2>Your deliveries</h2><span>${all.length} total${isDemo() ? " · Demo data" : ""}</span></div><div class="delivery-list">${all.length ? all.map(delivery => deliveryCard(delivery)).join("") : empty("No deliveries yet", "New requests will appear here after confirmation.")}</div></section></div>`);
  document.querySelector("#delivery-form").addEventListener("submit", createDelivery);
}

function riderDirectorySection() {
  if (isDemo()) return "";
  if (!riders.length) return `<p class="integration-note">No riders found yet — add one via seed_data.py or your own signup flow.</p>`;
  return `<section><div class="section-heading"><h2>Rider directory</h2><span>${riders.length} riders</span></div><div class="rider-directory">${riders.map(rider => `<div class="rider-directory-card ${rider.availability_status !== "AVAILABLE" ? "unavailable" : ""}"><div><p class="rider-directory-name">${escapeHtml(rider.user.name)} <small>#${rider.id}</small></p><p class="rider-directory-meta">${escapeHtml(rider.vehicle_type || "Vehicle unknown")}${rider.plate_number ? ` · ${escapeHtml(rider.plate_number)}` : ""} · ${escapeHtml(rider.location || "Location unknown")} · ${rider.active_delivery_count} active</p></div><span class="rider-directory-badge ${rider.availability_status === "AVAILABLE" ? "" : "busy"}">${escapeHtml(rider.availability_status || "UNKNOWN")}</span></div>`).join("")}</div></section>`;
}

function dispatcherView() {
  const all = activeDeliveries();
  layout(`<div class="page-heading"><div><p class="eyebrow">Operations dashboard</p><h1>Assign work, then follow it through.</h1></div><button id="refresh" class="button ghost">${isDemo() ? "Reset demo" : "Refresh"}</button></div>${statistics()}${riderDirectorySection()}<section><div class="section-heading"><h2>Delivery requests</h2><span>${all.length} visible</span></div>${isDemo() ? `<p class="integration-note">Demo riders: Brian, Kevin, Samuel, and David. Assignments update only this browser’s temporary demo state.</p>` : `<p class="integration-note">Choose a rider from the directory above when assigning a delivery below.</p>`}<div class="delivery-list dispatch-grid">${all.length ? all.map(delivery => deliveryCard(delivery, { dispatcher: true })).join("") : empty("No deliveries found", "Deliveries created by retailers will appear here.")}</div></section>`);
  document.querySelectorAll(".assign-form").forEach(form => form.addEventListener("submit", assignDelivery));
}

function riderView() {
  const all = activeDeliveries(); const myDeliveries = isDemo() ? all.filter(delivery => delivery.assignedRiderName === session.user.name) : all; const outstanding = myDeliveries.filter(d => !["DELIVERED", "FAILED"].includes(d.status)).length;
  layout(`<div class="page-heading"><div><p class="eyebrow">My delivery route</p><h1>Focus on the next confirmed action.</h1></div><button id="refresh" class="button ghost">${isDemo() ? "Reset demo" : "Refresh"}</button></div><section class="rider-intro"><span>Today’s assigned jobs</span><strong>${outstanding}</strong></section><div class="delivery-list rider-grid">${myDeliveries.length ? myDeliveries.map(delivery => deliveryCard(delivery, { rider: true })).join("") : empty("No assigned deliveries", "When a dispatcher assigns a delivery to your rider profile, it will appear here.")}</div>`);
  document.querySelectorAll("[data-status-id]").forEach(button => button.addEventListener("click", updateStatus)); document.querySelectorAll("[data-scanner]").forEach(button => button.addEventListener("click", showScannerLimitation)); document.querySelectorAll("[data-demo-scan]").forEach(button => button.addEventListener("click", demoScan));
}

function empty(title, copy) { return `<div class="empty"><h3>${title}</h3><p>${copy}</p></div>`; }
function render() { if (!session?.user) return renderLogin(); ({ retailer: retailerView, dispatcher: dispatcherView, rider: riderView }[session.user.role] || retailerView)(); }
function apiStatusCopy() { return apiAvailability === "online" ? ["online", "API Connected — real sign-in is available."] : apiAvailability === "offline" ? ["offline", "API Offline — Demo Mode Available."] : ["", "Checking Reflex API connection…"]; }

function renderLogin() {
  const [apiClass, apiCopy] = apiStatusCopy(); const directOpenHint = location.protocol === "file:" ? `<p class="direct-open-hint">The interface is open. For real sign-in and API data, start <code>node frontend/server.mjs</code> and use <code>http://localhost:5173</code>.</p>` : "";
  app.innerHTML = `<section class="login"><div class="login-intro"><a class="brand" href="#"><span>R</span>Reflex</a><p class="eyebrow">DELIVERY COORDINATION PLATFORM</p><h1>Know what’s moving. Keep every promise.</h1><p>One secure workspace for retailer staff, dispatchers, and riders.</p></div><form id="login-form" class="login-card"><h2>Real API login</h2><p>Sign in with an account created in the existing Reflex database.</p><div class="api-status ${apiClass}"><i></i>${apiCopy}</div>${directOpenHint}<label>Phone number<input name="phone" type="tel" required autocomplete="username" /></label><label>Password<input name="password" type="password" required autocomplete="current-password" /></label><button class="button" type="submit">Sign in</button><p id="login-error" class="form-error" role="alert"></p><div class="test-accounts"><p class="test-accounts-label">Seeded test accounts (panel testing)</p><div class="test-account-buttons">${TEST_ACCOUNTS.map(acc => `<button type="button" class="test-account-button" data-test-phone="${acc.phone}" data-test-password="${acc.password}">${acc.role}</button>`).join("")}</div></div><section class="demo-access"><h3>DEMO MODE</h3><p>Backend unavailable? Explore Reflex with temporary frontend-only data. No demo action contacts the API.</p><div class="demo-buttons"><button class="demo-button" type="button" data-demo-role="retailer">Retailer Demo</button><button class="demo-button" type="button" data-demo-role="dispatcher">Dispatcher Demo</button><button class="demo-button" type="button" data-demo-role="rider">Rider Demo</button></div></section></form></section>`;
  document.querySelector("#login-form").addEventListener("submit", login); document.querySelectorAll("[data-demo-role]").forEach(button => button.addEventListener("click", () => startDemo(button.dataset.demoRole))); document.querySelectorAll("[data-test-phone]").forEach(button => button.addEventListener("click", () => { document.querySelector('[name="phone"]').value = button.dataset.testPhone; document.querySelector('[name="password"]').value = button.dataset.testPassword; document.querySelector("#login-form").requestSubmit(); }));
}

async function detectApiAvailability() { apiAvailability = "checking"; if (!session) renderLogin(); try { await api.health(); apiAvailability = "online"; } catch { apiAvailability = "offline"; } if (!session) renderLogin(); }
function startDemo(role) { const names = { retailer: "Amina Retail", dispatcher: "Grace Dispatcher", rider: "Brian" }; session = { mode: "demo", user: { id: `demo-${role}`, name: names[role], role } }; demoDeliveries = structuredClone(DEMO_SEED); render(); showToast(`Demo Mode started: ${role}. No backend data is being used.`); }

async function login(event) {
  event.preventDefault(); const form = new FormData(event.currentTarget); const button = event.currentTarget.querySelector("button[type=submit]"); button.disabled = true; button.textContent = "Signing in…";
  try { const token = await api.login(form.get("phone"), form.get("password")); session = { mode: "real", token: token.access_token, user: null }; session.user = await api.getCurrentUser(); localStorage.setItem(STORE_KEY, JSON.stringify(session)); await refreshDeliveries(); await refreshRiders(); render(); showToast(`Welcome, ${session.user.name}.`); }
  catch (error) { document.querySelector("#login-error").textContent = `${friendlyError(error)} Demo Mode remains available below.`; apiAvailability = "offline"; button.disabled = false; button.textContent = "Sign in"; }
}

async function createDelivery(event) {
  event.preventDefault(); const form = new FormData(event.currentTarget); const phone = String(form.get("customer_phone")).trim(); if (!/^[+0-9() -]{7,20}$/.test(phone)) return showToast("Enter a valid customer phone number.", "error"); const button = event.currentTarget.querySelector("button"); button.disabled = true; button.textContent = "Creating…";
  try { const payload = Object.fromEntries(form); payload.customer_phone = phone; if (isDemo()) { const nextId = Math.max(...demoDeliveries.map(d => d.id), 1000) + 1; demoDeliveries.unshift({ ...payload, id: nextId, reference: `RF-${nextId}`, status: "OPEN", assignedRiderName: null, created_at: new Date().toISOString() }); event.currentTarget.reset(); showToast("Demo delivery created successfully."); render(); return; } payload.creator_id = session.user.id; const delivery = await api.createDelivery(payload); showToast(`Delivery REF-${delivery.id} created successfully.`); event.currentTarget.reset(); await refreshDeliveries(); }
  catch (error) { showToast(friendlyError(error), "error"); }
  finally { if (button.isConnected) { button.disabled = false; button.textContent = "Create delivery"; } }
}

async function assignDelivery(event) {
  event.preventDefault(); const button = event.currentTarget.querySelector("button"); button.disabled = true; button.textContent = "Assigning…";
  try { if (isDemo()) { const riderName = new FormData(event.currentTarget).get("riderName"); if (!riderName) throw new ApiError("Select a demo rider before assigning."); const delivery = demoDeliveries.find(d => d.id === Number(event.currentTarget.dataset.deliveryId)); delivery.assignedRiderName = riderName; delivery.status = "ASSIGNED"; showToast("Rider assigned successfully — Demo Mode."); render(); return; } const riderId = new FormData(event.currentTarget).get("riderId"); if (!riderId) throw new ApiError("Enter a rider profile ID before assigning."); await api.assignDelivery(event.currentTarget.dataset.deliveryId, riderId, session.user.id); showToast("Rider assigned successfully."); await refreshDeliveries(); }
  catch (error) { showToast(friendlyError(error), "error"); }
  finally { if (button.isConnected) { button.disabled = false; button.textContent = "Assign rider"; } }
}

async function updateStatus(event) { const button = event.currentTarget; button.disabled = true; try { if (isDemo()) { const delivery = demoDeliveries.find(d => d.id === Number(button.dataset.statusId)); delivery.status = button.dataset.nextStatus; showToast(`${STATUS_LABELS[delivery.status]} confirmed — Demo Mode.`); render(); return; } await api.updateDeliveryStatus(button.dataset.statusId, button.dataset.nextStatus); showToast(`${STATUS_LABELS[button.dataset.nextStatus]} confirmed.`); await refreshDeliveries(); } catch (error) { showToast(friendlyError(error), "error"); if (button.isConnected) button.disabled = false; } }
function demoScan(event) { const delivery = demoDeliveries.find(d => d.id === Number(event.currentTarget.dataset.demoScan)); showToast(`Order ${delivery.reference} confirmed successfully — Demo Mode.`); }
function showScannerLimitation() { showToast("QR confirmation is not available yet: the existing backend exposes no scanning endpoint.", "error"); }
function bindCommonEvents() { document.querySelector("#logout")?.addEventListener("click", () => { localStorage.removeItem(STORE_KEY); session = null; deliveries = []; demoDeliveries = []; riders = []; render(); detectApiAvailability(); }); document.querySelector("#refresh")?.addEventListener("click", () => { if (isDemo()) { demoDeliveries = structuredClone(DEMO_SEED); showToast("Demo data reset."); render(); } else { refreshDeliveries(); refreshRiders().then(render); } }); }
function userIsEditingForm() { const form = document.querySelector("#delivery-form"); return !!(form && document.activeElement && form.contains(document.activeElement)); }

async function refreshDeliveries({ quiet = false } = {}) {
  if (!session || isDemo() || syncing) return;
  if (quiet && userIsEditingForm()) return;
  syncing = true; render();
  try { deliveries = await api.getDeliveries(); lastSynced = new Date(); apiAvailability = "online"; }
  catch (error) { apiAvailability = "offline"; if (!quiet) showToast(`${friendlyError(error)} You can log out and use Demo Mode.`, "error"); }
  finally { syncing = false; render(); }
}
async function refreshRiders() { if (!session || isDemo() || session.user.role !== "dispatcher") return; try { riders = await api.getRiders(); } catch { riders = []; } }
setInterval(() => { if (session?.mode === "real" && document.visibilityState === "visible") refreshDeliveries({ quiet: true }); }, POLL_MS);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && session?.mode === "real") refreshDeliveries({ quiet: true }); });
render(); if (session?.mode === "real") { refreshDeliveries({ quiet: true }); refreshRiders().then(render); } else detectApiAvailability();
