"""All AstraScreen API logic in one place. Both web servers (FastAPI and the built-in fallback)
call handle(), so they behave exactly the same."""
from __future__ import annotations
import csv, html, io, json, mimetypes, secrets, urllib.parse
import pandas as pd
from . import config as C, db, engine

ROLES = {"technician": "Lab technician", "inspector": "QA inspector", "engineer": "Reliability / QA engineer"}
CAN = {"upload": {"technician", "engineer"}, "actuals": {"technician", "engineer"}, "decide": {"inspector", "engineer"}}
DECISIONS = {"Continue screening", "Investigate", "Reject part", "Retest in another board", "Board fixed, retested"}
SESSIONS: dict[str, dict] = {}
MODEL = engine.ForecastModel()
MODEL_STATS: dict = {}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message); self.status, self.message = status, message


def startup():
    db.init()
    MODEL_STATS.update(MODEL.train(pd.read_csv(C.HISTORY_FILE)))


# ---------------------------------------------------------------- helpers
def _json(data, status=200):
    return status, "application/json; charset=utf-8", json.dumps(data, default=_default).encode(), {}


def _default(o):
    if hasattr(o, "item"): return o.item()
    raise TypeError(type(o))


def _user(headers, query):
    auth = headers.get("authorization", "")
    tok = auth[7:] if auth.lower().startswith("bearer ") else query.get("t", "")
    u = SESSIONS.get(tok)
    if not u:
        raise ApiError(401, "Please sign in again.")
    return u


def _need(user, action):
    if user["role"] not in CAN[action]:
        allowed = " or ".join(ROLES[r] for r in sorted(CAN[action]))
        raise ApiError(403, f"Your role ({ROLES[user['role']]}) cannot do this. Ask a {allowed}.")


def _body_json(body):
    try:
        return json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise ApiError(400, "Invalid request.")


def _lot_payload(lot):
    dec = db.latest_decisions(lot["lot_id"])
    for p in lot["results"]:
        d = dec.get(p["part_id"])
        p["decision"] = d["decision"] if d else None
        p["decision_by"] = f'{d["user"]} ({ROLES.get(d["role"], d["role"])})' if d else None
    lot["decided"] = len(dec)
    return lot


def _run_screening(filename, raw, user):
    df = engine.read_table(filename, raw)
    lot_hint = filename.rsplit("/", 1)[-1].split("_")[0].split(".")[0] or "LOT"
    df, info = engine.validate_readings(df, lot_hint)
    lot_id = str(df.lot_id.iloc[0])
    if len(info["lots"]) > 1:
        raise engine.DataError("The file contains more than one lot_id. Upload one lot at a time.")
    res, summary = engine.screen(df, MODEL)
    cols = ["part_id", "board", "socket", "row", "col", "leak_0h_uA", "leak_24h_uA", "current_24h_mA", "f10", "f50",
            "f90", "robust_z", "A", "B", "C", "hard_fail", "data_issue", "status", "reason", "risk"]
    res = res[[c for c in cols if c in res.columns]]
    records = json.loads(res.round(3).to_json(orient="records"))
    db.save_lot(lot_id, filename, user, info, summary, records)
    c = summary["counts"]
    db.log(lot_id, "Screening", f"{filename}: {summary['parts']} parts; {c['Review part']} review, "
           f"{c['Check board']} check board, {c['Fail']} fail, {c['Data check']} data check", user)
    return lot_id


def _static(path):
    rel = path.lstrip("/") or "index.html"
    f = (C.WEB_DIR / rel).resolve()
    if not str(f).startswith(str(C.WEB_DIR.resolve())) or not f.is_file():
        f = C.WEB_DIR / "index.html"
    ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype.endswith("javascript"):
        ctype += "; charset=utf-8"
    return 200, ctype, f.read_bytes(), {"Cache-Control": "no-store"}


# ---------------------------------------------------------------- router
def handle(method, path, query, headers, body):
    headers = {k.lower(): v for k, v in headers.items()}
    try:
        return _route(method, path, query, headers, body)
    except ApiError as e:
        return _json({"error": e.message}, e.status)
    except engine.DataError as e:
        return _json({"error": str(e)}, 422)
    except Exception as e:  # keep the demo alive and show a readable message
        return _json({"error": f"Unexpected error: {e}"}, 500)


