const state = { token: localStorage.trackzyToken || "", user: null, view: "home", data: {}, track: "" };

const $ = (html) => {
  const n = document.createElement("template");
  n.innerHTML = html.trim();
  return n.content.firstChild;
};

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

function loadChatwoot() {
  fetch("/api/chat/config").then(r => r.json()).then(cfg => {
    if (!cfg.enabled || window.chatwootSDK) return;
    window.chatwootSettings = { position: "right", type: "expanded_bubble", launcherTitle: "Chat with support" };
    const s = document.createElement("script");
    s.src = cfg.base_url.replace(/\/$/, "") + "/packs/js/sdk.js";
    s.async = true;
    s.onload = () => window.chatwootSDK.run({ websiteToken: cfg.website_token, baseUrl: cfg.base_url });
    document.body.appendChild(s);
    const btn = document.getElementById("chatbtn");
    if (btn) btn.style.display = "none";
  }).catch(() => {});
}

function money(n, c = "USD") {
  return `${c} ${Number(n || 0).toLocaleString()}`;
}

async function boot() {
  const params = new URLSearchParams(location.search);
  if (params.get("track")) {
    state.track = params.get("track");
    return renderPublic();
  }
  loadChatwoot();
  if (!state.token) return renderLogin();
  try {
    state.user = await api("/api/me");
    state.view = state.user.role === "customer" ? "rfqs" : "shipments";
    await renderApp();
  } catch {
    state.token = "";
    renderLogin();
  }
}

function renderLogin() {
  document.getElementById("app").innerHTML = `
    <div class="login">
      <div class="brand"><div class="mark">T</div><div><strong>Trackzy</strong><small>Sourceeasy logistics</small></div></div>
      <h2>Sign in</h2>
      <p class="muted">Customer RFQ, ops quote, shipment, and public tracking. First build, own schema.</p>
      <label>Email</label><input id="email" value="customer@trackzy.test" />
      <label>Password</label><input id="password" type="password" value="customer123" />
      <p><button class="primary" id="go">Enter</button></p>
      <p class="muted">customer@trackzy.test / customer123<br>ops@trackzy.test / ops123<br>support@trackzy.test / support123<br>manager@trackzy.test / manager123<br>admin@trackzy.test / admin123</p>
      <p class="muted">Public sample: <a href="/?track=trk_8f3a21">trk_8f3a21</a></p>
    </div>`;
  document.getElementById("go").onclick = async () => {
    try {
      const out = await api("/api/login", { method: "POST", body: { email: email.value, password: password.value } });
      state.token = out.token;
      localStorage.trackzyToken = out.token;
      state.user = out.user;
      state.view = out.user.role === "customer" ? "rfqs" : "shipments";
      await renderApp();
    } catch (e) { alert(e.message); }
  };
}

async function renderPublic() {
  const s = await api("/api/track/" + state.track);
  document.getElementById("app").innerHTML = `
    <div class="public">
      <div class="brand"><div class="mark">T</div><div><strong>Trackzy</strong><small>Public tracking</small></div></div>
      <div class="panel" style="margin-top:16px">
        <h2>${s.reference}</h2>
        <p>${s.origin} → ${s.destination}</p>
        <p><span class="tag sea">${s.status}</span> <span class="tag">${s.load_type}</span></p>
        <div class="timeline">${s.timeline.map(e => `<div><strong>${e.status}</strong><div class="muted">${e.at || ""}</div></div>`).join("")}</div>
        <p class="muted">Supplier, value, and documents stay behind sign-in.</p>
      </div>
    </div>`;
}

function shell(body) {
  const role = state.user.role;
  const links = [
    ["rfqs", "RFQs"],
    ["shipments", "Shipments"],
    ["support", "Support chat"],
  ];
  if (role !== "customer") links.push(["direct", "Direct shipment"]);
  if (role === "admin" || role === "manager_ops") links.unshift(["tower", "Master"]);
  return `
    <header class="top">
      <div class="brand"><div class="mark">T</div><div><strong>Trackzy</strong><small>${role.replace("_", " ")}</small></div></div>
      <nav><span>${state.user.name}</span><button id="out">Sign out</button></nav>
    </header>
    <div class="layout">
      <aside class="side">${links.map(([id, label]) => `<button data-view="${id}" class="${state.view === id ? "on" : ""}">${label}</button>`).join("")}</aside>
      <main class="main">${body}</main>
    </div>
    <button class="primary" id="chatbtn" style="position:fixed;right:20px;bottom:20px">Chat with support</button>
    <div class="chat" id="chat"><header>Quick chat</header><div class="log" id="log"></div>
      <div style="display:flex;gap:6px;padding:8px"><input id="msg" placeholder="Message ops" /><button class="primary" id="send">Send</button></div>
    </div>`;
}

