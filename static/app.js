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

function loadChatwoot() {
  fetch("/api/chat/config").then(r => r.json()).then(cfg => {
    if (!cfg.enabled || window.chatwootSDK) return;
    window.chatwootSettings = { position: "right", type: "expanded_bubble", launcherTitle: "Chat with support" };
    const s = document.createElement("script");
    s.src = cfg.base_url.replace(/\/$/, "") + "/packs/js/sdk.js";
    s.async = true;
    s.onload = () => window.chatwootSDK.run({ websiteToken: cfg.website_token, baseUrl: cfg.base_url });
    document.body.appendChild(s);
  }).catch(() => {});
}

async function boot() {
  const params = new URLSearchParams(location.search);
  if (params.get("track")) { state.track = params.get("track"); return renderPublic(); }
  loadChatwoot();
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
        <div class="brand"><div class="mark">T</div><div><strong>Trackzy</strong><div class="muted">Sourceeasy logistics</div></div></div>
        <div>
          <h1>Move cargo from quote to delivery.</h1>
          <p>Customers raise an RFQ. Ops quotes it. Acceptance creates a shipment and a tracking number.</p>
          <div class="pills"><span>RFQ</span><span>Quote</span><span>FCL / LCL</span><span>Public tracking</span></div>
        </div>
        <p class="muted">Demo: customer@trackzy.test / customer123 · ops@trackzy.test / ops123</p>
      </div>
      <div class="panel-wrap">
        <form class="card" id="login">
          <h2>Sign in</h2>
          <p class="muted">Use your email or login name.</p>
          <label>Email or login name</label><input id="email" value="customer@trackzy.test" />
          <label>Password</label><input id="password" type="password" value="customer123" />
          <p class="row"><button class="primary" type="submit">Enter workspace</button><button class="ghost" type="button" id="reg">Request account</button></p>
          <p class="muted"><a href="/?track=trk_8f3a21">Track a shipment</a></p>
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
  const s = await api("/api/track/" + state.track);
  const steps = (state.meta?.statuses || s.timeline.map(e => e.status));
  const idx = steps.indexOf(s.status);
  document.getElementById("app").innerHTML = `
    <section class="panel-wrap" style="min-height:100vh">
      <div class="card" style="width:min(760px,100%);padding:28px">
        <div class="brand"><div class="mark">T</div><div><strong>Trackzy</strong><div class="muted">Public tracking</div></div></div>
        <h1>${s.reference}</h1>
        <p>${s.origin} → ${s.destination}</p>
        <p><span class="tag">${s.status}</span> <span class="tag warn">${s.load_type}</span></p>
        <div class="rail">${steps.map((_, i) => `<i class="${i <= idx ? "on" : ""}"></i>`).join("")}</div>
        ${s.timeline.map(e => `<p><strong>${e.status}</strong><br><span class="muted">${e.at || ""}</span></p>`).join("")}
        <p class="muted">Supplier, value, and documents stay behind sign-in.</p>
      </div>
    </section>`;
}

function shell(body) {
  const role = state.user.role;
  const links = [["rfqs", "RFQs"], ["shipments", "Shipments"], ["support", "Support"]];
  if (role !== "customer") links.push(["direct", "New shipment"], ["signups", "Accounts"]);
  if (role === "admin" || role === "manager_ops") links.unshift(["tower", "Overview"]);
  return `<div class="app">
    <aside class="side">
      <div class="brand"><div class="mark">T</div><div><strong>Trackzy</strong><div class="muted">${role.replaceAll("_", " ")}</div></div></div>
      ${links.map(([id, label]) => `<button data-view="${id}" class="${state.view === id ? "on" : ""}">${label}</button>`).join("")}
    </aside>
    <main class="main">
      <div class="topbar"><div><strong>${state.user.name}</strong><div class="muted">${state.user.email}</div></div><button class="ghost" id="out">Sign out</button></div>
      ${body}
    </main>
  </div>`;
}

async function renderApp() {
  const openId = state.openRfq;
  let body = "";
  if (state.view === "tower") body = await tower();
  if (state.view === "rfqs") body = await rfqs();
  if (state.view === "shipments") body = await shipments();
  if (state.view === "direct") body = directForm();
  if (state.view === "signups") body = await signups();
  if (state.view === "support") body = await supportPage();
  document.getElementById("app").innerHTML = shell(body);
  document.getElementById("out").onclick = () => { localStorage.removeItem("trackzyToken"); location.reload(); };
  document.querySelectorAll("[data-view]").forEach(b => b.onclick = async () => { state.view = b.dataset.view; await renderApp(); });
  bind();
  if (openId && state.view === "rfqs") showRfq(openId);
}

