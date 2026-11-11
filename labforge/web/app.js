/* LabForge web UI. No build step: plain modern JavaScript. */
"use strict";

// ------------------------------------------------------------------ utilities
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body ? { "Content-Type": "application/json" } : {},
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const text = await res.text();
  let data; try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) throw new Error((data && data.detail) || `${res.status} ${res.statusText}`);
  return data;
}

const store = {
  get(k, d) { try { const v = localStorage.getItem("lf." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("lf." + k, JSON.stringify(v)); } catch { /* private mode */ } },
};

function toast(msg, kind = "info", ms = 3800) {
  const el = h(`<div class="toast ${kind}"><div>${msg}</div></div>`);
  $("#toasts").appendChild(el);
  setTimeout(() => { el.style.transition = "opacity .3s, transform .3s"; el.style.opacity = 0; el.style.transform = "translateY(6px)"; }, ms);
  setTimeout(() => el.remove(), ms + 350);
}

const fmt = {
  left(sec) {
    sec = Math.max(0, Math.floor(sec));
    const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = sec % 60;
    return hh ? `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}` : `${mm}:${String(ss).padStart(2, "0")}`;
  },
  dur(min) { return min >= 60 ? `${+(min / 60).toFixed(1)} h` : `${min} min`; },
  ago(ts) {
    const s = Date.now() / 1000 - ts;
    if (s < 45) return "just now";
    if (s < 3600) return `${Math.round(s / 60)} min ago`;
    if (s < 86400) return `${Math.round(s / 3600)} h ago`;
    return new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" });
  },
  time(ts) { return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }); },
  when(ts) { return new Date(ts * 1000).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); },
};

const greet = () => { const hr = new Date().getHours(); return hr < 12 ? "Good morning" : hr < 18 ? "Good afternoon" : "Good evening"; };
const initials = (n) => (n || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("") || "?";

// ------------------------------------------------------------------ icons
const ICON = {
  router: `<circle cx="12" cy="12" r="9"/><path d="M8 9.5h6.5M12 7l2.5 2.5L12 12M16 14.5H9.5M12 17l-2.5-2.5L12 12"/>`,
  switch: `<rect x="2.5" y="6" width="19" height="12" rx="2.5"/><path d="M6 10.5h9M13 8.5l2 2-2 2M18 13.5H9M11 11.5l-2 2 2 2"/>`,
  firewall: `<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9.5h18M3 14.5h18M9 4v5.5M15 9.5v5M9 14.5V20"/>`,
  host: `<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>`,
  rocket: `<path d="M5 15c-1.5 1.5-2 5-2 5s3.5-.5 5-2"/><path d="M14.5 4.5c3-1.5 5.5-1 5.5-1s.5 2.5-1 5.5l-6 6-4.5-4.5z"/><path d="M9.5 10.5 6 10l-2 2 4 1M13.5 14.5 14 18l-2 2-1-4"/>`,
  trash: `<path d="M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3"/>`,
  clock: `<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>`,
  check: `<path d="M5 12.5l4.5 4.5L19 7.5"/>`,
  x: `<path d="M6 6l12 12M18 6 6 18"/>`,
  play: `<path d="M7 5v14l11-7z"/>`,
  term: `<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>`,
  file: `<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>`,
  upload: `<path d="M12 16V4M7 9l5-5 5 5M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>`,
  plus: `<path d="M12 5v14M5 12h14"/>`,
  lock: `<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>`,
  layers: `<path d="M12 3 2 8l10 5 10-5z"/><path d="M2 13l10 5 10-5"/>`,
  zap: `<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>`,
  users: `<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.5-3.5 3.2-5.5 6.5-5.5s6 2 6.5 5.5M16 4.5a3.5 3.5 0 0 1 0 7M18.5 14.5c1.8.7 2.8 2.5 3 5.5"/>`,
  shield: `<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m8.5 12 2.5 2.5 4.5-4.5"/>`,
  cpu: `<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>`,
  back: `<path d="M15 18l-6-6 6-6"/>`,
  refresh: `<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>`,
  copy: `<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>`,
};
const icon = (name, cls = "") => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICON[name] || ""}</svg>`;
const KIND_LABEL = { router: "Router", switch: "Switch", firewall: "Firewall", host: "Host" };

// ------------------------------------------------------------------ topology renderer
function subnetOf(cidr) {
  const m = /^(\d+)\.(\d+)\.(\d+)\.(\d+)\/(\d+)$/.exec(cidr || "");
  if (!m) return null;
  const p = +m[5];
  const ip = ((+m[1] << 24) >>> 0) + (+m[2] << 16) + (+m[3] << 8) + +m[4];
  const mask = p === 0 ? 0 : (0xffffffff << (32 - p)) >>> 0;
  const n = (ip & mask) >>> 0;
  return `${n >>> 24}.${(n >>> 16) & 255}.${(n >>> 8) & 255}.${n & 255}/${p}`;
}

/* Renders in pixel space: node tiles keep a fixed size and the layout stretches to fit the box. */
function renderTopology(topo, opts = {}) {
  const { states = null, selected = null, labels = true, addresses = false, mini = false, status = "running", linksDown = [] } = opts;
  const W = opts.width || (mini ? 400 : 900), H = opts.height || (mini ? 200 : 520);
  const nodes = Object.entries(topo.nodes);
  const xs = nodes.map(([, n]) => n.pos[0]), ys = nodes.map(([, n]) => n.pos[1]);
  const minX = Math.min(...xs), minY = Math.min(...ys);
  const spanX = Math.max(1, Math.max(...xs) - minX), spanY = Math.max(1, Math.max(...ys) - minY);
  const T = mini ? 11 : 27;
  const padX = mini ? 30 : 70, padTop = mini ? 50 : 56, padBot = mini ? 22 : 70;
  const s = Math.min((W - 2 * padX) / spanX, (H - padTop - padBot) / spanY, mini ? 0.6 : 1.5);
  const ox = (W - spanX * s) / 2 - minX * s;
  const oy = padTop + (H - padTop - padBot - spanY * s) / 2 - minY * s;
  const P = (name) => { const [x, y] = topo.nodes[name].pos; return [ox + x * s, oy + y * s]; };
  const running = status === "running";
  const ifaceIp = (node, iface) => (topo.nodes[node].interfaces || {})[iface];

  let links = "", flows = "", ifl = "";
  topo.links.forEach(([a, b], i) => {
    const [na, ia] = a.split(":"), [nb, ib] = b.split(":");
    const [x1, y1] = P(na), [x2, y2] = P(nb);
    const isDown = linksDown.includes(i);
    links += `<line class="link ${isDown ? "down" : running && states ? "up" : ""}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
    if (states && !mini) links += `<line class="hit" data-link="${i}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"><title>${esc(a)} ↔ ${esc(b)}: click to ${isDown ? "restore" : "simulate a failure"}</title></line>`;
    if (isDown && !mini) {
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      flows += `<g class="cut" transform="translate(${mx},${my})"><circle r="11"/><path d="M-4-4l8 8M4-4l-8 8"/></g>`;
    } else if (running && states && !mini) {
      flows += `<line class="flow" style="animation-delay:${(i * -0.37).toFixed(2)}s" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
    }
    if (labels && !mini) {
      const len = Math.hypot(x2 - x1, y2 - y1) || 1;
      const offs = [];
      [[ia, x1, y1, x2, y2], [ib, x2, y2, x1, y1]].forEach(([ifc, sx, sy, tx, ty]) => {
        // Links leaving a node downwards start below its name label.
        const down = (ty - sy) / len > 0.45;
        const off = Math.min(down ? T + 58 : T + 24, len * (down ? 0.48 : 0.3));
        offs.push(off);
        const lx = sx + ((tx - sx) / len) * off, ly = sy + ((ty - sy) / len) * off;
        const w = ifc.length * 6.2 + 10;
        ifl += `<g class="ifl" transform="translate(${lx.toFixed(1)},${ly.toFixed(1)})"><rect x="${-w / 2}" y="-8.5" width="${w}" height="17" rx="5"/><text y="0.5">${esc(ifc)}</text></g>`;
      });
      if (addresses) {
        const net = subnetOf(ifaceIp(na, ia)) || subnetOf(ifaceIp(nb, ib));
        if (net && len - offs[0] - offs[1] > net.length * 6.2 + 40) {
          const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, w = net.length * 6.2 + 12;
          ifl += `<g class="ifl net" transform="translate(${mx.toFixed(1)},${my.toFixed(1)})"><rect x="${-w / 2}" y="-9.5" width="${w}" height="19" rx="9.5"/><text class="ip" y="0.5">${esc(net)}</text></g>`;
        }
      }
    }
  });

  let ns = "";
  nodes.forEach(([name, n]) => {
    const [x, y] = P(name);
    const st = states ? states[name] : null;
    const isUp = st && st.state === "running";
    const boot = status === "deploying";
    const color = `var(--k-${n.kind})`;
    const ic = T * 1.05;
    ns += `<g class="node ${selected === name ? "sel" : ""} ${boot ? "boot" : ""}" data-node="${esc(name)}" transform="translate(${x.toFixed(1)},${y.toFixed(1)})">
      <rect class="halo" x="${-T - 6}" y="${-T - 6}" width="${2 * T + 12}" height="${2 * T + 12}" rx="${T * 0.6}"/>
      <rect class="tile" x="${-T}" y="${-T}" width="${2 * T}" height="${2 * T}" rx="${T * 0.5}"
        style="fill:color-mix(in srgb, ${color} 15%, var(--surface));stroke:color-mix(in srgb, ${color} 55%, transparent)"/>
      <g transform="translate(${-ic / 2},${-ic / 2}) scale(${ic / 24})" style="color:${color}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${ICON[n.kind]}</g>
      ${states ? `<circle class="state" cx="${T - 3}" cy="${-T + 3}" r="6" style="fill:${isUp ? "var(--ok)" : boot ? "var(--warn)" : "var(--text-3)"}"/>` : ""}
      ${labels && !mini ? `<text class="nlabel" y="${T + 18}">${esc(name)}</text>` : ""}
      ${labels && !mini && n.label ? `<text class="nsub" y="${T + 32}">${esc(n.label)}</text>` : ""}
    </g>`;
  });

  return `<svg class="topo" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${links}${flows}${ifl}${ns}</svg>`;
}

// ------------------------------------------------------------------ app state
const state = {
  user: store.get("user", ""),
  catalog: null,
  kinds: null,
  health: null,
  timers: [],
  cleanup: [],
  term: null,
};

function clearTimers() { state.timers.forEach(clearInterval); state.timers = []; state.cleanup.forEach((f) => f()); state.cleanup = []; }
function every(ms, fn) { const id = setInterval(fn, ms); state.timers.push(id); return id; }

async function loadCatalog(force = false) {
  if (!state.catalog || force) state.catalog = await api("/api/catalog");
  return state.catalog;
}

// ------------------------------------------------------------------ theme & user
function applyTheme(t) { document.documentElement.dataset.theme = t; store.set("theme", t); }
(function initTheme() {
  const saved = store.get("theme", null);
  const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  document.documentElement.dataset.theme = saved || (prefersLight ? "light" : "dark");
})();
$("#theme-toggle").onclick = () => applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");

function renderUser() {
  $("#user-name").textContent = state.user || "Set your name";
  $("#user-avatar").textContent = initials(state.user);
}
function askName(force = false) {
  if (state.user && !force) return;
  openModal(`
    <div class="modal-head"><div><h2>Welcome to LabForge</h2><div class="sub">Your name is shown as the owner of the labs you launch.</div></div></div>
    <div class="modal-body"><div class="field"><label for="nm">Your name</label><input class="input" id="nm" maxlength="40" placeholder="e.g. Alex Morgan" value="${esc(state.user)}"></div></div>
    <div class="modal-foot"><button class="btn primary" id="nm-ok">Continue</button></div>`, { onOpen: (m) => {
    const inp = $("#nm", m); inp.focus(); inp.select();
    const ok = () => { const v = inp.value.trim(); if (!v) { inp.focus(); return; } state.user = v; store.set("user", v); renderUser(); closeModal(); };
    $("#nm-ok", m).onclick = ok; inp.onkeydown = (e) => e.key === "Enter" && ok();
  }, dismissable: !!state.user });
}
$("#user-chip").onclick = () => askName(true);

// ------------------------------------------------------------------ modal
let modalClose = null;
function openModal(inner, { wide = false, onOpen, dismissable = true, onClose } = {}) {
  const ov = $("#overlay");
  ov.innerHTML = ""; ov.hidden = false;
  const m = h(`<div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true">${inner}</div>`);
  ov.appendChild(m);
  modalClose = () => { ov.hidden = true; ov.innerHTML = ""; document.removeEventListener("keydown", onKey); modalClose = null; onClose && onClose(); };
  const onKey = (e) => { if (e.key === "Escape" && dismissable) closeModal(); };
  document.addEventListener("keydown", onKey);
  ov.onclick = (e) => { if (e.target === ov && dismissable) closeModal(); };
  $$("[data-close]", m).forEach((b) => (b.onclick = closeModal));
  onOpen && onOpen(m);
  return m;
}
function closeModal() { modalClose && modalClose(); }