def _route(method, path, query, headers, body):
    parts = [urllib.parse.unquote(p) for p in path.strip("/").split("/") if p]
    if not parts or parts[0] not in ("api", "report"):
        return _static(path)

    if parts[0] == "report" and len(parts) == 2:
        _user(headers, query)
        return 200, "text/html; charset=utf-8", _report_html(parts[1]).encode(), {}

    route = "/".join(parts[1:])
    if method == "POST" and route == "login":
        b = _body_json(body)
        name, role = str(b.get("name", "")).strip()[:40], b.get("role")
        if not name or role not in ROLES:
            raise ApiError(400, "Enter your name and choose a role.")
        tok = secrets.token_urlsafe(18)
        SESSIONS[tok] = {"name": name, "role": role}
        db.log(None, "Sign in", ROLES[role], SESSIONS[tok])
        return _json({"token": tok, "name": name, "role": role, "role_label": ROLES[role]})

    user = _user(headers, query)
    if method == "GET" and route == "me":
        return _json({**user, "role_label": ROLES[user["role"]]})
    if method == "GET" and route == "model":
        return _json({"version": C.MODEL_VERSION, "stats": MODEL_STATS, "limit_uA": C.LIMIT_UA, "pda_percent": C.PDA_PERCENT,
                      "thresholds": {"A_robust_z": C.A_ROBUST_Z, "A_iso_z": C.A_ISO_Z, "B_near_limit": C.B_NEAR_LIMIT,
                                     "B_max_range_uA": C.B_MAX_RANGE_UA, "C_p_value": C.C_P_VALUE,
                                     "C_min_neighbours": C.C_MIN_NEIGHBOURS}})
    if method == "GET" and route == "samples":
        files = sorted(p.name for p in C.SAMPLE_DIR.iterdir() if "readings_24h" in p.name)
        return _json([{"name": f, "has_actuals": (C.SAMPLE_DIR / (f.split("_")[0] + "_actual_168h.csv")).exists()} for f in files])
    if method == "POST" and route == "samples/load":
        _need(user, "upload")
        name = _body_json(body).get("name", "")
        f = C.SAMPLE_DIR / name
        if "/" in name or not f.is_file():
            raise ApiError(404, "Sample file not found.")
        return _json({"lot_id": _run_screening(name, f.read_bytes(), user)})
    if method == "POST" and route == "upload":
        _need(user, "upload")
        name = urllib.parse.unquote(headers.get("x-filename", "upload.csv"))
        if not body:
            raise ApiError(400, "The file is empty.")
        return _json({"lot_id": _run_screening(name, body, user)})
    if method == "GET" and route == "lots":
        return _json(db.list_lots())
    if method == "GET" and route == "audit":
        return _json(db.audit(query.get("lot") or None))

    if len(parts) >= 3 and parts[1] == "lots":
        lot_id, rest = parts[2], "/".join(parts[3:])
        lot = db.get_lot(lot_id)
        if not lot:
            raise ApiError(404, f"Lot {lot_id} not found. Upload it first.")
        if method == "GET" and rest == "":
            return _json(_lot_payload(lot))
        if method == "POST" and rest == "decisions":
            b = _body_json(body)
            pid, dec, note = b.get("part_id"), b.get("decision"), str(b.get("note", ""))[:200]
            if dec not in DECISIONS:
                raise ApiError(400, "Unknown decision.")
            part = next((p for p in lot["results"] if p["part_id"] == pid), None)
            if not part:
                raise ApiError(404, "Part not found in this lot.")
            if not (user["role"] == "technician" and dec in {"Retest in another board", "Board fixed, retested"}):
                _need(user, "decide")
            db.add_decision(lot_id, pid, dec, note, user)
            return _json({"ok": True})
        if method == "POST" and rest in ("actuals", "actuals/sample"):
            _need(user, "actuals")
            if rest == "actuals/sample":
                f = C.SAMPLE_DIR / f"{lot_id}_actual_168h.csv"
                if not f.exists():
                    raise ApiError(404, "No sample 168h file for this lot.")
                fname, raw = f.name, f.read_bytes()
            else:
                fname, raw = urllib.parse.unquote(headers.get("x-filename", "actual.csv")), body
            act = engine.read_table(fname, raw)
            res = pd.DataFrame(lot["results"])
            val = engine.check_actuals(res, act)
            amap = dict(zip(act.part_id, pd.to_numeric(act.get("leak_168h_uA"), errors="coerce")))
            for p in lot["results"]:
                v = amap.get(p["part_id"]); p["actual_168h_uA"] = None if v is None or pd.isna(v) else round(float(v), 3)
            db.set_validation(lot_id, val, lot["results"])
            db.log(lot_id, "168h readings revealed",
                   f"{fname}: forecast error {val['mae_uA']:.2f} µA, {val['over_limit_flagged_at_24h']} of "
                   f"{val['over_limit_168h']} over-limit parts were flagged at 24h", user)
            return _json(val)
        if method == "GET" and rest == "report.csv":
            return _report_csv(lot)
    raise ApiError(404, "Not found.")


