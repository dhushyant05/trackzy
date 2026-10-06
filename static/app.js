const state = { token: localStorage.trackzyToken || "", user: null, view: "shipments", data: {}, track: "", chatCustomer: null };

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}),
      ...(opts.headers || {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

function money(n, c = "USD") { return `${c} ${Number(n || 0).toLocaleString()}`; }
function toast(msg) { alert(msg); }

function hideTawk() {
  window.Tawk_API = window.Tawk_API || {};
  window.Tawk_API.onLoad = function () { window.Tawk_API.hideWidget(); };
  if (window.Tawk_API.hideWidget) window.Tawk_API.hideWidget();
}

function loadTawk() {
  if (state.user && state.user.role !== "customer") return hideTawk();
  if (window.__tawkLoaded) return;
  fetch("/api/chat/config").then(r => r.json()).then(cfg => {
    if (!cfg.enabled || !cfg.property_id || !cfg.widget_id) return;
    window.__tawkLoaded = true;
    window.Tawk_API = window.Tawk_API || {};
    window.Tawk_LoadStart = new Date();
    const s = document.createElement("script");
    s.async = true;
    s.src = `https://embed.tawk.to/${cfg.property_id}/${cfg.widget_id}`;
    s.charset = "UTF-8";
    s.setAttribute("crossorigin", "*");
    document.body.appendChild(s);
  }).catch(() => {});
}

async function boot() {
  const params = new URLSearchParams(location.search);
  if (params.get("track")) { state.track = params.get("track"); loadTawk(); return renderPublic(); }
  loadTawk();
  if (!state.token) return renderLogin();
  try {
    state.user = await api("/api/me");
    state.meta = await api("/api/meta");
    state.view = state.user.role === "customer" ? "rfqs" : (state.user.role === "admin" || state.user.role === "manager_ops" ? "tower" : "shipments");
    await renderApp();
  } catch { state.token = ""; renderLogin(); }
}

function renderLogin() {
  document.getElementById("app").innerHTML = `
    <section class="auth">
      <div class="hero">
        <div class="brand"><img class="logo" src="/static/logo.png" alt="Trackzy" /><div><strong>Trackzy</strong></div></div>
        <div>
          <h1>Move cargo from quote to delivery.</h1>
          <div class="pills"><span>RFQ</span><span>Quote</span><span>FCL / LCL</span><span>Public tracking</span></div>
        </div>
      </div>
      <div class="panel-wrap">
        <form class="card" id="login">
          <h2>Sign in</h2>
          <p class="muted">Use your email or login name.</p>
          <label>Email or login name</label><input id="email" />
          <label>Password</label><input id="password" type="password" />
          <p class="row"><button class="primary" type="submit">Enter workspace</button><button class="ghost" type="button" id="reg">Request account</button></p>
        </form>
        <form class="card" id="trackform" style="margin-top:16px">
          <h2>Track a shipment</h2>
          <p class="muted">Use the tracking number or shipment reference. No sign-in needed.</p>
          <label>Tracking number</label><input id="trackno" placeholder="trk_8f3a21 or SHP-1001" />
          <p><button class="primary" type="submit">Track</button></p>
        </form>
      </div>
    </section>`;
  document.getElementById("login").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const out = await api("/api/login", { method: "POST", body: { email: email.value, password: password.value } });
      state.token = out.token; localStorage.trackzyToken = out.token; state.user = out.user;
      state.meta = await api("/api/meta");
      state.view = out.user.role === "customer" ? "rfqs" : "shipments";
      await renderApp();
    } catch (err) { toast(err.message); }
  };
  document.getElementById("reg").onclick = renderRegister;
  document.getElementById("trackform").onsubmit = (e) => {
    e.preventDefault();
    const token = document.getElementById("trackno").value.trim();
    if (!token) return toast("Enter a tracking number");
    location.href = "/?track=" + encodeURIComponent(token);
  };
}

function renderRegister() {
  document.getElementById("app").innerHTML = `
    <section class="auth">
      <div class="hero"><div><h1>Request a customer login.</h1><p>Ops verifies the details, then creates the account. You cannot sign in until that happens.</p></div></div>
      <div class="panel-wrap"><form class="card" id="regform">
        <h2>Account request</h2>
        <label>Name</label><input name="name" required />
        <label>Login name</label><input name="login_name" required placeholder="acme.priya" />
        <label>Email</label><input name="email" type="email" required />
        <label>Phone</label><input name="phone" required />
        <label>Address</label><textarea name="address" required></textarea>
        <p class="row"><button class="primary">Send to ops</button><button class="ghost" type="button" id="back">Back</button></p>
      </form></div>
    </section>`;
  document.getElementById("back").onclick = renderLogin;
  document.getElementById("regform").onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target).entries());
    try { await api("/api/registrations", { method: "POST", body: f }); toast("Sent to ops. Sign in after they approve it."); renderLogin(); }
    catch (err) { toast(err.message); }
  };
}