// ------------------------------------------------------------------ launch flow
const TTL_CHOICES = [30, 60, 120, 240, 480];
function launchModal(tpl) {
  let ttl = TTL_CHOICES.includes(tpl.ttl_minutes) ? tpl.ttl_minutes : 120;
  const first = (state.user || "").split(" ")[0];
  openModal(`
    <div class="modal-head"><span class="kind-ico k-router" style="background:var(--accent-soft);color:var(--accent)">${icon("rocket")}</span>
      <div><h2>Launch ${esc(tpl.name)}</h2><div class="sub">${tpl.node_count} devices · ${tpl.link_count} links · ${tpl.check_count} built-in tests</div></div>
      <button class="btn ghost sm x" data-close>${icon("x")}</button></div>
    <div class="modal-body">
      <div class="field"><label for="ln">Lab name</label><input class="input" id="ln" maxlength="60" value="${esc(first ? `${first}'s ${tpl.name}` : tpl.name)}"></div>
      <div class="field"><label>Auto-destroy after</label><div class="seg" id="ttl">${TTL_CHOICES.map((m) => `<button data-m="${m}" class="${m === ttl ? "on" : ""}">${fmt.dur(m)}</button>`).join("")}</div></div>
      <div class="summary-box">
        <div><b>${tpl.node_count}</b>virtual devices</div>
        <div><b>~${tpl.mem_mb} MB</b>memory</div>
        <div><b id="ttl-at">—</b>destroys itself at</div>
      </div>
    </div>
    <div class="modal-foot"><button class="btn ghost" data-close>Cancel</button><button class="btn primary lg" id="go">${icon("rocket")}Launch lab</button></div>`,
  { onOpen: (m) => {
    const upd = () => { $("#ttl-at", m).textContent = new Date(Date.now() + ttl * 60000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); };
    upd();
    $$("#ttl button", m).forEach((b) => (b.onclick = () => { ttl = +b.dataset.m; $$("#ttl button", m).forEach((x) => x.classList.toggle("on", x === b)); upd(); }));
    $("#ln", m).focus();
    $("#go", m).onclick = async () => {
      const btn = $("#go", m); btn.disabled = true; btn.innerHTML = `<span class="spin"></span>Launching…`;
      try {
        const lab = await api("/api/labs", { method: "POST", body: { template: tpl.id, name: $("#ln", m).value, owner: state.user || "anonymous", ttl_minutes: ttl } });
        closeModal();
        toast(`<b>${esc(lab.name)}</b> is being built`, "ok");
        location.hash = `#/labs/${lab.id}`;
      } catch (e) {
        btn.disabled = false; btn.innerHTML = `${icon("rocket")}Launch lab`;
        toast(esc(e.message), "bad", 6000);
      }
    };
  } });
}