async function renderApp() {
  let body = "";
  if (state.view === "tower") body = await tower();
  if (state.view === "rfqs") body = await rfqs();
  if (state.view === "shipments") body = await shipments();
  if (state.view === "direct") body = directForm();
  if (state.view === "support") body = await supportPage();
  document.getElementById("app").innerHTML = shell(body);
  document.getElementById("out").onclick = () => { localStorage.removeItem("trackzyToken"); location.reload(); };
  document.querySelectorAll("[data-view]").forEach(b => b.onclick = async () => { state.view = b.dataset.view; await renderApp(); });
  document.getElementById("chatbtn").onclick = toggleChat;
  bind();
  if (state.view === "chat") fillChat(document.getElementById("fullchat"));
}

async function supportPage() {
  const rows = await api("/api/messages");
  const customers = state.user.role === "customer" ? [] : [...new Map(rows.map(m => [m.customer_id, m])).values()];
  state.chatCustomer = state.chatCustomer || (state.user.customer_id || rows[0]?.customer_id);
  const visible = state.user.role === "customer" ? rows : rows.filter(m => m.customer_id === state.chatCustomer);
  return `<h2>Support chat</h2>
    <p class="muted">Customers reach support here. Ops, support, and admin reply in the same thread. Shipment problems can be escalated to ops.</p>
    <div class="chatdesk">
      ${state.user.role === "customer" ? "" : `<aside class="panel">${customers.map(c => `<button data-cust="${c.customer_id}" class="${c.customer_id === state.chatCustomer ? "on" : ""}">Customer ${c.customer_id}</button>`).join("") || "<p class='muted'>No chats yet</p>"}</aside>`}
      <section class="panel">
        <div class="log" id="desklog">${visible.map(bubble).join("") || "<p class='muted'>No messages yet. Ask support about a shipment, document, or quote.</p>"}</div>
        <form id="deskform" class="row"><input id="deskmsg" placeholder="Write to support" /><button class="primary">Send</button></form>
      </section>
    </div>`;
}

function bubble(m) {
  const mine = m.role === state.user.role && m.author === state.user.name;
  return `<div class="bubble ${mine ? "mine" : ""}"><strong>${m.author}</strong> <span class="muted">${m.role}</span><div>${m.body}</div></div>`;
}

async function tower() {
  const d = await api("/api/dashboard");
  const cards = [
    ["Active shipments", d.active_shipments],
    ["RFQs pending", d.rfqs_pending],
    ["Quotes pending", d.quotes_pending],
    ["Direct shipments", d.direct_shipments],
    ["In transit", d.in_transit],
    ["Warehouse", d.warehouse],
    ["Customs pending", d.customs_pending],
    ["Delivered", d.delivered],
  ];
  return `<h2>Master dashboard</h2><div class="grid">${cards.map(([k, v]) => `<div class="card"><span>${k}</span><b>${v}</b></div>`).join("")}</div>`;
}

async function rfqs() {
  const rows = await api("/api/rfqs");
  state.data.rfqs = rows;
  const customer = state.user.role === "customer";
  return `<div class="row" style="justify-content:space-between"><h2>RFQs</h2>${customer ? `<button class="primary" id="newrfq">New RFQ</button>` : ""}</div>
    <div class="list">${rows.map(r => `
      <article class="panel item">
        <div><strong>${r.reference}</strong><div class="muted">${r.customer} · ${r.origin} → ${r.destination}</div></div>
        <div><span class="tag">${r.load_type}</span> <span class="tag sea">${r.status}</span></div>
        <div>${r.totals.weight_kg} kg · ${r.totals.cbm} CBM<br><span class="muted">${money(r.totals.value)}</span></div>
        <button data-open="${r.id}">Open</button>
      </article>`).join("") || `<p class="muted">No RFQs yet.</p>`}
    </div><div id="detail"></div>`;
}

async function shipments() {
  const rows = await api("/api/shipments");
  state.data.shipments = rows;
  return `<h2>Shipments</h2><div class="list">${rows.map(s => `
    <article class="panel">
      <div class="item">
        <div><strong>${s.reference}</strong><div class="muted">${s.customer} · ${s.source} · ${s.origin} → ${s.destination}</div></div>
        <div><span class="tag">${s.load_type}</span> <span class="tag sea">${s.status}</span></div>
        <div>${s.totals.weight_kg} kg · ${s.totals.cbm} CBM</div>
        <div class="muted">Public ${s.public_token}</div>
      </div>
      <div class="timeline">${s.timeline.map(e => `<div><strong>${e.status}</strong> <span class="muted">${e.actor}</span></div>`).join("")}</div>
      ${state.user.role !== "customer" ? `<div class="row" style="margin-top:8px"><select data-status="${s.id}">${(state.meta.statuses || []).map(x => `<option ${x === s.status ? "selected" : ""}>${x}</option>`).join("")}</select><button data-save="${s.id}">Update status</button></div>` : ""}
      <div class="muted" style="margin-top:8px">${(s.documents || []).map(d => `${d.name}: ${d.status}`).join(" · ")}</div>
    </article>`).join("")}</div>`;
}