async function tower() {
  const d = await api("/api/dashboard");
  const cards = [["Active", d.active_shipments], ["RFQs", d.rfqs_pending], ["Quotes", d.quotes_pending], ["In transit", d.in_transit], ["Warehouse", d.warehouse], ["Customs", d.customs_pending], ["Delivered", d.delivered], ["Direct", d.direct_shipments]];
  return `<h2>Operations overview</h2><div class="kpis">${cards.map(([k, v]) => `<article class="card kpi"><span class="muted">${k}</span><b>${v}</b></article>`).join("")}</div>`;
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
      <p class="muted">${s.totals.weight_kg} kg · ${s.totals.cbm} CBM · public ${s.public_token}</p>
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

async function signups() {
  const rows = await api("/api/registrations");
  return `<h2>Account requests</h2><div class="list">${rows.map(r => `<article class="card" style="padding:16px;margin-bottom:12px"><strong>${r.name}</strong> <span class="tag">${r.status}</span><div class="muted">${r.login_name} · ${r.email} · ${r.phone}</div><p>${r.address}</p>${r.status === "pending" ? `<div class="row"><input data-pass="${r.id}" value="customer123" /><input data-co="${r.id}" placeholder="Company" /><button class="primary" data-approve="${r.id}">Create account</button><button class="ghost" data-reject="${r.id}">Reject</button></div>` : `<p class="muted">${r.note || ""}</p>`}</article>`).join("") || `<p class="muted">No requests.</p>`}</div>`;
}

async function supportPage() {
  const rows = await api("/api/messages");
  const customers = [...new Map(rows.map(m => [m.customer_id, m])).values()];
  state.chatCustomer = state.chatCustomer || state.user.customer_id || rows[0]?.customer_id;
  const visible = state.user.role === "customer" ? rows : rows.filter(m => m.customer_id === state.chatCustomer);
  return `<h2>Support</h2><div class="split">${state.user.role === "customer" ? "" : `<aside class="card" style="padding:12px">${customers.map(c => `<button class="ghost" data-cust="${c.customer_id}">Customer ${c.customer_id}</button>`).join("") || `<p class="muted">No chats</p>`}</aside>`}
    <section class="card" style="padding:16px"><div>${visible.map(m => `<div class="bubble ${m.author === state.user.name ? "mine" : ""}"><strong>${m.author}</strong><div>${m.body}</div></div>`).join("") || `<p class="muted">No messages yet.</p>`}</div>
    <form id="deskform" class="row"><input id="deskmsg" placeholder="Write to support" /><button class="primary">Send</button></form></section></div>`;
}

function bind() {
  document.querySelectorAll("[data-open]").forEach(b => b.onclick = () => showRfq(b.dataset.open));
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
    await api("/api/messages", { method: "POST", body: { body: document.getElementById("deskmsg").value, customer_id: state.chatCustomer } });
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
}

function showRfq(id) {
  state.openRfq = id;
  const r = state.data.rfqs.find(x => String(x.id) === String(id));
  const box = document.getElementById("detail");
  const ops = state.user.role !== "customer";
  const q = r.quotes[r.quotes.length - 1];
  box.innerHTML = `<article class="card" style="padding:16px;margin-top:12px"><h3>${r.reference}</h3><p>${r.service_type} · ${r.notes || ""}</p>
    ${r.suppliers.map(s => `<h4>${s.name}</h4><ul>${s.products.map(p => `<li>${p.name} · ${p.quantity} ${p.unit} · ${p.weight_kg} kg · ${p.cbm} CBM · ${money(p.line_value)}</li>`).join("")}</ul>`).join("")}
    ${r.quotes.map(item => `<p><strong>${item.reference}</strong> ${money(item.amount, item.currency)} · ${item.status}<br>${item.included || ""} ${item.transit ? "· " + item.transit : ""}</p>${item.status === "sent" && state.user.role === "customer" ? `<button class="primary" data-accept="${item.id}">Accept quote</button>` : ""}`).join("")}
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
    toast(`Shipment ${out.shipment_reference}. Public token ${out.public_token}`);
    state.view = "shipments"; await renderApp();
  };
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
