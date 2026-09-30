/* AstraScreen web app (plain JavaScript, no external libraries). */
const S = { token: null, user: null, view: "login", lot: null, sel: null, filter: "Flagged", q: "", lots: [], samples: [], model: null };
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cls = (s) => s.split(" ")[0];
const ROLE = { technician: "Lab technician", inspector: "QA inspector", engineer: "Reliability / QA engineer" };
const can = (a) => ({ upload: ["technician", "engineer"], actuals: ["technician", "engineer"], decide: ["inspector", "engineer"] }[a] || []).includes(S.user?.role);
const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch {} } };

async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {}, S.token ? { Authorization: "Bearer " + S.token } : {});
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const r = await fetch(path, { method: opts.method || (opts.body ? "POST" : "GET"), headers, body: opts.body });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && path !== "/api/login") { logout(); throw new Error(data.error || "Please sign in again."); }
  if (!r.ok) throw new Error(data.error || "Request failed");
  return data;
}
function toast(msg, err) {
  document.querySelectorAll(".toast").forEach((x) => x.remove());
  const t = document.createElement("div"); t.className = "toast" + (err ? " err" : ""); t.setAttribute("role", "status"); t.textContent = msg;
  document.body.appendChild(t); setTimeout(() => t.remove(), err ? 6000 : 3500);
}
function logout() { S.token = S.user = null; store.set("as_token", null); S.view = "login"; render(); }

/* ------------------------------------------------------------------ layout */
function header() {
  const lotOn = !!S.lot;
  return `<header class="top"><div class="brand">AstraScreen <small>AI review of burn-in screening</small></div>
  <nav aria-label="Main">
    <button data-v="lots" class="${S.view === "lots" ? "on" : ""}">Lots</button>
    <button data-v="lot" class="${S.view === "lot" ? "on" : ""}" ${lotOn ? "" : "disabled"}>${lotOn ? "Lot " + esc(S.lot.lot_id) : "Dashboard"}</button>
    <button data-v="audit" class="${S.view === "audit" ? "on" : ""}">Audit log</button>
    <button data-v="model" class="${S.view === "model" ? "on" : ""}">Model</button></nav>
  <span class="sp"></span>
  <div class="userbadge"><span><b>${esc(S.user.name)}</b> · ${esc(ROLE[S.user.role])}</span>
  <button class="btn-ghost btn-sm" id="switch">Switch user</button></div></header>`;
}
function bindHeader() {
  document.querySelectorAll("nav button").forEach((b) => (b.onclick = () => go(b.dataset.v)));
  $("switch").onclick = logout;
}
async function go(v) { S.view = v; if (v === "lots") await loadLots(); if (v === "lot" && S.lot) await openLot(S.lot.lot_id, true); render(); }

function render() {
  const app = $("app");
  if (S.view === "login" || !S.user) { app.innerHTML = loginView(); bindLogin(); return; }
  const body = { lots: lotsView, lot: lotView, audit: auditView, model: modelView }[S.view]();
  app.innerHTML = header() + `<main class="wrap">${body}</main>`;
  bindHeader();
  ({ lots: bindLots, lot: bindLot, audit: () => {}, model: () => {} }[S.view])();
}

/* ------------------------------------------------------------------ login */
function loginView() {
  const roles = [["technician", "Lab technician", "Uploads test files, fixes boards, records retests."],
                 ["inspector", "QA inspector", "Reviews flagged parts and records decisions."],
                 ["engineer", "Reliability / QA engineer", "Everything: upload, review, reveal 168h, reports."]];
  return `<main class="login"><h1>AstraScreen</h1>
  <p class="muted">AI-driven anomaly detection in component burn-in and screening (SIH26170). Sign in with your role.</p>
  <div class="card"><form id="lf"><label class="f" for="nm">Your name</label>
  <input type="text" id="nm" required maxlength="40" value="${esc(store.get("as_name") || "")}" placeholder="e.g. Shivansh" autocomplete="name">
  <span class="f" style="display:block;font-weight:600;margin:14px 0 0">Role</span>
  <div class="roles" role="radiogroup" aria-label="Role">${roles.map(([k, t, d], i) => `<label class="role ${i === 2 ? "on" : ""}"><input type="radio" name="role" value="${k}" ${i === 2 ? "checked" : ""}><b>${t}</b><span class="muted small">${d}</span></label>`).join("")}</div>
  <button class="btn-p" type="submit">Sign in</button></form></div>
  <p class="muted small" style="margin-top:14px">Demo build: the sample lots are simulated burn-in data, not real ISRO data.</p></main>`;
}
function bindLogin() {
  document.querySelectorAll(".role input").forEach((r) => (r.onchange = () => document.querySelectorAll(".role").forEach((l) => l.classList.toggle("on", l.contains(r) ? r.checked : false))));
  $("lf").onsubmit = async (e) => {
    e.preventDefault();
    const name = $("nm").value.trim(), role = document.querySelector(".role input:checked").value;
    try {
      const u = await api("/api/login", { json: { name, role } });
      S.token = u.token; S.user = u; store.set("as_token", u.token); store.set("as_name", name);
      await go("lots");
    } catch (err) { toast(err.message, true); }
  };
}