function templateModal(tpl) {
  openModal(`
    <div class="modal-head"><div><div class="eyebrow">${esc(tpl.category)}</div><h2>${esc(tpl.name)}</h2></div>
      <button class="btn ghost sm x" data-close>${icon("x")}</button></div>
    <div class="modal-body">
      <div class="detail-art" id="dart"></div>
      <div class="detail-grid">
        <div>
          <h4>About</h4><p class="muted" style="margin:0 0 18px">${esc(tpl.description || tpl.summary)}</p>
          <h4>Use it to</h4><ul>${tpl.use_cases.map((u) => `<li>${esc(u)}</li>`).join("")}</ul>
          <h4>Devices</h4>
          <div class="chips" style="margin-bottom:18px">${Object.entries(tpl.topology.nodes).map(([n, d]) => `<span class="chip k-${d.kind}"><span class="sw"></span>${esc(n)}</span>`).join("")}</div>
        </div>
        <div>
          <h4>Built-in tests (${tpl.check_count})</h4>
          <div class="card" style="box-shadow:none">${tpl.topology.checks.map((c) => `
            <div class="test wait"><span class="ic">${icon(c.expect === "fail" ? "shield" : "check")}</span>
              <div><div class="nm">${esc(c.name)}</div><div class="dt">${esc(c.type)} on ${esc(c.node)}${c.target ? " → " + esc(c.target) : ""}</div></div><span></span></div>`).join("")}
          </div>
        </div>
      </div>
    </div>
    <div class="modal-foot"><a class="btn ghost" href="/api/catalog/${tpl.id}/yaml" target="_blank">${icon("file")}View YAML</a><button class="btn primary" id="go">${icon("rocket")}Launch this lab</button></div>`,
  { wide: true, onOpen: (m) => {
    const art = $("#dart", m);
    art.innerHTML = renderTopology(tpl.topology, { width: art.clientWidth, height: art.clientHeight, addresses: true });
    $("#go", m).onclick = () => launchModal(tpl);
  } });
}

function importModal() {
  openModal(`
    <div class="modal-head"><div><h2>Add a topology</h2><div class="sub">Paste a LabForge YAML template. It is validated before it joins the catalog.</div></div>
      <button class="btn ghost sm x" data-close>${icon("x")}</button></div>
    <div class="modal-body"><textarea class="input" id="yml" rows="16" spellcheck="false" placeholder="id: my-lab&#10;name: My lab&#10;summary: ...&#10;nodes:&#10;  r1: {kind: router, pos: [100, 100], interfaces: {eth1: 10.0.0.1/30}}&#10;  ...&#10;links:&#10;  - [r1:eth1, r2:eth1]"></textarea><div id="yml-res"></div></div>
    <div class="modal-foot"><button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="go">${icon("upload")}Validate and add</button></div>`,
  { onOpen: (m) => {
    $("#go", m).onclick = async () => {
      try {
        const t = await api("/api/catalog", { method: "POST", body: { yaml: $("#yml", m).value } });
        closeModal(); toast(`<b>${esc(t.name)}</b> added to the catalog`, "ok"); await loadCatalog(true); route();
      } catch (e) { $("#yml-res", m).innerHTML = `<div class="result no">${esc(e.message)}</div>`; }
    };
  } });
}

function confirmDestroy(lab, after) {
  openModal(`
    <div class="modal-head"><span class="kind-ico" style="background:var(--bad-soft);color:var(--bad)">${icon("trash")}</span>
      <div><h2>Destroy this lab?</h2><div class="sub">${esc(lab.name)} · ${lab.node_count} devices</div></div></div>
    <div class="modal-body"><p class="muted" style="margin:0">All devices, links and unsaved configuration are removed immediately. The lab's history and test results stay in the activity log.</p></div>
    <div class="modal-foot"><button class="btn ghost" data-close>Keep it</button><button class="btn solid-danger" id="go">${icon("trash")}Destroy lab</button></div>`,
  { onOpen: (m) => {
    $("#go", m).onclick = async () => {
      $("#go", m).disabled = true;
      try { await api(`/api/labs/${lab.id}?by=${encodeURIComponent(state.user || "")}`, { method: "DELETE" }); closeModal(); toast(`Destroying <b>${esc(lab.name)}</b>`, "warn"); after && after(); }
      catch (e) { toast(esc(e.message), "bad"); closeModal(); }
    };
  } });
}

// ------------------------------------------------------------------ shared bits
function ttlRing(lab, size = 40) {
  const total = Math.max(1, lab.expires_at - lab.created_at);
  const frac = Math.max(0, Math.min(1, lab.remaining_seconds / total));
  const r = size / 2 - 4, c = 2 * Math.PI * r;
  const cls = lab.remaining_seconds < 300 ? "crit" : lab.remaining_seconds < 900 ? "low" : "";
  return `<svg class="ring ${cls}" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
    <circle class="bg" cx="${size / 2}" cy="${size / 2}" r="${r}"/>
    <circle class="fg" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c * (1 - frac)).toFixed(1)}"/></svg>`;
}
const statusPill = (s) => `<span class="pill ${s}">${s[0].toUpperCase() + s.slice(1)}</span>`;

function labRow(lab) {
  const tpl = (state.catalog || []).find((t) => t.id === lab.template);
  const active = ["running", "deploying", "destroying"].includes(lab.status);
  return `<a class="lab-row" href="#/labs/${lab.id}">
    ${active ? ttlRing(lab, 40) : `<span class="kind-ico" style="background:var(--surface-3);color:var(--text-3)">${icon("layers")}</span>`}
    <div style="min-width:0"><div class="title">${esc(lab.name)}</div>
      <div class="meta">${esc(tpl ? tpl.name : lab.template)} · ${esc(lab.owner)} · ${lab.node_count} devices${lab.last_checks ? ` · tests ${lab.last_checks.passed}/${lab.last_checks.total}` : ""}</div></div>
    <span class="faint mono" style="font-size:12.5px">${active ? fmt.left(lab.remaining_seconds) + " left" : fmt.ago(lab.destroyed_at || lab.created_at)}</span>
    ${statusPill(lab.status)}</a>`;
}

function eventRow(e, showLab = false) {
  return `<div class="ev ${e.level}"><time>${fmt.time(e.ts)}</time><span class="b"></span>
    <div>${showLab && e.lab_name ? `<a class="lab" href="#/labs/${e.lab_id}">${esc(e.lab_name)}</a> · ` : ""}${esc(e.message)}</div></div>`;
}

function emptyState(title, text, iconName = "layers") {
  return `<div class="empty">${icon(iconName)}<b>${esc(title)}</b>${text}</div>`;
}

