"""Creates simulated burn-in data for the demo (no real ISRO data).

Files written to sample_data/:
  history_lots.csv        past lots L01-L06 with 0h, 24h and 168h readings (used to train Module B)
  L07_readings_24h.csv    lot to screen: has a board fault on board 3 + part faults
  L07_actual_168h.csv     real 168h readings for L07, revealed at the end of the demo
  L08_readings_24h.xlsx   second lot (Excel): scattered part faults + one hard-limit fail
  L08_actual_168h.csv     real 168h readings for L08
Ground truth for testing goes to tests/truth_*.csv (not used by the app).
"""
import numpy as np, pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT, TRUTH = ROOT / "sample_data", ROOT / "tests"
ROWS, COLS, BOARDS = 5, 8, 3
rng = np.random.default_rng(2026)

def make_lot(lot_id, part_faults=(), board_fault=None, hard_fail=None):
    rows = []
    for b in range(1, BOARDS + 1):
        for s in range(1, ROWS * COLS + 1):
            r, c = divmod(s - 1, COLS)
            rows.append(dict(lot_id=lot_id, part_id=f"{lot_id}-B{b}-S{s:02d}", board=b, socket=s, row=r, col=c,
                             l0=rng.normal(10, 0.9), a=max(rng.normal(0.08, 0.02), 0.01), offset=0.0,
                             cur=rng.normal(4.0, 0.12), truth="ok"))
    df = pd.DataFrame(rows).set_index("part_id")
    for pid, kind in part_faults:                       # ("L07-B1-S14", "high") / ("...", "drift") / ("...", "fastdrift")
        if kind == "high":   df.loc[pid, ["l0", "cur"]] = [44.5, 4.55]
        if kind == "drift":  df.loc[pid, ["l0", "a"]] = [12.0, 2.2]
        if kind == "fastdrift": df.loc[pid, ["l0", "a"]] = [12.0, 3.05]
        df.loc[pid, "truth"] = "part_fault"
    if board_fault:
        b, sockets = board_fault
        for s in sockets:
            pid = f"{lot_id}-B{b}-S{s:02d}"
            df.loc[pid, ["offset", "truth"]] = [rng.uniform(14, 19), "board_fault"]
    if hard_fail:
        df.loc[hard_fail, ["l0", "truth"]] = [51.5, "part_fault"]
    n = len(df); noise = lambda: rng.normal(0, 0.15, n)
    df["leak_24h_uA"] = df.l0 + df.a * np.sqrt(24) + df.offset + noise()
    df["leak_168h_uA"] = df.l0 + df.a * np.sqrt(168) + df.offset + noise()
    df["leak_0h_uA"] = df.l0 + noise()
    df["current_24h_mA"] = df.cur
    return df.reset_index()

cols = ["lot_id", "part_id", "board", "socket", "row", "col", "leak_0h_uA", "leak_24h_uA", "current_24h_mA"]
hist = []
for k in range(1, 7):
    L = f"L0{k}"
    faults = [(f"{L}-B{rng.integers(1,4)}-S{rng.integers(1,41):02d}", kind) for kind in ("high", "drift", "fastdrift", "drift")]
    faults = list(dict(faults).items())
    bf = (int(rng.integers(1, 4)), [4, 5, 12, 13, 20]) if k % 2 == 0 else None
    d = make_lot(L, faults, bf)
    d["qa_outcome"] = d.truth
    hist.append(d)
hist = pd.concat(hist)
hist[cols + ["leak_168h_uA", "qa_outcome"]].round(3).to_csv(OUT / "history_lots.csv", index=False)

l7 = make_lot("L07", [("L07-B1-S14", "high"), ("L07-B2-S07", "fastdrift"), ("L07-B1-S31", "fastdrift"), ("L07-B2-S26", "drift")],
              board_fault=(3, [5, 6, 7, 13, 14, 15]))
l7[cols].round(3).to_csv(OUT / "L07_readings_24h.csv", index=False)
l7[["part_id", "leak_168h_uA"]].round(3).to_csv(OUT / "L07_actual_168h.csv", index=False)
l7[["part_id", "truth"]].to_csv(TRUTH / "truth_L07.csv", index=False)

l8 = make_lot("L08", [("L08-B2-S19", "high"), ("L08-B3-S33", "fastdrift")], hard_fail="L08-B1-S03")
l8[cols].round(3).to_excel(OUT / "L08_readings_24h.xlsx", index=False)
l8[["part_id", "leak_168h_uA"]].round(3).to_csv(OUT / "L08_actual_168h.csv", index=False)
l8[["part_id", "truth"]].to_csv(TRUTH / "truth_L08.csv", index=False)
print("sample data written to", OUT)