async function renderPublic() {
  let s;
  try { s = await api("/api/track/" + encodeURIComponent(state.track)); }
  catch (err) {
    document.getElementById("app").innerHTML = `<section class="panel-wrap" style="min-height:100vh"><div class="card" style="padding:28px"><h2>Tracking number not found</h2><p>${err.message}</p><p><a href="/">Back</a></p></div></section>`;
    return;
  }
  const steps = s.timeline.map(e => e.status);
  document.getElementById("app").innerHTML = `
    <section class="panel-wrap" style="min-height:100vh">
      <div class="card" style="width:min(760px,100%);padding:28px">
        <div class="brand"><img class="logo" src="/static/logo.png" alt="Trackzy" /><div><strong>Trackzy</strong><div class="muted">Public tracking</div></div></div>
        <h1>${s.reference}</h1>
        <p>${s.origin} → ${s.destination}</p>
        <p><span class="tag">${s.status}</span> <span class="tag warn">${s.load_type}</span></p>
        <div class="rail">${steps.map(() => `<i class="on"></i>`).join("")}</div>
        ${s.timeline.map(e => `<p><strong>${e.status}</strong><br><span class="muted">${e.at || ""}</span></p>`).join("")}
        <p class="muted">Supplier, value, and documents stay behind sign-in.</p>
        <p><a href="/">Back to sign in</a></p>
      </div>
    </section>`;
}

function shell(body) {
  const role = state.user.role;
  const links = [["rfqs", "RFQs"], ["shipments", "Shipments"]];
  if (role !== "customer") links.unshift(["queue", "Queue"]);
  if (role === "customer") links.push(["profile", "My company"]);
  if (role !== "customer") links.push(["customers", "Customers"], ["direct", "New shipment"], ["signups", "Accounts"]);
  if (role === "admin" || role === "manager_ops") links.unshift(["tower", "Overview"]);
  return `<div class="app">
    <aside class="side">
      <div class="brand"><img class="logo" src="/static/logo.png" alt="Trackzy" /><div><strong>Trackzy</strong><div class="muted">${role.replaceAll("_", " ")}</div></div></div>
      ${links.map(([id, label]) => `<button data-view="${id}" class="${state.view === id ? "on" : ""}">${label}${id === "queue" && state.queueCount ? ` <span class="tag warn">${state.queueCount}</span>` : ""}</button>`).join("")}
    </aside>
    <main class="main">
      <div class="topbar"><div><strong>${state.user.name}</strong><div class="muted">${state.user.email}</div></div><button class="ghost" id="out">Sign out</button></div>
      ${notices.filter(n => !n.read).map(n => `<p class="tag warn">${n.title}: ${n.body} <button class="ghost" data-read="${n.id}">Dismiss</button></p>`).join("")}
      ${body}
    </main>
  </div>`;
}

async function renderApp() {
  const openId = state.openRfq;
  if (state.user.role !== "customer") {
    try { state.queueCount = (await api("/api/queue")).count; } catch { state.queueCount = 0; }
  }
  let body = "";
  if (state.view === "tower") body = await tower();
  if (state.view === "queue") body = await queuePage();
  if (state.view === "profile") body = await profilePage();
  if (state.view === "rfqs") body = await rfqs();
  if (state.view === "shipments") body = await shipments();
  if (state.view === "direct") body = directForm();
  if (state.view === "customers") body = await customersPage();
  if (state.view === "signups") body = await signups();
  if (state.view === "users") body = await usersPage();
  const notices = state.user.role === "customer" ? await api("/api/notices") : [];
  document.getElementById("app").innerHTML = shell(body);
  document.getElementById("out").onclick = () => { localStorage.removeItem("trackzyToken"); location.reload(); };
  document.querySelectorAll("[data-view]").forEach(b => b.onclick = async () => { state.view = b.dataset.view; await renderApp(); });
  bind();
  if (openId && state.view === "rfqs") showRfq(openId);
  loadTawk();
}

async function queuePage() {
  const data = await api("/api/queue");
  state.queueCount = data.count;
  return `<h2>Ops queue</h2><p class="muted">${data.count} item${data.count === 1 ? "" : "s"} waiting</p>
    <div class="list">${data.items.map(item => `<article class="card" style="padding:16px;margin-bottom:12px"><span class="tag warn">${item.action}</span> <strong>${item.title}</strong><div class="muted">${item.detail}</div>
      ${item.kind === "rfq" ? `<div class="row"><select data-assign="${item.id}">${data.staff.map(s => `<option value="${s.id}" ${s.id === item.assigned_to_id ? "selected" : ""}>${s.name}</option>`).join("")}</select><button class="ghost" data-assign-btn="${item.id}">Assign</button><button class="primary" data-open="${item.id}">Open RFQ</button></div>` : ""}
      ${item.kind === "account" ? `<button class="ghost" data-view-jump="signups">Open accounts</button>` : ""}
      ${item.kind === "document" || item.kind === "quote" ? `<button class="primary" data-open="${item.id}">Open RFQ</button>` : ""}
    </article>`).join("") || `<p class="muted">Nothing waiting.</p>`}</div>`;
}

