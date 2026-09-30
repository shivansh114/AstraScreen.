"""SQLite storage: lots, results, QA decisions and an audit trail of every action."""
import json, sqlite3, threading
from datetime import datetime, timezone
from . import config as C

_lock = threading.Lock()


def _conn():
    C.DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(C.DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def now():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def init():
    with _lock, _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS lots(lot_id TEXT PRIMARY KEY, filename TEXT, uploaded_by TEXT, role TEXT,
            uploaded_at TEXT, model_version TEXT, file_info TEXT, summary TEXT, results TEXT, validation TEXT);
        CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, lot_id TEXT, part_id TEXT,
            decision TEXT, note TEXT, user TEXT, role TEXT, at TEXT, model_version TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, lot_id TEXT, kind TEXT,
            detail TEXT, user TEXT, role TEXT, at TEXT);
        """)


def save_lot(lot_id, filename, user, file_info, summary, results):
    with _lock, _conn() as con:
        con.execute("DELETE FROM decisions WHERE lot_id=?", (lot_id,))
        con.execute("INSERT OR REPLACE INTO lots VALUES(?,?,?,?,?,?,?,?,?,NULL)",
                    (lot_id, filename, user["name"], user["role"], now(), C.MODEL_VERSION,
                     json.dumps(file_info), json.dumps(summary), json.dumps(results)))


def set_validation(lot_id, validation, results):
    with _lock, _conn() as con:
        con.execute("UPDATE lots SET validation=?, results=? WHERE lot_id=?",
                    (json.dumps(validation), json.dumps(results), lot_id))


def get_lot(lot_id):
    with _conn() as con:
        r = con.execute("SELECT * FROM lots WHERE lot_id=?", (lot_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    for k in ("file_info", "summary", "results", "validation"):
        d[k] = json.loads(d[k]) if d[k] else None
    return d


def list_lots():
    with _conn() as con:
        rows = con.execute("SELECT lot_id, filename, uploaded_by, role, uploaded_at, summary, validation "
                           "FROM lots ORDER BY uploaded_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r); d["summary"] = json.loads(d["summary"]); d["validated"] = bool(d.pop("validation"))
        out.append(d)
    return out


def add_decision(lot_id, part_id, decision, note, user):
    with _lock, _conn() as con:
        con.execute("INSERT INTO decisions(lot_id,part_id,decision,note,user,role,at,model_version) VALUES(?,?,?,?,?,?,?,?)",
                    (lot_id, part_id, decision, note, user["name"], user["role"], now(), C.MODEL_VERSION))


def latest_decisions(lot_id):
    with _conn() as con:
        rows = con.execute("SELECT * FROM decisions WHERE lot_id=? ORDER BY id", (lot_id,)).fetchall()
    out = {}
    for r in rows:
        out[r["part_id"]] = dict(r)
    return out


def log(lot_id, kind, detail, user):
    with _lock, _conn() as con:
        con.execute("INSERT INTO events(lot_id,kind,detail,user,role,at) VALUES(?,?,?,?,?,?)",
                    (lot_id, kind, detail, user["name"], user["role"], now()))


def audit(lot_id=None, limit=300):
    q = ("SELECT at, lot_id, 'Decision' AS kind, part_id || ': ' || decision || CASE WHEN note<>'' THEN ' (' || note || ')' ELSE '' END AS detail, user, role FROM decisions {w1} "
         "UNION ALL SELECT at, lot_id, kind, detail, user, role FROM events {w2} ORDER BY at DESC LIMIT ?")
    with _conn() as con:
        if lot_id:
            rows = con.execute(q.format(w1="WHERE lot_id=?", w2="WHERE lot_id=?"), (lot_id, lot_id, limit)).fetchall()
        else:
            rows = con.execute(q.format(w1="", w2=""), (limit,)).fetchall()
    return [dict(r) for r in rows]