// ------------------------------------------------------------------ pages
async function pageOverview(view) {
  view.innerHTML = `<div class="page">
    <div class="card hello">
      <svg class="hello-art" width="260" height="140" viewBox="0 0 260 140" fill="none" stroke="var(--accent)" stroke-width="1.5" opacity=".9">
        <circle cx="40" cy="30" r="9"/><circle cx="130" cy="80" r="11"/><circle cx="220" cy="35" r="9"/><circle cx="190" cy="120" r="7"/><circle cx="70" cy="115" r="7"/>
        <path d="M48 34l72 41M139 73l72-34M137 89l47 26M122 87l-45 24" stroke-dasharray="3 5"/></svg>
      <div><h2>${greet()}${state.user ? ", " + esc(state.user.split(" ")[0]) : ""}</h2>
        <p>Spin up a realistic network in seconds, test your change against it, and let it clean itself up. Nothing touches production.</p></div>
      <span class="spacer"></span>
      <a class="btn primary lg" href="#/catalog">${icon("rocket")}Launch a lab</a>
    </div>
    <div class="kpis" id="kpis">${'<div class="card kpi"><div class="skeleton" style="height:58px"></div></div>'.repeat(5)}</div>
    <div class="grid-2">
      <div class="stack">
        <div class="card"><div class="card-head"><h3>Running now</h3><span class="spacer"></span><a class="btn ghost sm" href="#/labs">All labs</a></div>
          <div class="card-body" style="padding:8px 0 4px"><div class="lab-list" id="running"></div></div></div>
        <div class="card"><div class="card-head"><h3>Labs launched</h3><span class="faint" style="font-size:12.5px">last 14 days</span></div>
          <div class="card-body"><div class="bars" id="bars"></div></div></div>
      </div>
      <div class="card"><div class="card-head"><h3>Activity</h3><span class="spacer"></span><a class="btn ghost sm" href="#/activity">View all</a></div>
        <div class="events" id="feed" style="max-height:520px"></div></div>
    </div>
  </div>`;
  await loadCatalog().catch(() => {});

  const refresh = async () => {
    const [stats, labs, events] = await Promise.all([api("/api/stats"), api("/api/labs?active=true"), api("/api/events?limit=30")]);
    const max = state.health ? state.health.max_active_labs : 10;
    $("#kpis").innerHTML = [
      { l: "Active labs", ic: "zap", v: stats.active_labs, s: `<small>/ ${max}</small>`, sub: "capacity in use", hero: true },
      { l: "Labs launched", ic: "rocket", v: stats.labs_launched_30d, sub: `by ${stats.engineers_30d} engineer${stats.engineers_30d === 1 ? "" : "s"} · 30 days` },
      { l: "Device-hours", ic: "cpu", v: stats.device_hours_30d, sub: "of lab time delivered · 30 days" },
      { l: "Time to ready", ic: "clock", v: stats.avg_deploy_seconds ?? "—", s: stats.avg_deploy_seconds != null ? "<small>s</small>" : "", sub: "average, launch to usable" },
      { l: "Test pass rate", ic: "shield", v: stats.check_pass_rate ?? "—", s: stats.check_pass_rate != null ? "<small>%</small>" : "", sub: `${stats.checks_total_30d} checks in ${stats.check_runs_30d} runs` },
    ].map((k) => `<div class="card kpi ${k.hero ? "hero" : ""}"><div class="label">${icon(k.ic)}${k.l}</div><div class="value">${k.v}${k.s || ""}</div><div class="sub">${k.sub}</div></div>`).join("");
    const peak = Math.max(1, ...stats.daily.map((d) => d.labs));
    $("#bars").innerHTML = stats.daily.map((d) => `<div class="bar ${d.labs ? "has" : ""}"><i data-v="${d.labs} lab${d.labs === 1 ? "" : "s"}" style="height:${(d.labs / peak) * 100}%"></i><span>${new Date(d.day + "T12:00").toLocaleDateString(undefined, { day: "numeric" })}</span></div>`).join("");
    $("#running").innerHTML = labs.length ? labs.map(labRow).join("") : emptyState("No labs running", `<div>Pick a topology from the <a href="#/catalog" style="color:var(--accent)">catalog</a> to start one.</div>`);
    $("#feed").innerHTML = events.length ? events.slice().reverse().map((e) => eventRow(e, true)).join("") : emptyState("Nothing yet", "Lab activity appears here.", "clock");
  };
  await refresh().catch((e) => toast(esc(e.message), "bad"));
  every(4000, () => refresh().catch(() => {}));
}

async function pageCatalog(view) {
  view.innerHTML = `<div class="page">
    <div class="page-head"><div><div class="eyebrow">Catalog</div><h1>Pick a topology</h1><p>Every template boots in seconds, ships with its own tests and destroys itself when time is up.</p></div>
      <span class="spacer"></span><button class="btn" id="import">${icon("upload")}Add topology</button></div>
    <div class="filters" id="filters"></div>
    <div class="catalog" id="cat">${'<div class="card" style="height:330px"><div class="skeleton" style="height:100%"></div></div>'.repeat(3)}</div>
    <div class="section-title"><h2>Device targets</h2><p>What each lab node runs today. Open images, no licences needed.</p></div>
    <div class="kinds" id="kinds"></div>
    <div class="section-title"><h2>Vendor images</h2><p>Plug in through the same driver interface once licensed images are in the registry.</p></div>
    <div class="roadmap" id="roadmap"></div>
  </div>`;
  $("#import").onclick = importModal;
  const [cat, kinds] = await Promise.all([loadCatalog(true), state.kinds ? state.kinds : api("/api/kinds")]);
  state.kinds = kinds;
  let filter = store.get("catFilter", "All");
  const cats = ["All", ...new Set(cat.map((t) => t.category))];
  if (!cats.includes(filter)) filter = "All";
  const draw = () => {
    $("#filters").innerHTML = cats.map((c) => `<button class="filter ${c === filter ? "on" : ""}" data-c="${esc(c)}">${esc(c)}</button>`).join("");
    $$("#filters .filter").forEach((b) => (b.onclick = () => { filter = b.dataset.c; store.set("catFilter", filter); draw(); }));
    const items = cat.filter((t) => filter === "All" || t.category === filter);
    $("#cat").innerHTML = items.map((t) => `
      <div class="card tpl" data-id="${t.id}">
        <div class="tpl-art"><span class="cat">${esc(t.category)}</span>${t.source !== "built-in" ? `<span class="src chip">Custom</span>` : ""}${renderTopology(t.topology, { mini: true, labels: false })}</div>
        <div class="tpl-body">
          <h3>${esc(t.name)}</h3><p>${esc(t.summary)}</p>
          <div class="chips">${Object.entries(t.kinds).map(([k, n]) => `<span class="chip k-${k}"><span class="sw"></span>${n} ${KIND_LABEL[k]}${n > 1 ? (k === "switch" ? "es" : "s") : ""}</span>`).join("")}</div>
          <div class="tpl-foot"><div class="tpl-stats"><span><b>${t.check_count}</b> tests</span><span><b>${fmt.dur(t.ttl_minutes)}</b> default</span><span class="diff ${t.difficulty}">${t.difficulty}</span></div>
            <span class="spacer"></span><button class="btn primary sm" data-launch="${t.id}">${icon("rocket")}Launch</button></div>
        </div>
      </div>`).join("");
    $$("#cat .tpl").forEach((el) => (el.onclick = (e) => {
      const t = cat.find((x) => x.id === el.dataset.id);
      if (e.target.closest("[data-launch]")) launchModal(t); else templateModal(t);
    }));
  };
  draw();
  $("#kinds").innerHTML = kinds.kinds.map((k) => `
    <div class="card kind-card"><div class="top"><span class="kind-ico k-${k.name}">${icon(k.name)}</span><div><h4>${esc(k.title)}</h4><div class="sub">stands in for ${esc(k.vendor_like)}</div></div></div>
      <p>${esc(k.description)}</p>
      <div class="img"><span class="pill ${k.image_ready ? "running" : "expired"}" style="height:20px;font-size:11px">${k.image_ready ? "Image ready" : "Pulled on first use"}</span>${esc((k.ready_image || k.image).split("/").pop())}</div></div>`).join("");
  $("#roadmap").innerHTML = kinds.roadmap.map((v) => `<div class="vendor"><b>${icon("lock")}${esc(v.name)}</b><span>${esc(v.licence)} · replaces ${esc(v.replaces)}</span></div>`).join("");
}