async function profilePage() {
  const rows = await api("/api/customers");
  const c = rows[0];
  if (!c) return `<p class="muted">No company is linked to this login.</p>`;
  return `<h2>My company</h2><form id="profile" class="card" style="padding:18px;max-width:640px">
    <label>Company</label><input name="company" value="${c.company || ""}" />
    <label>Contact</label><input name="contact_name" value="${c.contact_name || ""}" />
    <label>Email</label><input name="email" value="${c.email || ""}" />
    <label>Phone</label><input name="phone" value="${c.phone || ""}" />
    <label>Address</label><textarea name="address">${c.address || ""}</textarea>
    <label>Country</label><input name="country" value="${c.country || ""}" />
    <label>Preferred lane</label><input name="preferred_lane" value="${c.preferred_lane || ""}" />
    <label>Preferred load</label><select name="preferred_load"><option ${c.preferred_load === "LCL" ? "selected" : ""}>LCL</option><option ${c.preferred_load === "FCL" ? "selected" : ""}>FCL</option></select>
    <label>Payment preference</label><input name="payment_preference" value="${c.payment_preference || ""}" />
    <input type="hidden" name="notes" value="${c.notes || ""}" />
    <p><button class="primary">Save company details</button></p>
  </form>`;
}

async function tower() {
  const d = await api("/api/dashboard");
  const cards = [["Active", d.active_shipments], ["RFQs", d.rfqs_pending], ["Quotes", d.quotes_pending], ["In transit", d.in_transit], ["Warehouse", d.warehouse], ["Customs", d.customs_pending], ["Documents", d.documents_pending], ["Delayed", d.delayed], ["Delivered", d.delivered], ["Direct", d.direct_shipments]];
  return `<h2>Operations overview</h2>
    <form id="search" class="row"><input name="q" placeholder="Search shipment or customer" /><button class="primary">Search</button></form>
    <div class="kpis">${cards.map(([k, v]) => `<article class="card kpi"><span class="muted">${k}</span><b>${v}</b></article>`).join("")}</div>
    <h3>Alerts</h3>${(d.alerts || []).map(a => `<p class="tag warn">${a}</p>`).join("") || `<p class="muted">No alerts.</p>`}
    <h3>Workload</h3>${(d.workload || []).map(w => `<p>${w.name}: ${w.assigned} assigned RFQs</p>`).join("")}
    <div id="found">${(d.search || []).map(s => `<p>${s.kind}: ${s.label}</p>`).join("")}</div>`;
}

async function usersPage() {
  const rows = await api("/api/users");
  const settings = await api("/api/settings");
  return `<h2>Users</h2>
    <form id="newuser" class="card" style="padding:16px;margin-bottom:12px">
      <label>Name</label><input name="name" required /><label>Email</label><input name="email" required /><label>Login</label><input name="login_name" />
      <label>Role</label><select name="role"><option>ops</option><option>support</option><option>manager_ops</option><option>admin</option><option>customer</option></select>
      <p><button class="primary">Create user</button></p>
    </form>
    ${rows.map(u => `<p>${u.name} · ${u.email} · <select data-role="${u.id}">${["admin","manager_ops","ops","support","customer"].map(r => `<option ${r === u.role ? "selected" : ""}>${r}</option>`).join("")}</select> <button class="ghost" data-role-save="${u.id}">Save role</button></p>`).join("")}
    <h3>Support routing</h3>
    <form id="mode"><select name="support_mode"><option ${settings.support_mode === "ops" ? "selected" : ""}>ops</option><option ${settings.support_mode === "support" ? "selected" : ""}>support</option><option ${settings.support_mode === "hybrid" ? "selected" : ""}>hybrid</option></select> <button class="primary">Save routing</button></form>`;
}

async function rfqs() {
  const rows = await api("/api/rfqs");
  state.data.rfqs = rows;
  return `<div class="topbar"><h2>RFQs</h2>${state.user.role === "customer" ? `<button class="primary" id="newrfq">New RFQ</button>` : ""}</div>
    <div class="card" style="padding:8px 16px"><table class="table"><thead><tr><th>Reference</th><th>Lane</th><th>Load</th><th>Cargo</th><th></th></tr></thead>
    <tbody>${rows.map(r => `<tr><td><strong>${r.reference}</strong><div class="muted">${r.customer}</div></td><td>${r.origin} → ${r.destination}</td><td><span class="tag">${r.status}</span></td><td>${r.totals.weight_kg} kg · ${r.totals.cbm} CBM</td><td><button class="ghost" data-open="${r.id}">Open</button></td></tr>`).join("") || `<tr><td colspan="5">No RFQs yet.</td></tr>`}</tbody></table></div><div id="detail"></div>`;
}