/* ------------------------------------------------------------------ lots */
async function loadLots() {
  [S.lots, S.samples, S.model] = await Promise.all([api("/api/lots"), api("/api/samples"), S.model ? S.model : api("/api/model")]);
}
function lotsView() {
  const up = can("upload");
  const ms = S.model?.stats || {};
  const rows = S.lots.map((l) => { const c = l.summary.counts; return `<tr class="row" data-lot="${esc(l.lot_id)}" tabindex="0">
    <td><b>${esc(l.lot_id)}</b><br><span class="muted small">${esc(l.filename)}</span></td><td class="num">${l.summary.parts}</td>
    <td>${c["Review part"] ? `<span class="pill p-Review">${c["Review part"]} review</span> ` : ""}${c["Check board"] ? `<span class="pill p-Check">${c["Check board"]} check board</span> ` : ""}${c["Fail"] ? `<span class="pill p-Fail">${c["Fail"]} fail</span> ` : ""}${c["Data check"] ? `<span class="pill p-Data">${c["Data check"]} data</span>` : ""}${!(c["Review part"] + c["Check board"] + c["Fail"] + c["Data check"]) ? '<span class="pill p-Routine">all routine</span>' : ""}</td>
    <td class="small">${esc(l.uploaded_by)}<br><span class="muted">${esc(l.uploaded_at)}</span></td><td>${l.validated ? "✓ 168h checked" : '<span class="muted">–</span>'}</td></tr>`; }).join("");
  return `<div class="grid2"><div class="stack">
    <section class="card"><h2>Screen a new lot (24h readings)</h2>
    ${up ? `<div class="drop" id="drop"><p style="margin:0 0 10px"><b>Drag a CSV or Excel file here</b></p>
      <label class="btn-o" style="display:inline-block;border:1px solid var(--blue);border-radius:6px;padding:8px 14px;cursor:pointer">Choose file<input type="file" id="file" accept=".csv,.xlsx,.xls" hidden></label></div>
      <div class="samples">${S.samples.map((s) => `<button class="btn-run" data-sample="${esc(s.name)}">Load sample lot ${esc(s.name.split("_")[0])} (${s.name.endsWith(".xlsx") ? "Excel" : "CSV"})</button>`).join("")}</div>`
      : `<p class="banner info">Your role (${esc(ROLE[S.user.role])}) reviews lots. A lab technician or engineer uploads new test files.</p>`}
    <details style="margin-top:14px"><summary class="small"><b>File format</b></summary><p class="small muted">One row per part. Required columns:
    <code>part_id</code> <code>board</code> <code>socket</code> <code>leak_0h_uA</code> <code>leak_24h_uA</code>. Optional: <code>lot_id</code>
    <code>row</code> <code>col</code> <code>current_24h_mA</code>. Columns in nA (e.g. <code>leak_24h_nA</code>) are converted automatically.
    Rows with missing or invalid readings are marked <b>Data check</b>.</p></details></section>
    <section class="card"><h2>How AstraScreen decides</h2><ol class="small" style="margin:0;padding-left:18px">
    <li><b>Hard limit</b> above ${S.model?.limit_uA ?? 50} µA → Fail (existing rule, always applies).</li>
    <li><b>Module C, part or board?</b> Flags bunched on one board → Check board, retest first.</li>
    <li><b>Module A, unusual part?</b> Far from similar parts in the same lot → Review part.</li>
    <li><b>Module B, drift by 168h?</b> Forecast near the limit or range too wide → Review part.</li>
    <li>Otherwise → Routine. The QA engineer makes the final call; every action is logged.</li></ol></section></div>
    <div class="stack"><section class="card"><h2>Screened lots</h2>${S.lots.length ? `<div class="tablewrap"><table><thead><tr><th>Lot</th><th>Parts</th><th>Result</th><th>Uploaded</th><th>168h</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="empty">No lots yet. Load a sample lot to start the demo.</p>'}</section>
    <section class="card"><h2>Forecast model (Module B)</h2><div class="kv">
    <span>Trained on</span><span>past lots ${esc((ms.train_lots || []).join(", "))}</span>
    <span>Range calibrated on</span><span>lot ${esc(ms.calibration_lot)}</span>
    <span>Tested on unseen lot</span><span>${esc(ms.test_lot)} (${ms.test_parts} parts)</span>
    <span>Forecast error</span><span><b>${ms.mae_uA?.toFixed(2)} µA</b> average (MAE)</span>
    <span>Range held true value</span><span><b>${ms.coverage ? (ms.coverage * 100).toFixed(0) : "–"}%</b> of parts (target 80%)</span></div>
    <p class="muted small" style="margin-bottom:0">Simulated history data. Retrain on ISRO lots before real use.</p></section></div></div>`;
}
function bindLots() {
  document.querySelectorAll("tr.row[data-lot]").forEach((r) => { r.onclick = () => openLot(r.dataset.lot); r.onkeydown = (e) => { if (e.key === "Enter") openLot(r.dataset.lot); }; });
  document.querySelectorAll("[data-sample]").forEach((b) => (b.onclick = () => screenFile(() => api("/api/samples/load", { json: { name: b.dataset.sample } }), b.dataset.sample)));
  const f = $("file"), d = $("drop");
  if (!f) return;
  const send = (file) => screenFile(() => api("/api/upload", { method: "POST", headers: { "X-Filename": encodeURIComponent(file.name) }, body: file }), file.name);
  f.onchange = () => f.files[0] && send(f.files[0]);
  d.ondragover = (e) => { e.preventDefault(); d.classList.add("over"); };
  d.ondragleave = () => d.classList.remove("over");
  d.ondrop = (e) => { e.preventDefault(); d.classList.remove("over"); e.dataTransfer.files[0] && send(e.dataTransfer.files[0]); };
}
async function screenFile(request, name) {
  const steps = ["Read and validate the file", "Module A: unusual part?", "Module B: 168h forecast", "Module C: part or board?"];
  const ov = document.createElement("div"); ov.className = "overlay";
  ov.innerHTML = `<div class="card" role="dialog" aria-label="Screening"><h2>Screening ${esc(name)}</h2><div class="steps">${steps.map((s, i) => `<div class="step" id="s${i}"><span>${i + 1}. ${s}</span><span id="t${i}"></span></div>`).join("")}</div></div>`;
  document.body.appendChild(ov);
  const anim = (async () => { for (let i = 0; i < 4; i++) { $("s" + i).classList.add("on"); await new Promise((r) => setTimeout(r, 600)); $("s" + i).classList.replace("on", "done"); $("t" + i).textContent = "✓"; } })();
  try { const [res] = await Promise.all([request(), anim]); ov.remove(); toast("Lot " + res.lot_id + " screened"); await openLot(res.lot_id); }
  catch (err) { ov.remove(); toast(err.message, true); }
}

/* ------------------------------------------------------------------ lot dashboard */
async function openLot(id, keep) {
  const lot = await api("/api/lots/" + encodeURIComponent(id));
  const prev = keep && S.lot?.lot_id === id ? S.sel : null;
  S.lot = lot; S.view = "lot";
  const order = [...lot.results].sort((a, b) => b.risk - a.risk);
  S.sel = prev || (order.find((p) => p.status === "Review part" && p.B) || order[0]).part_id;
  render();
}
const P = () => S.lot.results.find((p) => p.part_id === S.sel);
function short(p) {
  const med = S.lot.summary.median_uA;
  if (p.status === "Check board") return `Bunched with other flags on board ${p.board}`;
  if (p.status === "Fail") return `Above the ${S.lot.summary.limit_uA} µA limit at 24h`;
  if (p.status === "Data check") return "Missing or invalid reading";
  if (p.status === "Routine") return "In line with similar parts";
  const bits = [];
  if (p.A) bits.push(`${(p.leak_24h_uA / med).toFixed(1)}x lot median`);
  if (p.B) bits.push(`168h may reach ${p.f90.toFixed(0)} µA`);
  return bits.join("; ");
}
function fc(p) {
  if (p.status === "Check board") return '<span style="color:var(--teal)">Retest first</span>';
  if (p.f50 == null) return "–";
  return `${p.f50.toFixed(1)} <span class="muted">(${p.f10.toFixed(0)}–${p.f90.toFixed(0)})</span>`;
}
function lotView() {
  const L = S.lot, s = L.summary, c = s.counts, v = L.validation;
  const flagged = L.results.filter((p) => p.status !== "Routine").length;
  const stats = [["Routine", "--green", "--ok"], ["Review part", "--orange", "--orange"], ["Check board", "--teal", "--teal"], ["Fail", "--red", "--red"], ["Data check", "--purple", "--purple"]].filter(([k]) => k !== "Data check" || c[k]);
  const vb = v ? `<div class="banner ok" style="margin-bottom:14px"><div><b>Real 168h readings revealed.</b> Forecast error <b>${v.mae_uA.toFixed(2)} µA</b> on average; the range held <b>${(v.coverage * 100).toFixed(0)}%</b> of real values.
    ${v.over_limit_168h ? ` <b>${v.over_limit_flagged_at_24h} of ${v.over_limit_168h}</b> parts that went over the limit at 168h were already flagged at 24h. The fixed limit alone caught <b>${v.fixed_limit_caught_at_24h}</b> at 24h.` : " No part went over the limit at 168h."}</div></div>` : "";
  const filters = ["Flagged", "Review part", "Check board", "Fail", ...(c["Data check"] ? ["Data check"] : []), "Routine", "All"];
  const q = S.q.toLowerCase();
  let rows = [...L.results].sort((a, b) => b.risk - a.risk).filter((p) => S.filter === "All" || (S.filter === "Flagged" ? p.status !== "Routine" : p.status === S.filter)).filter((p) => !q || p.part_id.toLowerCase().includes(q));
  return `<div class="lothead"><h1>Lot ${esc(L.lot_id)}</h1><span class="muted small">${esc(L.filename)} · uploaded ${esc(L.uploaded_at)} by ${esc(L.uploaded_by)} · limit ${s.limit_uA} µA</span><span class="sp"></span>
    ${can("actuals") && !v ? `<button class="btn-run" id="reveal">Reveal real 168h readings</button><label class="btn-o" style="border:1px solid var(--blue);border-radius:6px;padding:8px 14px;cursor:pointer">Upload 168h file<input type="file" id="actfile" accept=".csv,.xlsx" hidden></label>` : ""}
    <a class="btn-o" style="border:1px solid var(--blue);border-radius:6px;padding:8px 14px;text-decoration:none" href="/report/${encodeURIComponent(L.lot_id)}?t=${S.token}" target="_blank" rel="noopener">QA report</a>
    <a class="btn-o" style="border:1px solid var(--blue);border-radius:6px;padding:8px 14px;text-decoration:none" href="/api/lots/${encodeURIComponent(L.lot_id)}/report.csv?t=${S.token}">Download CSV</a></div>
  ${vb}
  <section class="card summary" style="margin-bottom:16px">${stats.map(([k, t]) => `<div class="stat"><b style="color:var(${t})">${c[k]}</b><span>${k}</span></div>`).join("")}
    <div class="bar" aria-hidden="true">${stats.map(([k, , b]) => `<div style="width:${(c[k] / s.parts) * 100}%;background:var(${b})"></div>`).join("")}</div>
    <div class="stat"><b style="color:var(--navy)">${L.decided}/${flagged}</b><span>flags decided</span></div>
    <div class="stat" title="Supports the existing PDA lot check; does not replace it"><b style="color:var(${s.pda_warning ? "--red" : "--green"})">${s.at_risk_percent.toFixed(1)}%</b><span>may fail by 168h (PDA ${s.pda_percent}%)</span></div></section>
  <div class="grid2"><section class="card"><h2>Review queue, highest risk first</h2>
    <div class="chips" role="group" aria-label="Filter">${filters.map((f) => `<button class="chip ${S.filter === f ? "on" : ""}" data-f="${f}">${f}</button>`).join("")}
    <input type="search" id="q" placeholder="Search part" value="${esc(S.q)}" aria-label="Search part"></div>
    <div class="tablewrap" style="max-height:640px;overflow:auto"><table><thead><tr><th>Part</th><th>24h</th><th>168h forecast (range)</th>${v ? "<th>Real 168h</th>" : ""}<th>Status</th><th>Why</th></tr></thead><tbody>
    ${rows.length ? rows.map((p) => `<tr class="row ${p.part_id === S.sel ? "sel" : ""}" data-id="${esc(p.part_id)}" tabindex="0"><td style="white-space:nowrap"><b>${esc(p.part_id)}</b></td>
      <td class="num">${p.leak_24h_uA == null ? "–" : p.leak_24h_uA.toFixed(1) + " µA"}</td><td class="num">${fc(p)}</td>
      ${v ? `<td class="num" style="${p.actual_168h_uA > s.limit_uA ? "color:var(--red);font-weight:700" : ""}">${p.actual_168h_uA == null ? "–" : p.actual_168h_uA.toFixed(1)}</td>` : ""}
      <td><span class="pill p-${cls(p.status)}">${p.status}</span>${p.decision ? `<span class="dec">QA: ${esc(p.decision)}</span>` : ""}</td><td class="small muted">${short(p)}</td></tr>`).join("") : `<tr><td colspan="6" class="empty">No parts in this view.</td></tr>`}
    </tbody></table></div></section>
  <div class="stack"><section class="card"><h2>Burn-in boards (Module C: part or board?)</h2><div class="boards">${boardsHTML()}</div>
    <div class="legend"><span><i style="background:var(--ok)"></i>Routine</span><span><i style="background:var(--orange)"></i>Review part</span><span><i style="background:var(--teal)"></i>Check board</span><span><i style="background:var(--red)"></i>Fail</span>${c["Data check"] ? '<span><i style="background:var(--purple)"></i>Data check</span>' : ""}</div></section>
  <section class="card" id="ev">${evidenceHTML()}</section></div></div>`;
}
function boardsHTML() {
  const L = S.lot;
  return L.summary.boards.map((b) => {
    const ps = L.results.filter((p) => p.board === b.board).sort((x, y) => x.socket - y.socket);
    const note = b.board_fault ? `${b.flags} flags bunched together, unlikely by chance (p = ${b.p_value.toFixed(2)}). Check sockets, retest parts.` : b.flags ? "Flags scattered: treated as part faults." : "No flags.";
    const cells = [];
    for (let r = 0; r < b.rows; r++) for (let cc = 0; cc < b.cols; cc++) {
      const p = ps.find((x) => x.row === r && x.col === cc);
      cells.push(p ? `<button class="sock ${cls(p.status)} ${p.part_id === S.sel ? "sel" : ""}" data-id="${esc(p.part_id)}" title="${esc(p.part_id)}: ${p.status}" aria-label="${esc(p.part_id)} ${p.status}"></button>` : `<span></span>`);
    }
    return `<div class="board ${b.board_fault ? "fault" : ""}"><h3><span>Board ${b.board}</span><span class="muted" style="font-weight:400">${b.flags} flag${b.flags === 1 ? "" : "s"}</span></h3>
      <div class="bgrid" style="grid-template-columns:repeat(${b.cols},1fr)">${cells.join("")}</div><div class="bnote">${note}</div></div>`;
  }).join("");
}
function axes(W, x0, sy, lim) {
  return [0, 20, 40, 60].map((v) => `<line x1="${x0}" x2="${W - 10}" y1="${sy(v)}" y2="${sy(v)}" stroke="var(--grid)"/><text x="${x0 - 6}" y="${sy(v) + 4}" font-size="10" text-anchor="end" fill="var(--muted)">${v}</text>`).join("") +
    `<line x1="${x0}" x2="${W - 10}" y1="${sy(lim)}" y2="${sy(lim)}" stroke="var(--red)" stroke-dasharray="5 4" stroke-width="1.5"/><text x="${x0 + 4}" y="${sy(lim) - 5}" font-size="10" fill="var(--red)" font-weight="600">Limit ${lim} µA</text>`;
}
const yTop = (v) => Math.max(60, Math.ceil((v + 5) / 10) * 10);
function peerSVG(p) {
  const L = S.lot, lim = L.summary.limit_uA, W = 250, H = 190, x0 = 38, y0 = 12, h = H - 40;
  const ymax = yTop(Math.max(lim, ...L.results.map((q) => q.leak_24h_uA || 0))), sy = (v) => y0 + h - (Math.min(v, ymax) / ymax) * h;
  const dots = L.results.filter((q) => q.leak_24h_uA != null).map((q, i) => `<circle cx="${x0 + 20 + ((i * 37) % 70)}" cy="${sy(q.leak_24h_uA)}" r="2.6" fill="var(--blue)" opacity=".5"/>`).join("");
  const col = { "Check board": "var(--teal)", Routine: "var(--green)", Fail: "var(--red)", "Data check": "var(--purple)" }[p.status] || "var(--orange)";
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(p.part_id)} compared with similar parts">${axes(W, x0, sy, lim)}${dots}
  <line x1="${x0 + 14}" x2="${x0 + 96}" y1="${sy(L.summary.median_uA)}" y2="${sy(L.summary.median_uA)}" stroke="var(--navy)" stroke-width="2"/>
  ${p.leak_24h_uA != null ? `<circle cx="${x0 + 160}" cy="${sy(p.leak_24h_uA)}" r="7" fill="${col}" stroke="var(--card)" stroke-width="2"/>
  <text x="${x0 + 160}" y="${sy(p.leak_24h_uA) - 12}" font-size="11" text-anchor="middle" font-weight="700" fill="var(--ink)">${p.leak_24h_uA.toFixed(1)} µA</text>` : ""}
  <text x="${x0 + 55}" y="${H - 10}" font-size="11" text-anchor="middle" fill="var(--muted)">Lot (median ${L.summary.median_uA.toFixed(1)})</text>
  <text x="${x0 + 160}" y="${H - 10}" font-size="11" text-anchor="middle" fill="var(--muted)">This part</text>
  <text x="10" y="${y0 + h / 2}" font-size="10" fill="var(--muted)" transform="rotate(-90 10 ${y0 + h / 2})" text-anchor="middle">Leakage at 24h (µA)</text></svg>`;
}
function fcSVG(p) {
  const lim = S.lot.summary.limit_uA, W = 320, H = 190, x0 = 38, y0 = 12, w = W - x0 - 12, h = H - 40;
  const ymax = yTop(Math.max(lim, p.f90 || 0, p.actual_168h_uA || 0, p.leak_24h_uA || 0));
  const sx = (t) => x0 + (t / 168) * w, sy = (v) => y0 + h - (Math.min(v, ymax) / ymax) * h;
  const ax = [0, 20, 40, 60].filter((v) => v <= ymax).concat(ymax > 60 ? [ymax] : []);
  const axis = ax.map((v) => `<line x1="${x0}" x2="${W - 10}" y1="${sy(v)}" y2="${sy(v)}" stroke="var(--grid)"/><text x="${x0 - 6}" y="${sy(v) + 4}" font-size="10" text-anchor="end" fill="var(--muted)">${v}</text>`).join("") +
    `<line x1="${x0}" x2="${W - 10}" y1="${sy(lim)}" y2="${sy(lim)}" stroke="var(--red)" stroke-dasharray="5 4" stroke-width="1.5"/><text x="${sx(24) + 6}" y="${sy(lim) - 5}" font-size="10" fill="var(--red)" font-weight="600">Limit ${lim} µA</text>`;
  const paused = p.status === "Check board" || p.f50 == null;
  const msg = p.status === "Check board" ? ["Forecast paused", "reading may come from the board;", "retest in another board first"] : ["No forecast", "reading missing or invalid", ""];
  const act = p.actual_168h_uA != null ? `<path d="M${sx(168)} ${sy(p.actual_168h_uA) - 7} l6 7 l-6 7 l-6 -7z" fill="${p.actual_168h_uA > lim ? "var(--red)" : "var(--green)"}" stroke="var(--card)"/>
    <text x="${sx(168) - 10}" y="${sy(p.actual_168h_uA) + (p.actual_168h_uA > (p.f50 || 0) ? -8 : 18)}" font-size="10.5" text-anchor="end" font-weight="700" fill="${p.actual_168h_uA > lim ? "var(--red)" : "var(--green)"}">real ${p.actual_168h_uA.toFixed(1)}</text>` : "";
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="168 hour forecast for ${esc(p.part_id)}">
  <rect x="${sx(0)}" y="${y0}" width="${sx(24) - sx(0)}" height="${h}" fill="var(--measured)"/>${axis}
  ${[0, 24, 96, 168].map((t) => `<text x="${sx(t)}" y="${H - 14}" font-size="10" text-anchor="middle" fill="var(--muted)">${t}h</text>`).join("")}
  ${paused ? `<text x="${sx(100)}" y="${sy(ymax / 2)}" font-size="11" text-anchor="middle" fill="var(--teal)" font-weight="700">${msg[0]}</text>
  <text x="${sx(100)}" y="${sy(ymax / 2) + 15}" font-size="10.5" text-anchor="middle" fill="var(--teal)">${msg[1]}</text><text x="${sx(100)}" y="${sy(ymax / 2) + 29}" font-size="10.5" text-anchor="middle" fill="var(--teal)">${msg[2]}</text>` :
  `<polygon points="${sx(24)},${sy(p.leak_24h_uA)} ${sx(168)},${sy(p.f90)} ${sx(168)},${sy(p.f10)}" fill="var(--band)"/>
  <line x1="${sx(24)}" y1="${sy(p.leak_24h_uA)}" x2="${sx(168)}" y2="${sy(p.f50)}" stroke="var(--orange)" stroke-width="2" stroke-dasharray="6 4"/>
  <circle cx="${sx(168)}" cy="${sy(p.f50)}" r="4" fill="var(--orange)"/>
  <text x="${sx(168) - 8}" y="${Math.min(sy(p.f10) + 16, y0 + h - 6)}" font-size="10.5" text-anchor="end" font-weight="700" fill="var(--orange)">forecast ${p.f50.toFixed(1)}</text>`}
  ${p.leak_0h_uA != null && p.leak_24h_uA != null ? `<line x1="${sx(0)}" y1="${sy(p.leak_0h_uA)}" x2="${sx(24)}" y2="${sy(p.leak_24h_uA)}" stroke="var(--navy)" stroke-width="2.4"/>
  <circle cx="${sx(0)}" cy="${sy(p.leak_0h_uA)}" r="4" fill="var(--navy)"/><circle cx="${sx(24)}" cy="${sy(p.leak_24h_uA)}" r="4" fill="var(--navy)"/>` : ""}${act}
  <text x="${sx(12)}" y="${y0 + h - 4}" font-size="9.5" text-anchor="middle" fill="var(--muted)">measured</text>
  <text x="${sx(96)}" y="${y0 + h - 4}" font-size="9.5" text-anchor="middle" fill="var(--muted)">forecast, shaded = range</text>
  <text x="${x0 + w / 2}" y="${H - 1}" font-size="10" text-anchor="middle" fill="var(--muted)">Burn-in hours</text></svg>`;
}
function evidenceHTML() {
  const p = P(); if (!p) return '<p class="empty">Select a part.</p>';
  const k = { "Check board": "board", Routine: "ok", Fail: "fail", "Data check": "data" }[p.status] || "";
  const opts = p.status === "Check board" ? ["Retest in another board", "Board fixed, retested", "Investigate"] : p.status === "Routine" ? ["Continue screening", "Investigate"] : ["Continue screening", "Investigate", "Reject part"];
  const allowed = (o) => can("decide") || (S.user.role === "technician" && ["Retest in another board", "Board fixed, retested"].includes(o));
  return `<div class="ev-head"><h2 style="margin:0">${esc(p.part_id)}</h2><span class="muted small">Board ${p.board}, socket ${p.socket}</span><span class="sp"></span><span class="pill p-${cls(p.status)}">${p.status}</span></div>
  <div class="charts"><div>${peerSVG(p)}</div><div>${fcSVG(p)}</div></div>
  <div class="why ${k}"><b>${p.status === "Routine" ? "Result:" : "Why flagged:"}</b> ${esc(p.reason)}</div>
  <div class="actions">${opts.map((o) => `<button class="btn-o btn-sm ${p.decision === o ? "picked" : ""}" data-d="${o}" ${allowed(o) ? "" : 'disabled title="Your role cannot record this decision"'}>${o}</button>`).join("")}</div>
  <div class="actions"><input type="text" id="note" maxlength="200" placeholder="Note for the QA record (optional)" aria-label="Note">
  ${p.decision ? `<span class="saved">Saved: ${esc(p.decision)} · ${esc(p.decision_by)}</span>` : ""}</div>`;
}
function bindLot() {
  document.querySelectorAll("tr.row[data-id]").forEach((r) => { r.onclick = () => pick(r.dataset.id); r.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(r.dataset.id); } }; });
  document.querySelectorAll(".sock").forEach((s) => (s.onclick = () => pick(s.dataset.id)));
  document.querySelectorAll(".chip").forEach((c) => (c.onclick = () => { S.filter = c.dataset.f; render(); }));
  const q = $("q"); if (q) q.oninput = () => { S.q = q.value; const pos = q.selectionStart; render(); const n = $("q"); n.focus(); n.setSelectionRange(pos, pos); };
  document.querySelectorAll("[data-d]").forEach((b) => (b.onclick = async () => {
    try { await api(`/api/lots/${encodeURIComponent(S.lot.lot_id)}/decisions`, { json: { part_id: S.sel, decision: b.dataset.d, note: $("note").value } });
      toast(`Saved: ${b.dataset.d}`); await openLot(S.lot.lot_id, true); } catch (e) { toast(e.message, true); }
  }));
  const rv = $("reveal");
  if (rv) rv.onclick = async () => { try { await api(`/api/lots/${encodeURIComponent(S.lot.lot_id)}/actuals/sample`, { method: "POST", body: "{}" }); toast("Real 168h readings loaded"); await openLot(S.lot.lot_id, true); } catch (e) { toast(e.message, true); } };
  const af = $("actfile");
  if (af) af.onchange = async () => { const f = af.files[0]; if (!f) return;
    try { await api(`/api/lots/${encodeURIComponent(S.lot.lot_id)}/actuals`, { method: "POST", headers: { "X-Filename": encodeURIComponent(f.name) }, body: f }); toast("168h readings checked"); await openLot(S.lot.lot_id, true); } catch (e) { toast(e.message, true); } };
}
function pick(id) {
  S.sel = id;
  document.querySelectorAll("tr.row[data-id]").forEach((r) => r.classList.toggle("sel", r.dataset.id === id));
  document.querySelectorAll(".sock").forEach((s) => s.classList.toggle("sel", s.dataset.id === id));
  $("ev").innerHTML = evidenceHTML(); bindLot();
}

/* ------------------------------------------------------------------ audit + model */
let AUDIT = [];
function auditView() {
  return `<section class="card"><h2>Audit log</h2><p class="muted small">Every sign-in, screening, 168h check and QA decision, newest first. Stored in SQLite.</p>
  <div class="tablewrap"><table><thead><tr><th>Time</th><th>Lot</th><th>Action</th><th>Details</th><th>By</th></tr></thead><tbody>
  ${AUDIT.length ? AUDIT.map((a) => `<tr><td class="num small">${esc(a.at)}</td><td>${esc(a.lot_id || "–")}</td><td><b>${esc(a.kind)}</b></td><td class="small">${esc(a.detail)}</td><td class="small">${esc(a.user)}<br><span class="muted">${esc(ROLE[a.role] || a.role)}</span></td></tr>`).join("") : '<tr><td colspan="5" class="empty">Nothing yet.</td></tr>'}
  </tbody></table></div></section>`;
}
function modelView() {
  const m = S.model, t = m.thresholds, s = m.stats;
  return `<div class="grid2"><section class="card"><h2>What each module does</h2>
  <h3>Module A: unusual part?</h3><p class="small">Compares each part's 24h leakage, 24h change and supply current with similar parts in the same lot (robust z-score against the lot median, plus Isolation Forest). Review if z &gt; ${t.A_robust_z}, or z &gt; ${t.A_iso_z} and Isolation Forest agrees.</p>
  <h3>Module B: drift by 168h?</h3><p class="small">Linear quantile regression predicts the 168h value (10%, 50%, 90%) from the 24h value and the 0h→24h change. The range is widened on a separate calibration lot (conformal method) so it holds about 80% of real values. Review if the upper forecast ≥ ${Math.round(t.B_near_limit * 100)}% of the limit or the range is wider than ${t.B_max_range_uA} µA.</p>
  <h3>Module C: part or board?</h3><p class="small">A binomial test checks whether a board has more flags than the other boards (p &lt; ${t.C_p_value}), and a neighbour check confirms the flags sit next to each other (at least ${t.C_min_neighbours}). Then the parts go to <b>Check board</b>: retest before judging, and their forecast is paused.</p>
  <h3>Always</h3><p class="small" style="margin-bottom:0">Hard limit ${m.limit_uA} µA → Fail. Lot outlook supports the PDA check (${m.pda_percent}%). The QA engineer makes the final decision.</p></section>
  <section class="card"><h2>Model check (simulated history)</h2><div class="kv"><span>Version</span><span>${esc(m.version)}</span>
  <span>Training lots</span><span>${esc(s.train_lots.join(", "))}</span><span>Calibration lot</span><span>${esc(s.calibration_lot)}</span>
  <span>Unseen test lot</span><span>${esc(s.test_lot)} (${s.test_parts} parts)</span><span>Forecast error</span><span><b>${s.mae_uA.toFixed(2)} µA</b> (MAE)</span>
  <span>Range coverage</span><span><b>${(s.coverage * 100).toFixed(0)}%</b> (target 80%)</span></div>
  <p class="muted small">Whole lots are held out: a part is never in both training and testing. Board-fault parts confirmed by QA are left out of drift training.</p></section></div>`;
}
const _go = go;
go = async function (v) { if (v === "audit") AUDIT = await api("/api/audit"); if (v === "model" && !S.model) S.model = await api("/api/model"); return _go(v); };

/* ------------------------------------------------------------------ start */
(async function start() {
  S.token = store.get("as_token");
  if (S.token) { try { S.user = await api("/api/me"); await go("lots"); return; } catch { S.token = null; } }
  render();
})();