async function pageLabs(view) {
  view.innerHTML = `<div class="page">
    <div class="page-head"><div><div class="eyebrow">Labs</div><h1>My labs</h1><p>Everything running right now, plus every lab you have launched.</p></div>
      <span class="spacer"></span><a class="btn primary" href="#/catalog">${icon("plus")}New lab</a></div>
    <div class="card" style="margin-bottom:18px"><div class="card-head"><h3>Active</h3></div><div class="card-body" style="padding:8px 0 4px"><div class="lab-list" id="active"></div></div></div>
    <div class="card"><div class="card-head"><h3>History</h3></div><div class="card-body" style="padding:8px 0 0;overflow-x:auto" id="hist"></div></div>
  </div>`;
  await loadCatalog().catch(() => {});
  const refresh = async () => {
    const labs = await api("/api/labs");
    const active = labs.filter((l) => ["running", "deploying", "destroying"].includes(l.status));
    const past = labs.filter((l) => !active.includes(l));
    $("#active").innerHTML = active.length ? active.map(labRow).join("") : emptyState("No active labs", `<div><a href="#/catalog" style="color:var(--accent)">Launch one</a> in a few seconds.</div>`);
    $("#hist").innerHTML = past.length ? `<table class="data"><thead><tr><th>Lab</th><th>Template</th><th>Owner</th><th>Started</th><th>Ran for</th><th>Tests</th><th>Outcome</th></tr></thead><tbody>
      ${past.map((l) => {
        const tpl = (state.catalog || []).find((t) => t.id === l.template);
        const ran = l.destroyed_at ? Math.round((l.destroyed_at - (l.ready_at || l.created_at)) / 60) : 0;
        return `<tr data-id="${l.id}"><td><b>${esc(l.name)}</b></td><td class="muted">${esc(tpl ? tpl.name : l.template)}</td><td class="muted">${esc(l.owner)}</td>
          <td class="muted">${fmt.when(l.created_at)}</td><td class="muted">${ran} min</td><td class="muted">${l.last_checks ? `${l.last_checks.passed}/${l.last_checks.total}` : "—"}</td><td>${statusPill(l.status)}</td></tr>`;
      }).join("")}</tbody></table>` : emptyState("No history yet", "Finished labs are listed here.", "clock");
    $$("#hist tbody tr").forEach((tr) => (tr.onclick = () => (location.hash = `#/labs/${tr.dataset.id}`)));
  };
  await refresh();
  every(4000, () => refresh().catch(() => {}));
}

async function pageActivity(view) {
  view.innerHTML = `<div class="page">
    <div class="page-head"><div><div class="eyebrow">Activity</div><h1>Everything that happened</h1><p>Launches, config pushes, test runs and teardowns across all labs.</p></div></div>
    <div class="card"><div class="events" id="feed" style="max-height:none"></div></div></div>`;
  const refresh = async () => {
    const ev = await api("/api/events?limit=300");
    $("#feed").innerHTML = ev.length ? ev.slice().reverse().map((e) => eventRow(e, true)).join("") : emptyState("Nothing yet", "Lab activity appears here.", "clock");
  };
  await refresh();
  every(5000, () => refresh().catch(() => {}));
}