async function shipments() {
  const rows = await api("/api/shipments");
  state.data.shipments = rows;
  const steps = state.meta?.statuses || [];
  return `<h2>Shipments</h2><div class="split"><div>${rows.map(s => {
    const idx = steps.indexOf(s.status);
    return `<article class="card" style="padding:16px;margin-bottom:12px"><div class="row" style="justify-content:space-between"><div><strong>${s.reference}</strong><div class="muted">${s.customer} · ${s.origin} → ${s.destination}</div></div><span class="tag">${s.status}</span></div>
      <div class="rail">${steps.map((_, i) => `<i class="${i <= idx ? "on" : ""}"></i>`).join("")}</div>
      <p><a href="/?track=${s.public_token}">Tracking link</a> · <span class="muted">${s.public_token}</span></p>
      ${(s.documents || []).map(d => `<span class="tag warn">${d.name}: ${d.status}</span> `).join("")}
      ${state.user.role !== "customer" ? `<div class="row" style="margin-top:10px"><select data-status="${s.id}">${steps.map(x => `<option ${x === s.status ? "selected" : ""}>${x}</option>`).join("")}</select><button class="primary" data-save="${s.id}">Update</button></div>` : ""}
    </article>`;
  }).join("") || `<p class="muted">No shipments yet.</p>`}</div><aside class="card" style="padding:16px"><h3>Customer view</h3><p class="muted">Public pages hide supplier, value, and documents. Signed-in customers see the full shipment.</p></aside></div>`;
}

function directForm() {
  return `<h2>Open a shipment</h2><form id="direct" class="card" style="padding:18px;max-width:640px">
    <label>Existing customer id</label><input name="customer_id" placeholder="Leave blank to create" />
    <label>Company</label><input name="company" /><label>Contact</label><input name="contact_name" /><label>Email</label><input name="email" />
    <label>Origin</label><input name="origin" value="Guangzhou, China" /><label>Destination</label><input name="destination" value="Mundra, India" />
    <label>Load</label><select name="load_type"><option>LCL</option><option>FCL</option></select>
    <label>Amount</label><input name="amount" value="0" /><p><button class="primary">Create shipment</button></p>
  </form>`;
}

async function customersPage() {
  const rows = await api("/api/customers");
  state.data.customers = rows;
  return `<h2>Customer database</h2>
    <div class="card" style="padding:8px 16px"><table class="table"><thead><tr><th>Company</th><th>Contact</th><th>Preference</th><th>Orders</th><th></th></tr></thead>
    <tbody>${rows.map(c => `<tr><td><strong>${c.company}</strong><div class="muted">${c.email}</div></td><td>${c.contact_name}<br><span class="muted">${c.phone}</span></td><td>${c.preferred_lane || "Not set"} · ${c.preferred_load}</td><td>${c.orders} shipments · ${c.rfqs} RFQs</td><td><button class="ghost" data-customer="${c.id}">Open</button></td></tr>`).join("")}</tbody></table></div>
    <div id="customer"></div>`;
}

async function showCustomer(id) {
  const c = await api("/api/customers/" + id);
  document.getElementById("customer").innerHTML = `<article class="card" style="padding:16px;margin-top:12px">
    <h3>${c.company}</h3>
    <p>${c.contact_name} · ${c.email} · ${c.phone}<br>${c.address} ${c.country}</p>
    <form id="custform">
      <label>Preferred lane</label><input name="preferred_lane" value="${c.preferred_lane || ""}" />
      <label>Preferred load</label><select name="preferred_load"><option ${c.preferred_load === "LCL" ? "selected" : ""}>LCL</option><option ${c.preferred_load === "FCL" ? "selected" : ""}>FCL</option></select>
      <label>Payment preference</label><input name="payment_preference" value="${c.payment_preference || ""}" />
      <label>Notes</label><textarea name="notes">${c.notes || ""}</textarea>
      <label>Add history note</label><input name="history_note" placeholder="What changed or what they asked for" />
      <input type="hidden" name="company" value="${c.company}" /><input type="hidden" name="contact_name" value="${c.contact_name}" />
      <input type="hidden" name="email" value="${c.email}" /><input type="hidden" name="phone" value="${c.phone}" />
      <input type="hidden" name="address" value="${c.address || ""}" /><input type="hidden" name="country" value="${c.country || ""}" />
      <p><button class="primary">Save customer</button></p>
    </form>
    <h4>Previous orders</h4>${c.orders.map(o => `<p>${o.reference} · ${o.origin} → ${o.destination} · ${o.status} · ${money(o.amount, o.currency)}</p>`).join("") || "<p class='muted'>No shipments yet.</p>"}
    <h4>RFQs</h4>${c.rfqs.map(r => `<p>${r.reference} · ${r.origin} → ${r.destination} · ${r.status}</p>`).join("") || "<p class='muted'>No RFQs.</p>"}
    <h4>History</h4>${c.history.map(n => `<p><strong>${n.author}</strong> ${n.body}</p>`).join("") || "<p class='muted'>No notes yet.</p>"}
  </article>`;
  document.getElementById("custform").onsubmit = async (e) => {
    e.preventDefault();
    await api("/api/customers/" + id, { method: "PATCH", body: Object.fromEntries(new FormData(e.target).entries()) });
    toast("Customer saved");
    await renderApp();
    await showCustomer(id);
  };
}