# ---------------------------------------------------------------- reports
def _report_csv(lot):
    dec = db.latest_decisions(lot["lot_id"])
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["lot_id", "part_id", "board", "socket", "leak_24h_uA", "forecast_168h_uA", "range_low", "range_high",
                "actual_168h_uA", "status", "risk", "reason", "qa_decision", "decided_by", "decided_at", "model_version"])
    for p in sorted(lot["results"], key=lambda p: -p["risk"]):
        d = dec.get(p["part_id"], {})
        w.writerow([lot["lot_id"], p["part_id"], p["board"], p["socket"], p["leak_24h_uA"], p.get("f50"), p.get("f10"),
                    p.get("f90"), p.get("actual_168h_uA", ""), p["status"], p["risk"], p["reason"], d.get("decision", ""),
                    d.get("user", ""), d.get("at", ""), lot["model_version"]])
    return 200, "text/csv; charset=utf-8", buf.getvalue().encode("utf-8-sig"), {
        "Content-Disposition": f'attachment; filename="AstraScreen_{lot["lot_id"]}_QA_report.csv"'}


def _fc(p):
    if p["status"] == "Check board":
        return "Retest first"
    if p.get("f50") is None:
        return "–"
    return "{:.1f} ({:.0f}–{:.0f})".format(p["f50"], p["f10"], p["f90"])


def _report_html(lot_id):
    lot = db.get_lot(lot_id)
    if not lot:
        raise ApiError(404, "Lot not found.")
    s, dec, e = lot["summary"], db.latest_decisions(lot_id), html.escape
    flagged = sorted([p for p in lot["results"] if p["status"] != "Routine"], key=lambda p: -p["risk"])
    rows = "".join(
        f"<tr><td>{e(p['part_id'])}</td><td>{p['leak_24h_uA']:.1f}</td>"
        f"<td>{_fc(p)}</td>"
        f"<td>{e(p['status'])}</td><td>{e(p['reason'])}</td>"
        f"<td>{e(dec[p['part_id']]['decision'] + ' – ' + dec[p['part_id']]['user']) if p['part_id'] in dec else 'Pending'}</td></tr>"
        for p in flagged)
    bnote = " ".join(f"Board {b['board']}: {b['flags']} flags bunched together (p = {b['p_value']:.2f}); check sockets and retest."
                     for b in s["boards"] if b["board_fault"]) or "No board faults found."
    v = lot["validation"]
    vtxt = (f"<p><b>168h check:</b> forecast error {v['mae_uA']:.2f} µA (average), range held {v['coverage']*100:.0f}% of real values. "
            f"{v['over_limit_flagged_at_24h']} of {v['over_limit_168h']} parts that went over the limit at 168h were flagged at 24h "
            f"(fixed limit alone caught {v['fixed_limit_caught_at_24h']}).</p>") if v else "<p>168h readings not yet available.</p>"
    c = s["counts"]
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AstraScreen QA report {e(lot_id)}</title><style>
body{{font-family:"Segoe UI",Roboto,Arial,sans-serif;color:#1B2433;margin:32px auto;max-width:980px;padding:0 20px;font-size:14px}}
h1{{color:#1F4E79;margin:0}}.muted{{color:#5B6575}}table{{border-collapse:collapse;width:100%;margin-top:12px;font-size:12.5px}}
th,td{{border-bottom:1px solid #DDE3EC;padding:6px 8px;text-align:left;vertical-align:top}}td:first-child,td:nth-child(3){{white-space:nowrap}}th{{background:#EAF2FB}}
.k{{display:inline-block;margin:10px 18px 0 0}}.k b{{font-size:20px;display:block}}button{{margin-top:16px;padding:8px 14px}}
@media print{{button{{display:none}}}}</style></head><body>
<h1>AstraScreen QA report – Lot {e(lot_id)}</h1>
<p class="muted">File {e(lot['filename'])} · uploaded {e(lot['uploaded_at'])} by {e(lot['uploaded_by'])} · model {e(lot['model_version'])} · limit {C.LIMIT_UA:.0f} µA</p>
<div><span class="k"><b>{s['parts']}</b>parts</span><span class="k"><b>{c['Routine']}</b>routine</span><span class="k"><b>{c['Review part']}</b>review part</span>
<span class="k"><b>{c['Check board']}</b>check board</span><span class="k"><b>{c['Fail']}</b>fail</span><span class="k"><b>{c['Data check']}</b>data check</span></div>
<p><b>Board check:</b> {e(bnote)}</p>
<p><b>Lot outlook:</b> {s['at_risk_168h']} parts ({s['at_risk_percent']:.1f}%) forecast to reach the limit by 168h; PDA {s['pda_percent']:.0f}%{' – WARNING' if s['pda_warning'] else ''}.</p>
{vtxt}
<table><thead><tr><th>Part</th><th>24h µA</th><th>168h forecast</th><th>Status</th><th>Reason</th><th>QA decision</th></tr></thead><tbody>{rows}</tbody></table>
<p class="muted">AstraScreen advises; the QA engineer decides. Hard limits always apply.</p>
<button onclick="window.print()">Print / save as PDF</button></body></html>"""