// ------------------------------------------------------------------ lab detail
async function pageLab(view, labId) {
  let lab, selected = null, tab = store.get("labTab", "tests"), showAddr = store.get("showAddr", true), lastEv = 0, testsRunning = false;
  const events = [];
  view.innerHTML = `<div class="page"><div class="skeleton" style="height:60px;margin-bottom:20px"></div><div class="skeleton" style="height:520px"></div></div>`;
  await loadCatalog().catch(() => {});
  try { lab = await api(`/api/labs/${labId}`); } catch (e) {
    view.innerHTML = `<div class="page">${emptyState("Lab not found", esc(e.message))}</div>`; return;
  }
  const tpl = (state.catalog || []).find((t) => t.id === lab.template);

  view.innerHTML = `<div class="page">
    <a class="back" href="#/labs">${icon("back")}My labs</a>
    <div class="lab-head">
      <div><h1><span id="lname">${esc(lab.name)}</span><span id="lstatus"></span></h1>
        <div class="meta"><span>Template <b>${esc(tpl ? tpl.name : lab.template)}</b></span><span>Owner <b>${esc(lab.owner)}</b></span>
          <span>Lab ID <b class="mono">${lab.id}</b></span><span id="lready"></span></div></div>
      <span class="spacer"></span>
      <div class="lab-actions">
        <div class="ttl" id="lttl"></div>
        <button class="btn" id="extend">${icon("clock")}+1 hour</button>
        <button class="btn danger" id="destroy">${icon("trash")}Destroy</button>
      </div>
    </div>
    <div class="lab-grid">
      <div>
        <div class="card canvas-card">
          <div class="canvas-tools"><b style="font-size:13.5px">Topology</b><span class="faint" style="font-size:12.5px">${lab.node_count} devices · ${lab.topology.links.length} links · click a device, or a link to fail it</span>
            <span class="spacer"></span><label class="toggle"><input type="checkbox" id="addr" ${showAddr ? "checked" : ""}><span class="sw"></span>Show addresses</label></div>
          <div class="canvas" id="canvas"></div>
        </div>
        <div class="tabs" id="tabs">
          <button class="tab" data-t="tests">${icon("shield")}Tests<span class="n" id="tn">${lab.topology.checks.length}</span></button>
          <button class="tab" data-t="events">${icon("clock")}Activity</button>
          <button class="tab" data-t="devices">${icon("layers")}Devices<span class="n">${lab.node_count}</span></button>
        </div>
        <div class="tab-panel card" id="panel"></div>
      </div>
      <div class="card inspector" id="insp"></div>
    </div></div>`;

  const isRunning = () => lab.status === "running";
  const isActive = () => ["running", "deploying", "destroying"].includes(lab.status);

  function drawHead() {
    $("#lstatus").innerHTML = statusPill(lab.status);
    $("#lready").innerHTML = lab.deploy_seconds ? `Ready in <b>${lab.deploy_seconds}s</b>` : "";
    $("#lttl").innerHTML = isActive()
      ? `${ttlRing(lab, 34)}<div><div class="t">${fmt.left(lab.remaining_seconds)}</div><small>until auto-destroy</small></div>`
      : `<div style="padding-left:8px"><div class="t" style="font-size:13px">${lab.status === "expired" ? "Expired" : "Ended"}</div><small>${lab.destroyed_at ? fmt.when(lab.destroyed_at) : ""}</small></div>`;
    $("#extend").disabled = !isActive() || lab.status === "destroying";
    $("#destroy").disabled = !isActive() || lab.status === "destroying";
  }

  function drawCanvas() {
    const c = $("#canvas");
    c.innerHTML = renderTopology(lab.topology, { states: lab.nodes || {}, selected, addresses: showAddr, status: lab.status,
      width: c.clientWidth, height: c.clientHeight, linksDown: (lab.runtime && lab.runtime.links_down) || [] });
    if (isRunning()) $$(".hit", c).forEach((ln) => (ln.onclick = () => linkModal(+ln.dataset.link)));
    if (lab.status === "deploying") c.appendChild(h(`<div class="deploying-banner"><span class="spin"></span>Building your lab…</div>`));
    if (lab.status === "destroying") c.appendChild(h(`<div class="deploying-banner"><span class="spin"></span>Tearing down…</div>`));
    if (!isActive()) c.appendChild(h(`<div class="gone-banner"><div><b>This lab has been ${lab.status === "failed" ? "stopped after an error" : lab.status}</b>
      <span class="faint">${lab.error ? esc(lab.error) : "Its devices are gone. Launch it again from the catalog any time."}</span>
      <div style="margin-top:14px"><button class="btn primary" id="relaunch">${icon("rocket")}Launch again</button></div></div></div>`));
    const rl = $("#relaunch"); if (rl && tpl) rl.onclick = () => launchModal(tpl);
    $$(".node", c).forEach((g) => (g.onclick = () => { selected = g.dataset.node; drawCanvas(); drawInspector(); }));
    $(".legend", c)?.remove();
    c.appendChild(h(`<div class="legend">${[...new Set(Object.values(lab.topology.nodes).map((n) => n.kind))].map((k) => `<span class="chip k-${k}"><span class="sw"></span>${KIND_LABEL[k]}</span>`).join("")}</div>`));
  }

  function drawInspector() {
    const el = $("#insp");
    if (!selected) {
      el.innerHTML = `<div class="insp-empty">${icon("cpu")}<b style="display:block;color:var(--text-2);margin-bottom:4px">Select a device</b>Click any device on the map to see its interfaces, open its console or push configuration.</div>`;
      return;
    }
    const spec = lab.topology.nodes[selected];
    const st = (lab.nodes || {})[selected] || {};
    const kind = (state.kinds?.kinds || []).find((k) => k.name === spec.kind);
    const ifaces = Object.entries(spec.interfaces || {});
    const ports = Object.entries(spec.ports || {});
    el.innerHTML = `
      <div class="insp-head"><span class="kind-ico k-${spec.kind}">${icon(spec.kind)}</span><div><h3>${esc(selected)}</h3><div class="sub">${esc(spec.label || KIND_LABEL[spec.kind])}</div></div>
        <span class="spacer" style="flex:1"></span>${st.state ? statusPill(st.state === "running" ? "running" : st.state) : ""}</div>
      <dl class="kv">
        <dt>Type</dt><dd>${esc(kind ? kind.title : spec.kind)}</dd>
        ${kind ? `<dt>Stands in for</dt><dd>${esc(kind.vendor_like)}</dd>` : ""}
        <dt>Image</dt><dd class="mono" style="font-size:12px">${esc(st.image || "—")}</dd>
        <dt>Mgmt address</dt><dd class="mono" style="font-size:12px">${esc(st.mgmt_ip || "—")}</dd>
      </dl>
      <div style="padding:12px 18px;border-bottom:1px solid var(--border)">
        <div class="faint" style="font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;font-weight:600;margin-bottom:4px">${ports.length ? "Switch ports" : "Interfaces"}</div>
        <table class="iftable">${ports.length
          ? ports.map(([p, m]) => `<tr><td>${esc(p)}</td><td>${m.access ? `access` : "trunk"}</td><td>VLAN ${m.access || (m.trunk || []).join(", ")}</td></tr>`).join("")
          : ifaces.map(([i, ip]) => `<tr><td>${esc(i)}</td><td class="mono">${esc(ip)}</td><td>${i === "lo" ? "loopback" : linkPeer(selected, i)}</td></tr>`).join("") || `<tr><td colspan="3" class="faint">No addresses</td></tr>`}
        </table>
        ${spec.gateway ? `<div class="faint" style="font-size:12.5px;margin-top:6px">Default gateway <span class="mono">${esc(spec.gateway)}</span></div>` : ""}
      </div>
      <div class="insp-actions">
        <button class="btn primary" id="i-con" ${isRunning() ? "" : "disabled"}>${icon("term")}Open console</button>
        <button class="btn" id="i-cfg" ${isRunning() ? "" : "disabled"}>${icon("file")}Config</button>
        <button class="btn" id="i-push" ${isRunning() ? "" : "disabled"}>${icon("upload")}Push change</button>
      </div>`;
    $("#i-con").onclick = () => openConsole(lab, selected);
    $("#i-cfg").onclick = () => configModal(lab, selected, false);
    $("#i-push").onclick = () => configModal(lab, selected, true);
  }

  function linkModal(i) {
    const [a, b] = lab.topology.links[i];
    const down = ((lab.runtime && lab.runtime.links_down) || []).includes(i);
    openModal(`
      <div class="modal-head"><span class="kind-ico" style="background:${down ? "var(--ok-soft)" : "var(--warn-soft)"};color:${down ? "var(--ok)" : "var(--warn)"}">${icon("zap")}</span>
        <div><h2>${down ? "Restore this link?" : "Simulate a link failure?"}</h2><div class="sub mono">${esc(a)} ↔ ${esc(b)}</div></div></div>
      <div class="modal-body"><p class="muted" style="margin:0">${down
        ? "Both interfaces come back up and routing re-converges."
        : "Both ends of the link go down, exactly like a cut fibre. Run the tests afterwards to see whether the network survives it."}</p></div>
      <div class="modal-foot"><button class="btn ghost" data-close>Cancel</button><button class="btn ${down ? "primary" : "solid-danger"}" id="go">${icon("zap")}${down ? "Restore link" : "Fail link"}</button></div>`,
    { onOpen: (m) => {
      $("#go", m).onclick = async () => {
        $("#go", m).disabled = true;
        try {
          lab = { ...lab, ...(await api(`/api/labs/${lab.id}/links/${i}`, { method: "POST", body: { up: down, by: state.user } })) };
          closeModal(); drawCanvas(); toast(down ? "Link restored" : `Link ${esc(a)} ↔ ${esc(b)} is down`, down ? "ok" : "warn");
        } catch (e) { closeModal(); toast(esc(e.message), "bad"); }
      };
    } });
  }

  function linkPeer(node, iface) {
    const end = `${node}:${iface.split(".")[0]}`;
    for (const [a, b] of lab.topology.links) { if (a === end) return "→ " + esc(b.split(":")[0]); if (b === end) return "→ " + esc(a.split(":")[0]); }
    return "";
  }

  function drawPanel() {
    $$("#tabs .tab").forEach((t) => t.classList.toggle("on", t.dataset.t === tab));
    const p = $("#panel");
    if (tab === "tests") {
      const run = lab.last_checks;
      const checksList = lab.topology.checks;
      const res = run ? run.results : null;
      const pct = run ? Math.round((run.passed / Math.max(1, run.total)) * 100) : 0;
      p.innerHTML = `
        <div class="tests-summary">
          ${run ? `<div class="score" style="color:${run.passed === run.total ? "var(--ok)" : "var(--bad)"}">${run.passed}/${run.total}</div>
            <div><b>${run.passed === run.total ? "All tests passed" : `${run.total - run.passed} test${run.total - run.passed > 1 ? "s" : ""} failed`}</b><div class="faint" style="font-size:12.5px">Last run ${fmt.ago(run.ts)}</div></div>
            <div class="progress ${run.passed === run.total ? "" : "bad"}" style="--p:${pct}%"><i style="width:${run.passed === run.total ? 100 : 100}%"></i></div>`
          : `<div><b>Prove the lab works</b><div class="faint" style="font-size:12.5px">Run the ${checksList.length} built-in tests now, and again after every change you push.</div></div>`}
          <span class="spacer"></span>
          <button class="btn primary" id="run" ${isRunning() && !testsRunning ? "" : "disabled"}>${testsRunning ? `<span class="spin"></span>Running…` : `${icon("play")}Run tests`}</button>
        </div>
        <div>${checksList.map((c, i) => {
          const r = res ? res[i] : null;
          const cls = testsRunning ? "wait" : r ? (r.ok ? "ok" : "no") : "wait";
          return `<div class="test ${cls}"><span class="ic">${testsRunning ? `<span class="spin" style="width:12px;height:12px"></span>` : icon(r ? (r.ok ? "check" : "x") : (c.expect === "fail" ? "shield" : "check"))}</span>
            <div style="min-width:0"><div class="nm">${esc(c.name)}${c.expect === "fail" ? `<span class="tag">must be blocked</span>` : ""}</div>
            <div class="dt">${r && !testsRunning ? esc(r.detail) : `${esc(c.type)} on ${esc(c.node)}${c.target ? " → " + esc(c.target) : ""}`}</div></div>
            <span class="tm">${r && !testsRunning ? r.seconds + "s" : ""}</span></div>`;
        }).join("")}</div>`;
      const btn = $("#run");
      if (btn) btn.onclick = runTests;
    } else if (tab === "events") {
      p.innerHTML = `<div class="events" id="levents">${events.map((e) => eventRow(e)).join("") || emptyState("No events", "")}</div>`;
      const le = $("#levents"); le.scrollTop = le.scrollHeight;
    } else {
      p.innerHTML = `<div style="overflow-x:auto"><table class="data"><thead><tr><th>Device</th><th>Type</th><th>State</th><th>Mgmt address</th><th>Image</th><th></th></tr></thead><tbody>
        ${Object.entries(lab.topology.nodes).map(([n, s]) => {
          const st = (lab.nodes || {})[n] || {};
          return `<tr data-n="${esc(n)}"><td><b>${esc(n)}</b> <span class="faint">${esc(s.label || "")}</span></td><td><span class="chip k-${s.kind}"><span class="sw"></span>${KIND_LABEL[s.kind]}</span></td>
            <td>${st.state ? statusPill(st.state === "running" ? "running" : st.state) : statusPill(lab.status === "deploying" ? "deploying" : "destroyed")}</td>
            <td class="mono">${esc(st.mgmt_ip || "—")}</td><td class="mono faint">${esc(st.image || "—")}</td>
            <td style="text-align:right"><button class="btn sm" data-con="${esc(n)}" ${isRunning() ? "" : "disabled"}>${icon("term")}Console</button></td></tr>`;
        }).join("")}</tbody></table></div>`;
      $$("[data-con]", p).forEach((b) => (b.onclick = (e) => { e.stopPropagation(); openConsole(lab, b.dataset.con); }));
      $$("tbody tr", p).forEach((tr) => (tr.onclick = () => { selected = tr.dataset.n; drawCanvas(); drawInspector(); }));
    }
  }

  async function runTests() {
    testsRunning = true; drawPanel();
    try {
      const run = await api(`/api/labs/${lab.id}/checks`, { method: "POST" });
      lab.last_checks = run;
      toast(run.passed === run.total ? `All ${run.total} tests passed` : `${run.total - run.passed} of ${run.total} tests failed`, run.passed === run.total ? "ok" : "bad");
    } catch (e) { toast(esc(e.message), "bad"); }
    testsRunning = false; drawPanel();
  }

  $$("#tabs .tab").forEach((t) => (t.onclick = () => { tab = t.dataset.t; store.set("labTab", tab); drawPanel(); }));
  $("#addr").onchange = (e) => { showAddr = e.target.checked; store.set("showAddr", showAddr); drawCanvas(); };
  $("#destroy").onclick = () => confirmDestroy(lab, () => poll());
  $("#extend").onclick = async () => {
    try { lab = { ...lab, ...(await api(`/api/labs/${lab.id}/extend`, { method: "POST", body: { minutes: 60 } })) }; drawHead(); toast("Added one hour", "ok"); }
    catch (e) { toast(esc(e.message), "bad"); }
  };

  let prevStatus = lab.status, prevStates = JSON.stringify(lab.nodes || {});
  async function poll() {
    try {
      const fresh = await api(`/api/labs/${labId}`);
      const ev = await api(`/api/labs/${labId}/events?after=${lastEv}`);
      if (ev.length) { events.push(...ev); lastEv = ev[ev.length - 1].id; }
      const statesStr = JSON.stringify(fresh.nodes || {});
      const changed = fresh.status !== prevStatus || statesStr !== prevStates;
      if (!testsRunning) fresh.last_checks = fresh.last_checks || lab.last_checks; else fresh.last_checks = lab.last_checks;
      lab = fresh;
      if (fresh.status !== prevStatus) {
        if (fresh.status === "running") toast(`<b>${esc(lab.name)}</b> is ready in ${lab.deploy_seconds}s`, "ok");
        if (fresh.status === "failed") toast(`Lab failed: ${esc(lab.error || "")}`, "bad", 8000);
        if (fresh.status === "expired") toast(`<b>${esc(lab.name)}</b> reached its lifetime and was destroyed`, "warn");
      }
      prevStatus = fresh.status; prevStates = statesStr;
      drawHead();
      if (changed) { drawCanvas(); drawInspector(); }
      if (tab === "events" && ev.length) drawPanel();
      if (changed && tab !== "events" && !testsRunning) drawPanel();
    } catch { /* transient */ }
  }
  const ev0 = await api(`/api/labs/${labId}/events`);
  events.push(...ev0); lastEv = ev0.length ? ev0[ev0.length - 1].id : 0;
  if (!state.kinds) state.kinds = await api("/api/kinds").catch(() => null);
  drawHead(); drawCanvas(); drawInspector(); drawPanel();
  let rsz; const onRs = () => { clearTimeout(rsz); rsz = setTimeout(() => $("#canvas") && drawCanvas(), 120); };
  window.addEventListener("resize", onRs); state.cleanup.push(() => window.removeEventListener("resize", onRs));
  every(1000, () => { if (isActive() && lab.remaining_seconds > 0) { lab.remaining_seconds -= 1; drawHead(); } });
  every(2500, poll);
}