async function signups() {
  const rows = await api("/api/registrations");
  return `<h2>Account requests</h2><div class="list">${rows.map(r => `<article class="card" style="padding:16px;margin-bottom:12px"><strong>${r.name}</strong> <span class="tag">${r.status}</span><div class="muted">${r.login_name} · ${r.email} · ${r.phone}</div><p>${r.address}</p>${r.status === "pending" ? `<div class="row"><input data-pass="${r.id}" value="customer123" /><input data-co="${r.id}" placeholder="Company" /><button class="primary" data-approve="${r.id}">Create account</button><button class="ghost" data-reject="${r.id}">Reject</button></div>` : `<p class="muted">${r.note || ""}</p>`}</article>`).join("") || `<p class="muted">No requests.</p>`}</div>`;
}

async function supportPage() {
  const data = await api("/api/messages");
  const rows = data.messages || [];
  const customers = data.customers || [];
  state.chatCustomer = state.chatCustomer || state.user.customer_id || customers[0]?.id;
  const visible = state.user.role === "customer" ? rows : rows.filter(m => m.customer_id === state.chatCustomer);
  const active = customers.find(c => c.id === state.chatCustomer);
  return `<h2>Support chat</h2>
    <div class="split">
      ${state.user.role === "customer" ? "" : `<aside class="card" style="padding:12px">${customers.map(c => `<button class="ghost" data-cust="${c.id}" style="display:block;width:100%;margin-bottom:6px;${c.id === state.chatCustomer ? "background:#ccfbf1" : ""}">${c.company}</button>`).join("")}</aside>`}
      <section class="card" style="padding:16px">
        <strong>${active ? active.company : "Your support thread"}</strong>
        <span id="online" class="tag" style="margin-left:8px">Checking</span>
        ${state.unread ? `<p class="tag warn">Reminder: ${state.unread} customer message${state.unread > 1 ? "s" : ""} waiting</p>` : ""}
        <div id="thread" style="min-height:280px;max-height:420px;overflow:auto;margin:12px 0">${visible.map(m => `<div class="bubble ${m.author === state.user.name ? "mine" : ""}"><strong>${m.author}</strong> <span class="muted">${m.role} · ${(m.at || "").slice(11, 16)}</span><div>${m.body}</div></div>`).join("") || `<p class="muted">No messages yet. Send the first one.</p>`}</div>
        <form id="deskform" class="row"><input id="deskmsg" placeholder="Write a message" autocomplete="off" /><button class="primary">Send</button></form>
      </section>
    </div>`;
}

function heartbeat() {
  clearInterval(state.beat);
  const tick = async () => {
    if (!state.token) return;
    const data = await api("/api/presence", { method: "POST", body: {} }).catch(() => null);
    if (!data) return;
    state.unread = data.unread || 0;
    state.online = data.online || [];
    const badge = document.querySelector("[data-view='support']");
    if (badge) badge.innerHTML = `Support${state.unread ? ` <span class="tag warn">${state.unread}</span>` : ""}`;
    const online = document.getElementById("online");
    if (online) {
      const staff = state.online.filter(u => u.role === "ops" || u.role === "support" || u.role === "manager_ops" || u.role === "admin");
      online.textContent = staff.length ? `Online: ${staff.map(u => u.name).join(", ")}` : "Ops offline";
      online.style.background = staff.length ? "#ecfdf5" : "#fee2e2";
    }
    if (state.unread && state.user.role !== "customer" && state.view !== "support" && state.unread !== state.alerted) {
      state.alerted = state.unread;
      if (Notification.permission === "granted") new Notification("Trackzy support", { body: `${state.unread} customer message waiting` });
    }
  };
  tick();
  state.beat = setInterval(tick, 15000);
  if (state.user && state.user.role !== "customer" && Notification.permission === "default") Notification.requestPermission();
}

function startChatPoll() {
  clearInterval(state.chatTimer);
  if (state.view !== "support") return;
  if (state.user.role !== "customer") api("/api/messages/read", { method: "POST", body: {} }).then(() => { state.unread = 0; });
  state.chatTimer = setInterval(async () => {
    if (state.view !== "support") return clearInterval(state.chatTimer);
    const box = document.getElementById("thread");
    const input = document.getElementById("deskmsg");
    if (!box || document.activeElement === input) return;
    const data = await api("/api/messages");
    const rows = (data.messages || []).filter(m => state.user.role === "customer" || m.customer_id === state.chatCustomer);
    box.innerHTML = rows.map(m => `<div class="bubble ${m.author === state.user.name ? "mine" : ""}"><strong>${m.author}</strong> <span class="muted">${m.role}</span><div>${m.body}</div></div>`).join("") || `<p class="muted">No messages yet.</p>`;
    box.scrollTop = box.scrollHeight;
  }, 4000);
}