function directForm() {
  return `<h2>Direct shipment</h2><form id="direct" class="panel">
    <label>Existing customer id (blank to create)</label><input name="customer_id" placeholder="1" />
    <label>New company</label><input name="company" />
    <label>Contact</label><input name="contact_name" />
    <label>Email</label><input name="email" />
    <label>Origin</label><input name="origin" value="Guangzhou, China" />
    <label>Destination</label><input name="destination" value="Mundra, India" />
    <label>Load</label><select name="load_type"><option>LCL</option><option>FCL</option></select>
    <label>Amount</label><input name="amount" value="0" />
    <p><button class="primary">Create shipment</button></p>
  </form>`;
}

function bind() {
  const open = document.querySelectorAll("[data-open]");
  open.forEach(b => b.onclick = () => showRfq(b.dataset.open));
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
    await api("/api/shipments", { method: "POST", body: { ...f, customer_id: f.customer_id ? Number(f.customer_id) : null, amount: Number(f.amount || 0), suppliers: [{ name: "Supplier", code: "SUP", products: [{ name: "Cargo", quantity: 1, weight_kg: 100, cbm: 1, unit_price: 10 }] }] } });
    state.view = "shipments";
    await renderApp();
  };
  document.querySelectorAll("[data-cust]").forEach(b => b.onclick = async () => { state.chatCustomer = Number(b.dataset.cust); await renderApp(); });
  const desk = document.getElementById("deskform");
  if (desk) desk.onsubmit = async (e) => {
    e.preventDefault();
    await api("/api/messages", { method: "POST", body: { body: document.getElementById("deskmsg").value, customer_id: state.chatCustomer, channel: "support" } });
    await renderApp();
  };
}

function showRfq(id) {
  const r = state.data.rfqs.find(x => String(x.id) === String(id));
  const box = document.getElementById("detail");
  const ops = state.user.role !== "customer";
  box.innerHTML = `<article class="panel" style="margin-top:16px">
    <h3>${r.reference}</h3>
    <p>${r.service_type} · ${r.notes || ""}</p>
    ${r.suppliers.map(s => `<h4>${s.name} ${s.code}</h4><ul>${s.products.map(p => `<li>${p.name} · ${p.quantity} ${p.unit} · ${p.weight_kg} kg · ${p.cbm} CBM · ${money(p.line_value)}</li>`).join("")}</ul>`).join("")}
    ${r.quotes.map(q => `<p><strong>${q.reference}</strong> ${money(q.amount, q.currency)} · ${q.payment_term} · ${q.status}<br>${q.included}</p>${q.status === "sent" && state.user.role === "customer" ? `<button class="primary" data-accept="${q.id}">Accept quote</button>` : ""}`).join("")}
    ${ops && r.status !== "accepted" ? `<form id="qf"><label>Quote amount</label><input name="amount" value="1500" /><label>Included</label><input name="included" value="Export, freight, destination CFS" /><p><button class="primary">Send quote</button></p></form>` : ""}
  </article>`;
  const qf = document.getElementById("qf");
  if (qf) qf.onsubmit = async (e) => {
    e.preventDefault();
    const amount = Number(new FormData(qf).get("amount"));
    await api(`/api/rfqs/${r.id}/quote`, { method: "POST", body: { amount, service_type: r.service_type, origin: r.origin, destination: r.destination, included: new FormData(qf).get("included"), payment_term: "pay_on_delivery" } });
    await renderApp();
  };
  const acc = box.querySelector("[data-accept]");
  if (acc) acc.onclick = async () => {
    const out = await api(`/api/quotes/${acc.dataset.accept}/accept`, { method: "POST", body: {} });
    alert(`Shipment ${out.shipment_reference}. Public token ${out.public_token}`);
    state.view = "shipments";
    await renderApp();
  };
}

function newRfq() {
  document.getElementById("detail").innerHTML = `<form id="rfqf" class="panel">
    <label>Origin</label><input name="origin" value="Yiwu, China" />
    <label>Destination</label><input name="destination" value="Nhava Sheva, India" />
    <label>Load</label><select name="load_type"><option>LCL</option><option>FCL</option></select>
    <label>Supplier</label><input name="supplier" value="Yiwu Bright Hardware" />
    <label>Product</label><input name="product" value="Cabinet hinges" />
    <label>Qty</label><input name="quantity" value="500" />
    <label>Weight kg</label><input name="weight_kg" value="120" />
    <label>CBM</label><input name="cbm" value="1.4" />
    <label>Unit price</label><input name="unit_price" value="0.4" />
    <p><button class="primary">Submit RFQ</button></p>
  </form>`;
  document.getElementById("rfqf").onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target).entries());
    await api("/api/rfqs", { method: "POST", body: {
      origin: f.origin, destination: f.destination, load_type: f.load_type, service_type: "Door-to-Door",
      suppliers: [{ name: f.supplier, code: "SUP", products: [{ name: f.product, quantity: Number(f.quantity), weight_kg: Number(f.weight_kg), cbm: Number(f.cbm), unit_price: Number(f.unit_price) }] }],
    }});
    await renderApp();
  };
}

boot().then(async () => { state.meta = await api("/api/meta").catch(() => ({ statuses: [] })); });