// ------------------------------------------------------------------ config modal
function highlight(text, lang) {
  return esc(text).split("\n").map((ln) => {
    if (/^\s*(!|#)/.test(ln)) return `<span class="c">${ln}</span>`;
    if (lang === "frr") return ln.replace(/^(\s*)(router|interface|neighbor|network|address-family|ip|ipv6|exit-address-family|bgp|ospf|hostname|frr|service|line|exit)\b/, '$1<span class="k">$2</span>').replace(/\b(\d+\.\d+\.\d+\.\d+(\/\d+)?)\b/g, '<span class="n">$1</span>');
    if (lang === "nft") return ln.replace(/\b(table|chain|type|policy|accept|drop|counter|iifname|oifname|ct|state|comment|tcp|udp|dport)\b/g, '<span class="k">$1</span>');
    return ln.replace(/\b(\d+\.\d+\.\d+\.\d+(\/\d+)?)\b/g, '<span class="n">$1</span>');
  }).join("\n");
}

const PUSH_EXAMPLES = {
  frr: (node, spec) => /router bgp (\d+)/.test(spec.config || "")
    ? `! Example: advertise a new loopback prefix\ninterface lo\n ip address 10.99.${Math.floor(Math.random() * 200) + 10}.1/32\nrouter bgp ${spec.config.match(/router bgp (\d+)/)[1]}\n address-family ipv4 unicast\n  redistribute connected\n exit-address-family`
    : `! Example: change OSPF cost on a link\ninterface eth2\n ip ospf cost 50`,
  nft: (node, spec) => spec.ruleset || "flush ruleset\n",
  shell: () => `# Shell commands, run in order (set -e)\nip -br addr`,
};

async function configModal(lab, node, pushMode) {
  const spec = lab.topology.nodes[node];
  const m = openModal(`
    <div class="modal-head"><span class="kind-ico k-${spec.kind}">${icon(spec.kind)}</span><div><h2>${esc(node)} configuration</h2>
      <div class="sub">${pushMode ? "Edit, then push. The device validates it like the real thing would." : "Live running configuration"}</div></div>
      <button class="btn ghost sm x" data-close>${icon("x")}</button></div>
    <div class="modal-body"><div class="${pushMode ? "cfg-grid" : ""}">
      <div><h4>Running config <button class="btn ghost sm" id="refresh">${icon("refresh")}</button></h4><pre class="code" id="run"><span class="spin"></span></pre></div>
      ${pushMode ? `<div><h4>Change to push</h4><textarea class="input" id="cand" rows="18" spellcheck="false" wrap="off"></textarea><div id="res"></div></div>` : ""}
    </div></div>
    <div class="modal-foot">${pushMode ? `<span class="faint" style="margin-right:auto;font-size:12.5px;align-self:center">Tip: run the lab tests afterwards to prove the change is safe.</span><button class="btn ghost" data-close>Close</button><button class="btn primary" id="push">${icon("upload")}Push to ${esc(node)}</button>`
      : `<button class="btn ghost" id="cp">${icon("copy")}Copy</button><button class="btn" data-close>Close</button>`}</div>`, { wide: pushMode });
  let lang = "shell";
  const load = async () => {
    $("#run", m).innerHTML = `<span class="spin"></span>`;
    try { const r = await api(`/api/labs/${lab.id}/nodes/${node}/config`); lang = r.lang; $("#run", m).innerHTML = highlight(r.output.trimEnd(), r.lang); return r; }
    catch (e) { $("#run", m).textContent = e.message; return null; }
  };
  const r = await load();
  $("#refresh", m).onclick = load;
  if (!pushMode) { $("#cp", m).onclick = () => { navigator.clipboard?.writeText($("#run", m).textContent); toast("Copied", "ok", 1500); }; return; }
  const cand = $("#cand", m);
  cand.value = (PUSH_EXAMPLES[r ? r.lang : "shell"] || PUSH_EXAMPLES.shell)(node, spec);
  $("#push", m).onclick = async () => {
    const b = $("#push", m); b.disabled = true; b.innerHTML = `<span class="spin"></span>Pushing…`;
    try {
      const res = await api(`/api/labs/${lab.id}/nodes/${node}/config`, { method: "POST", body: { text: cand.value, by: state.user } });
      $("#res", m).innerHTML = `<div class="result ${res.ok ? "ok" : "no"}">${esc(res.output.trim() || (res.ok ? "Applied." : "Rejected."))}</div>`;
      if (res.ok) { toast(`Change pushed to <b>${esc(node)}</b>`, "ok"); load(); }
    } catch (e) { $("#res", m).innerHTML = `<div class="result no">${esc(e.message)}</div>`; }
    b.disabled = false; b.innerHTML = `${icon("upload")}Push to ${esc(node)}`;
  };
}

// ------------------------------------------------------------------ console drawer
function openConsole(lab, node) {
  closeConsole();
  const spec = lab.topology.nodes[node];
  const cmd = (lab.nodes?.[node]?.console || ["sh"]).join(" ");
  const d = h(`<div class="drawer">
    <div class="drawer-head"><span class="live"></span><span class="ttl-t">${esc(node)} <code>${esc(cmd)}</code></span>
      <span class="chip k-${spec.kind}" style="background:#151b27;border-color:#232b3d;color:#a5afc3"><span class="sw"></span>${KIND_LABEL[spec.kind]}</span>
      <span class="spacer"></span><button class="btn ghost sm" id="c-x">${icon("x")}Close</button></div>
    <div class="term" id="term"></div></div>`);
  document.body.appendChild(d);
  const term = new window.Terminal({
    fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace', fontSize: 13, cursorBlink: true, allowProposedApi: true,
    theme: { background: "#0b0e14", foreground: "#e8ecf4", cursor: "#ff6a3d", selectionBackground: "#33415580", black: "#0b0e14", brightBlack: "#6f7a91",
      red: "#ff5468", green: "#2fd17a", yellow: "#f5b54a", blue: "#5b9dff", magenta: "#a98bff", cyan: "#23c7b5", white: "#e8ecf4" },
  });
  const fit = new window.FitAddon.FitAddon();
  term.loadAddon(fit); term.open($("#term", d)); fit.fit(); term.focus();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/labs/${lab.id}/nodes/${node}/console`);
  ws.binaryType = "arraybuffer";
  const dec = new TextDecoder();
  ws.onopen = () => { ws.send(JSON.stringify({ type: "resize", rows: term.rows, cols: term.cols })); if (spec.kind === "router") setTimeout(() => ws.send(JSON.stringify({ type: "input", data: "\r" })), 150); };
  ws.onmessage = (e) => term.write(typeof e.data === "string" ? e.data : dec.decode(new Uint8Array(e.data), { stream: true }));
  ws.onclose = () => term.write("\r\n\x1b[2m[disconnected]\x1b[0m\r\n");
  term.onData((data) => ws.readyState === 1 && ws.send(JSON.stringify({ type: "input", data })));
  const onResize = () => { fit.fit(); ws.readyState === 1 && ws.send(JSON.stringify({ type: "resize", rows: term.rows, cols: term.cols })); };
  window.addEventListener("resize", onResize);
  state.term = { d, ws, term, onResize };
  $("#c-x", d).onclick = closeConsole;
}
function closeConsole() {
  if (!state.term) return;
  const { d, ws, term, onResize } = state.term;
  try { ws.close(); } catch { /* */ }
  term.dispose(); d.remove(); window.removeEventListener("resize", onResize);
  state.term = null;
}

// ------------------------------------------------------------------ router
async function route() {
  clearTimers(); closeConsole();
  const view = $("#view");
  const hash = location.hash.replace(/^#/, "") || "/";
  const parts = hash.split("/").filter(Boolean);
  const name = parts[0] === "labs" && parts[1] ? "labs" : parts[0] || "overview";
  $$(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === name));
  window.scrollTo(0, 0);
  try {
    if (!parts.length) await pageOverview(view);
    else if (parts[0] === "catalog") await pageCatalog(view);
    else if (parts[0] === "labs" && parts[1]) await pageLab(view, parts[1]);
    else if (parts[0] === "labs") await pageLabs(view);
    else if (parts[0] === "activity") await pageActivity(view);
    else view.innerHTML = `<div class="page">${emptyState("Page not found", "")}</div>`;
  } catch (e) {
    view.innerHTML = `<div class="page">${emptyState("Something went wrong", esc(e.message))}</div>`;
  }
}
window.addEventListener("hashchange", route);

async function heartbeat() {
  const el = $("#engine-status");
  try {
    const hl = await api("/api/health");
    state.health = hl;
    el.className = "engine " + (hl.docker.ok ? "ok" : "bad");
    el.lastElementChild.textContent = hl.docker.ok ? `Engine online · Docker ${hl.docker.version}` : "Docker unavailable";
    const labs = await api("/api/labs?active=true");
    $("#nav-active").textContent = labs.length || "";
  } catch {
    el.className = "engine bad"; el.lastElementChild.textContent = "LabForge offline";
  }
}

renderUser();
heartbeat(); setInterval(heartbeat, 5000);
route();
askName();