function bind() {
  document.querySelectorAll("[data-read]").forEach(b => b.onclick = async () => { await api(`/api/notices/${b.dataset.read}/read`, { method: "POST", body: {} }); await renderApp(); });
  const search = document.getElementById("search");
  if (search) search.onsubmit = async (e) => { e.preventDefault(); const d = await api("/api/dashboard?q=" + encodeURIComponent(new FormData(search).get("q"))); document.getElementById("found").innerHTML = (d.search || []).map(s => `<p>${s.kind}: ${s.label}</p>`).join("") || "<p class='muted'>No match.</p>"; };
  const newuser = document.getElementById("newuser");
  if (newuser) newuser.onsubmit = async (e) => { e.preventDefault(); await api("/api/users", { method: "POST", body: Object.fromEntries(new FormData(newuser).entries()) }); toast("User created"); await renderApp(); };
  document.querySelectorAll("[data-role-save]").forEach(b => b.onclick = async () => { await api(`/api/users/${b.dataset.roleSave}?role=${document.querySelector(`[data-role='${b.dataset.roleSave}']`).value}`, { method: "PATCH", body: {} }); toast("Role saved"); });
  const mode = document.getElementById("mode");
  if (mode) mode.onsubmit = async (e) => { e.preventDefault(); await api("/api/settings?support_mode=" + new FormData(mode).get("support_mode"), { method: "PATCH", body: {} }); toast("Routing saved"); };
  document.querySelectorAll("[data-open]").forEach(b => b.onclick = async () => {
    state.view = "rfqs";
    state.openRfq = b.dataset.open;
    await renderApp();
  });
  document.querySelectorAll("[data-assign-btn]").forEach(b => b.onclick = async () => {
    const userId = document.querySelector(`[data-assign="${b.dataset.assignBtn}"]`).value;
    await api(`/api/rfqs/${b.dataset.assignBtn}/assign?user_id=${userId}`, { method: "POST", body: {} });
    toast("Assigned");
  });
  document.querySelectorAll("[data-view-jump]").forEach(b => b.onclick = async () => { state.view = b.dataset.viewJump; await renderApp(); });
  const profile = document.getElementById("profile");
  if (profile) profile.onsubmit = async (e) => {
    e.preventDefault();
    const rows = await api("/api/customers");
    await api("/api/customers/" + rows[0].id, { method: "PATCH", body: Object.fromEntries(new FormData(profile).entries()) });
    toast("Company details saved");
  };
  document.querySelectorAll("[data-download]").forEach(b => b.onclick = async () => {
    const res = await fetch(`/api/quotes/${b.dataset.download}/download`, { headers: { Authorization: `Bearer ${state.token}` } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `quote-${b.dataset.download}.html`; a.click();
  });
  document.querySelectorAll("[data-customer]").forEach(b => b.onclick = () => showCustomer(b.dataset.customer));
  document.querySelectorAll("[data-save]").forEach(b => b.onclick = async () => {
    const sel = document.querySelector(`[data-status="${b.dataset.save}"]`);
    await api(`/api/shipments/${b.dataset.save}/status`, { method: "POST", body: { status: sel.value, note: "Updated from ops" } });
    await renderApp();
  });
  const nr = document.getElementById("newrfq");
  if (nr) nr.onclick = newRfq;
  const df = document.getElementById("direct");
  if (df) df.onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(df).entries());
    const out = await api("/api/shipments", { method: "POST", body: { ...f, customer_id: f.customer_id ? Number(f.customer_id) : null, amount: Number(f.amount || 0), suppliers: [{ name: "Supplier", code: "SUP", products: [{ name: "Cargo", quantity: 1, weight_kg: 100, cbm: 1, unit_price: 10 }] }] } });
    toast(`Shipment ${out.reference}. Tracking ${out.public_token}`);
    state.view = "shipments"; await renderApp();
  };
  document.querySelectorAll("[data-cust]").forEach(b => b.onclick = async () => { state.chatCustomer = Number(b.dataset.cust); await renderApp(); });
  const desk = document.getElementById("deskform");
  if (desk) desk.onsubmit = async (e) => {
    e.preventDefault();
    const text = document.getElementById("deskmsg").value.trim();
    if (!text) return;
    if (state.user.role !== "customer" && !state.chatCustomer) return toast("Select a customer first");
    await api("/api/messages", { method: "POST", body: { body: text, customer_id: state.chatCustomer } });
    document.getElementById("deskmsg").value = "";
    await renderApp();
  };
  document.querySelectorAll("[data-approve]").forEach(b => b.onclick = async () => {
    const password = document.querySelector(`[data-pass="${b.dataset.approve}"]`).value;
    const company = document.querySelector(`[data-co="${b.dataset.approve}"]`).value;
    const out = await api(`/api/registrations/${b.dataset.approve}/approve`, { method: "POST", body: { password, company } });
    toast(`Account created. Login ${out.login_name} / ${out.password}`);
    await renderApp();
  });
  document.querySelectorAll("[data-reject]").forEach(b => b.onclick = async () => {
    await api(`/api/registrations/${b.dataset.reject}/reject`, { method: "POST", body: { note: "Rejected" } });
    await renderApp();
  });
  const chatbtn = document.getElementById("chatbtn");
  const chatpop = document.getElementById("chatpop");
  if (chatbtn) chatbtn.onclick = async () => {
    chatpop.style.display = chatpop.style.display === "none" ? "block" : "none";
    if (chatpop.style.display === "block") await fillPopup();
  };
  const close = document.getElementById("chatclose");
  if (close) close.onclick = () => { chatpop.style.display = "none"; };
  const pop = document.getElementById("popform");
  if (pop) pop.onsubmit = async (e) => {
    e.preventDefault();
    const text = document.getElementById("popmsg").value.trim();
    if (!text) return;
    await api("/api/messages", { method: "POST", body: { body: text, customer_id: state.chatCustomer || state.user.customer_id } });
    document.getElementById("popmsg").value = "";
    await fillPopup();
  };
}

