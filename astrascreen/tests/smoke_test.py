"""Quick self-check without a browser:  python tests/smoke_test.py
Runs the API directly: sign in, screen both sample lots, record a decision, reveal 168h, build reports."""
import json, pathlib, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config as C
C.DB_PATH = pathlib.Path(tempfile.mkdtemp()) / "test.db"          # keep the real database untouched
from app import api

def call(method, path, body=None, token=None, headers=None, query=None):
    h = dict(headers or {}); h.update({"Authorization": f"Bearer {token}"} if token else {})
    raw = body if isinstance(body, bytes) else json.dumps(body or {}).encode()
    status, ctype, data, _ = api.handle(method, path, query or {}, h, raw)
    return status, (json.loads(data) if ctype.startswith("application/json") else data)

api.startup()
_, u = call("POST", "/api/login", {"name": "Test", "role": "engineer"}); t = u["token"]
ok = True
for f, lot in [("L07_readings_24h.csv", "L07"), ("L08_readings_24h.xlsx", "L08")]:
    s, r = call("POST", "/api/samples/load", {"name": f}, t); assert s == 200, r
    s, L = call("GET", f"/api/lots/{lot}", token=t); c = L["summary"]["counts"]
    print(lot, c, "board faults:", [b["board"] for b in L["summary"]["boards"] if b["board_fault"]])
    s, v = call("POST", f"/api/lots/{lot}/actuals/sample", {}, t)
    print("   168h check: error %.2f µA, coverage %.0f%%, over-limit flagged at 24h %d/%d (fixed limit %d)" %
          (v["mae_uA"], v["coverage"] * 100, v["over_limit_flagged_at_24h"], v["over_limit_168h"], v["fixed_limit_caught_at_24h"]))
    ok &= v["over_limit_flagged_at_24h"] == v["over_limit_168h"]
s, _ = call("POST", "/api/lots/L07/decisions", {"part_id": "L07-B1-S31", "decision": "Investigate"}, t); ok &= s == 200
_, tech = call("POST", "/api/login", {"name": "Tech", "role": "technician"})
s, r = call("POST", "/api/lots/L07/decisions", {"part_id": "L07-B1-S31", "decision": "Reject part"}, tech["token"]); ok &= s == 403
s, csv = call("GET", "/api/lots/L07/report.csv", token=t); ok &= s == 200 and b"L07-B1-S31" in csv
s, html = call("GET", "/report/L07", token=t); ok &= s == 200 and b"QA report" in html
s, r = call("POST", "/api/upload", b"id,value\n1,2\n", t, {"X-Filename": "bad.csv"}); ok &= s == 422
s, audit = call("GET", "/api/audit", token=t); ok &= len(audit) >= 5
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"); sys.exit(0 if ok else 1)