async function fillPopup() {
  const data = await api("/api/messages");
  const id = state.user.role === "customer" ? state.user.customer_id : (state.chatCustomer || data.customers[0]?.id);
  state.chatCustomer = id;
  const rows = (data.messages || []).filter(m => m.customer_id === id);
  document.getElementById("poplog").innerHTML = rows.map(m => `<div class="bubble ${m.author === state.user.name ? "mine" : ""}"><strong>${m.author}</strong><div>${m.body}</div></div>`).join("") || "<p class='muted'>No messages yet.</p>";
}

function showRfq(id) {
  state.openRfq = id;
  const r = state.data.rfqs.find(x => String(x.id) === String(id));
  const box = document.getElementById("detail");
  const ops = state.user.role !== "customer";
  const q = r.quotes[r.quotes.length - 1];
  box.innerHTML = `<article class="card" style="padding:16px;margin-top:12px"><h3>${r.reference}</h3><p>${r.service_type} · ${r.notes || ""}</p>
    ${r.documents.map(d => `<p><span class="tag ${d.status === "approved" || d.status === "uploaded" ? "" : "warn"}">${d.name}: ${d.status}</span> ${d.file_name ? `<button class="ghost" data-file="${d.id}">Open</button>` : ""} ${ops ? `<select data-doc="${d.id}">${["required","uploaded","under_review","approved","rejected","missing"].map(s => `<option ${s === d.status ? "selected" : ""}>${s}</option>`).join("")}</select><button class="ghost" data-doc-save="${d.id}">Save</button>` : ""}</p>`).join("")}
    <div class="row">
      <form id="upinv"><input type="file" name="file" required /><button class="primary">Add invoice</button></form>
      <form id="uppack"><input type="file" name="file" required /><button class="primary">Add packing list</button></form>
      ${ops ? `<button class="ghost" id="askinv">Ask for invoice</button><button class="ghost" id="askpack">Ask for packing list</button>` : ""}
    </div>
    ${r.suppliers.map(s => `<h4>${s.name}</h4>${s.products.map(p => `<p>${p.name} · ${p.quantity} ${p.unit} · ${p.weight_kg} kg · ${p.cbm} CBM ${(p.photos || []).map(photo => `<button class="ghost" data-photo="${photo.id}">Photo</button>`).join("")} <form data-photo-form="${p.id}" class="row"><input type="file" name="file" accept="image/*" required /><button class="ghost">Add photo</button></form></p>`).join("")}`).join("")}
    ${r.quotes.map(item => `<p><strong>${item.reference}</strong> ${money(item.amount, item.currency)} · ${item.status}<br>${item.included || ""} ${item.transit ? "· " + item.transit : ""} <button class="ghost" data-download="${item.id}">Download quote</button></p>${item.status === "sent" && state.user.role === "customer" ? `<button class="primary" data-accept="${item.id}">Accept quote</button>` : ""}`).join("")}
    ${ops && r.status !== "accepted" ? `<form id="qf">
      <label>Amount</label><input name="amount" value="${q ? q.amount : 1500}" />
      <label>Currency</label><input name="currency" value="${q ? q.currency : "USD"}" />
      <label>Transit</label><input name="transit" value="${q ? (q.transit || "") : "18-22 days"}" />
      <label>Included</label><input name="included" value="${q ? (q.included || "") : "Export, freight, destination CFS"}" />
      <label>Excluded</label><input name="excluded" value="${q ? (q.excluded || "") : "Duty and last mile"}" />
      <label>Documents required</label><input name="documents_required" value="${q ? (q.documents_required || "") : "Invoice, packing list"}" />
      <label>Instructions</label><input name="instructions" value="${q ? (q.instructions || "") : ""}" />
      <label>Payment</label><select name="payment_term"><option ${q && q.payment_term === "pay_on_delivery" ? "selected" : ""}>pay_on_delivery</option><option ${q && q.payment_term === "partial_advance" ? "selected" : ""}>partial_advance</option><option ${q && q.payment_term === "full_advance" ? "selected" : ""}>full_advance</option></select>
      <p><button class="primary">${q ? "Save quote edits" : "Send quote"}</button></p>
    </form>` : ""}
  </article>`;
  const qf = document.getElementById("qf");
  if (qf) qf.onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(qf).entries());
    const payload = { ...f, amount: Number(f.amount), service_type: r.service_type, origin: r.origin, destination: r.destination };
    if (q && q.status !== "accepted") await api(`/api/quotes/${q.id}`, { method: "PATCH", body: payload });
    else await api(`/api/rfqs/${r.id}/quote`, { method: "POST", body: payload });
    toast("Quote saved");
    await renderApp();
  };
  const acc = box.querySelector("[data-accept]");
  if (acc) acc.onclick = async () => {
    const out = await api(`/api/quotes/${acc.dataset.accept}/accept`, { method: "POST", body: {} });
    toast(`Shipment ${out.shipment_reference}. Tracking /?track=${out.public_token}`);
    state.view = "shipments"; await renderApp();
  };
  async function upload(formId, kind) {
    const form = document.getElementById(formId);
    if (!form) return;
    form.onsubmit = async (e) => {
      e.preventDefault();
      const data = new FormData(form);
      const res = await fetch(`/api/rfqs/${r.id}/documents?kind=${kind}`, { method: "POST", headers: { Authorization: `Bearer ${state.token}` }, body: data });
      if (!res.ok) return toast("Upload failed");
      toast("Document saved");
      await renderApp();
    };
  }
  upload("upinv", "invoice");
  upload("uppack", "packing_list");
  const ask = async (kind) => { await api(`/api/rfqs/${r.id}/documents/request?kind=${kind}`, { method: "POST", body: {} }); toast("Document requested in chat"); await renderApp(); };
  const askinv = document.getElementById("askinv");
  const askpack = document.getElementById("askpack");
  if (askinv) askinv.onclick = () => ask("invoice");
  box.querySelectorAll("[data-file]").forEach(b => b.onclick = async () => {
    const res = await fetch(`/api/documents/${b.dataset.file}`, { headers: { Authorization: `Bearer ${state.token}` } });
    if (!res.ok) return toast("File not available");
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = `document-${b.dataset.file}`;
    a.click();
  });
  box.querySelectorAll("[data-doc-save]").forEach(b => b.onclick = async () => {
    const status = box.querySelector(`[data-doc="${b.dataset.docSave}"]`).value;
    await api(`/api/documents/${b.dataset.docSave}?status=${status}`, { method: "PATCH", body: {} });
    toast("Document updated");
    await renderApp();
  });
  box.querySelectorAll("[data-photo-form]").forEach(form => form.onsubmit = async (e) => {
    e.preventDefault();
    const res = await fetch(`/api/products/${form.dataset.photoForm}/photos`, { method: "POST", headers: { Authorization: `Bearer ${state.token}` }, body: new FormData(form) });
    if (!res.ok) return toast("Photo upload failed");
    toast("Photo saved");
    await renderApp();
  });
  box.querySelectorAll("[data-photo]").forEach(b => b.onclick = async () => {
    const res = await fetch(`/api/photos/${b.dataset.photo}`, { headers: { Authorization: `Bearer ${state.token}` } });
    if (!res.ok) return toast("Photo not found");
    window.open(URL.createObjectURL(await res.blob()), "_blank");
  });
}

function newRfq() {
  document.getElementById("detail").innerHTML = `<form id="rfqf" class="card" style="padding:16px;margin-top:12px">
    <label>Origin</label><input name="origin" value="Yiwu, China" /><label>Destination</label><input name="destination" value="Nhava Sheva, India" />
    <label>Load</label><select name="load_type"><option>LCL</option><option>FCL</option></select>
    <label>Supplier</label><input name="supplier" value="Yiwu Bright Hardware" /><label>Product</label><input name="product" value="Cabinet hinges" />
    <label>Qty</label><input name="quantity" value="500" /><label>Weight kg</label><input name="weight_kg" value="120" /><label>CBM</label><input name="cbm" value="1.4" /><label>Unit price</label><input name="unit_price" value="0.4" />
    <p><button class="primary">Submit RFQ</button></p></form>`;
  document.getElementById("rfqf").onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target).entries());
    await api("/api/rfqs", { method: "POST", body: { origin: f.origin, destination: f.destination, load_type: f.load_type, service_type: "Door-to-Door", suppliers: [{ name: f.supplier, code: "SUP", products: [{ name: f.product, quantity: Number(f.quantity), weight_kg: Number(f.weight_kg), cbm: Number(f.cbm), unit_price: Number(f.unit_price) }] }] } });
    await renderApp();
  };
}

boot();
