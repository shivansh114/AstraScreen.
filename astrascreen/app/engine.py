"""AstraScreen screening engine.

Module A - unusual part?      robust z-score vs the lot median + Isolation Forest
Module B - drift by 168h?     linear quantile regression (10/50/90%) + conformal range calibration
Module C - part or board?     binomial test + neighbour check on the burn-in board
Hard limits always apply. The engine only advises; the QA engineer decides.
"""
from __future__ import annotations
import io
import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import QuantileRegressor
from . import config as C

REQUIRED = ["part_id", "board", "socket", "leak_0h_uA", "leak_24h_uA"]
OPTIONAL = ["lot_id", "row", "col", "current_24h_mA"]


class DataError(ValueError):
    """Problem with an uploaded file, explained in plain words."""


# ---------------------------------------------------------------- reading files
def read_table(filename: str, raw: bytes) -> pd.DataFrame:
    name = filename.lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(raw))
        elif name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw))
        else:
            raise DataError("Please upload a .csv or .xlsx file.")
    except DataError:
        raise
    except Exception as exc:
        raise DataError(f"Could not read the file: {exc}") from exc
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _convert_units(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Accept nA columns and convert them to µA."""
    notes = []
    for base in ("leak_0h", "leak_24h", "leak_168h"):
        na, ua = f"{base}_nA", f"{base}_uA"
        if na in df.columns and ua not in df.columns:
            df[ua] = pd.to_numeric(df[na], errors="coerce") / 1000.0
            notes.append(f"{na} converted from nA to µA")
    return df, notes


def validate_readings(df: pd.DataFrame, lot_hint: str) -> tuple[pd.DataFrame, dict]:
    df, notes = _convert_units(df)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise DataError("Missing column(s): " + ", ".join(missing) + ". Open 'File format' on the Lots page for the column names.")
    df = df.copy()
    if "lot_id" not in df.columns:
        df["lot_id"] = lot_hint
    for col in ["board", "socket", "leak_0h_uA", "leak_24h_uA", "current_24h_mA", "row", "col"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if df.part_id.duplicated().any():
        raise DataError(f"Duplicate part_id values: {', '.join(df.part_id[df.part_id.duplicated()].astype(str)[:5])}")
    if "row" not in df.columns or "col" not in df.columns or df[["row", "col"]].isna().any().any():
        df["row"] = ((df.socket - 1) // C.BOARD_COLS).astype("Int64")
        df["col"] = ((df.socket - 1) % C.BOARD_COLS).astype("Int64")
        notes.append(f"board row/column worked out from socket number ({C.BOARD_COLS} sockets per row)")
    bad = df[REQUIRED[1:]].isna().any(axis=1) | (df.leak_0h_uA < 0) | (df.leak_24h_uA < 0)
    df["data_issue"] = bad
    info = dict(rows=int(len(df)), bad_rows=int(bad.sum()), notes=notes,
                lots=sorted(df.lot_id.astype(str).unique().tolist()))
    if len(df) - int(bad.sum()) < 10:
        raise DataError("Fewer than 10 usable parts in the file; AstraScreen needs a full lot to compare parts.")
    return df, info


# ---------------------------------------------------------------- Module B model
class ForecastModel:
    """168h forecast from 0h + 24h readings, with a tested range."""

    def __init__(self):
        self.models, self.widen, self.stats = {}, 0.0, {}

    @staticmethod
    def _x(d):
        return np.c_[d.leak_24h_uA, d.leak_24h_uA - d.leak_0h_uA]

    def train(self, hist: pd.DataFrame):
        # parts later confirmed as board faults do not teach the model about drift
        hist = hist[hist.qa_outcome != "board_fault"] if "qa_outcome" in hist.columns else hist
        lots = sorted(hist.lot_id.unique())
        if len(lots) < 3:
            raise DataError("History needs at least 3 lots (train, calibrate, test).")
        train_l, calib_l, test_l = lots[:-2], lots[-2], lots[-1]
        tr, ca, te = hist[hist.lot_id.isin(train_l)], hist[hist.lot_id == calib_l], hist[hist.lot_id == test_l]
        self.models = {q: QuantileRegressor(quantile=q, alpha=0, solver="highs").fit(self._x(tr), tr.leak_168h_uA)
                       for q in (0.1, 0.5, 0.9)}
        pc = {q: m.predict(self._x(ca)) for q, m in self.models.items()}
        scores = np.sort(np.maximum(pc[0.1] - ca.leak_168h_uA, ca.leak_168h_uA - pc[0.9]))
        k = min(int(np.ceil((len(ca) + 1) * 0.8)) - 1, len(scores) - 1)
        self.widen = float(max(scores[k], 0.0))
        f = self.predict(te)
        self.stats = dict(train_lots=list(map(str, train_l)), calibration_lot=str(calib_l), test_lot=str(test_l),
                          test_parts=int(len(te)),
                          mae_uA=float(np.mean(np.abs(f.f50 - te.leak_168h_uA.values))),
                          coverage=float(np.mean((te.leak_168h_uA.values >= f.f10) & (te.leak_168h_uA.values <= f.f90))),
                          range_widen_uA=self.widen)
        return self.stats

    def predict(self, d: pd.DataFrame) -> pd.DataFrame:
        x = self._x(d)
        q = np.c_[self.models[0.1].predict(x) - self.widen, self.models[0.5].predict(x), self.models[0.9].predict(x) + self.widen]
        q = np.sort(q, axis=1)                     # keep 10% <= 50% <= 90%
        return pd.DataFrame(q, columns=["f10", "f50", "f90"], index=d.index)


# ---------------------------------------------------------------- screening
def screen(df: pd.DataFrame, model: ForecastModel) -> tuple[pd.DataFrame, dict]:
    lot = df.copy()
    ok = ~lot.data_issue
    use = lot[ok]
    med = float(use.leak_24h_uA.median())
    mad = float(1.4826 * np.median(np.abs(use.leak_24h_uA - med))) or 1e-6
    lot["robust_z"] = (lot.leak_24h_uA - med) / mad

    # Module A
    feats = [use.leak_24h_uA, use.leak_24h_uA - use.leak_0h_uA]
    if "current_24h_mA" in use.columns and use.current_24h_mA.notna().all():
        feats.append(use.current_24h_mA)
    X = np.c_[tuple(feats)]
    iqr = np.percentile(X, 75, 0) - np.percentile(X, 25, 0)
    X = (X - np.median(X, 0)) / np.where(iqr == 0, 1, iqr)
    iso = IsolationForest(n_estimators=300, contamination=C.A_CONTAMINATION, random_state=0).fit(X)
    lot["iso_flag"] = False
    lot.loc[use.index, "iso_flag"] = iso.predict(X) == -1
    lot["A"] = ok & ((lot.robust_z > C.A_ROBUST_Z) | (lot.iso_flag & (lot.robust_z > C.A_ISO_Z)))

    # Module B
    lot[["f10", "f50", "f90"]] = np.nan
    lot.loc[use.index, ["f10", "f50", "f90"]] = model.predict(use).values
    lot["B"] = ok & ((lot.f90 >= C.B_NEAR_LIMIT * C.LIMIT_UA) | ((lot.f90 - lot.f10) > C.B_MAX_RANGE_UA))
    lot["hard_fail"] = ok & (lot.leak_24h_uA > C.LIMIT_UA)

    # Module C
    lot["flag"] = lot.A | lot.B
    lot["C"] = False
    boards = []
    for b, d in lot.groupby("board"):
        k, n = int(d.flag.sum()), int(len(d))
        rest = lot[lot.board != b]
        p0 = max(float(rest.flag.mean()) if len(rest) else 0.0, 0.02)
        p = float(binomtest(k, n, p0, alternative="greater").pvalue) if k else 1.0
        cells = set(zip(d[d.flag].row.astype(int), d[d.flag].col.astype(int)))
        near = lambda r, c: any((r + dr, c + dc) in cells for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc)
        touching = [i for i in d[d.flag].index if near(int(lot.row[i]), int(lot.col[i]))]
        fault = bool(p < C.C_P_VALUE and len(touching) >= C.C_MIN_NEIGHBOURS)
        if fault:
            lot.loc[touching, "C"] = True
        boards.append(dict(board=int(b), parts=n, flags=k, p_value=p, touching=len(touching), board_fault=fault,
                           rows=int(d.row.max()) + 1, cols=int(d.col.max()) + 1))

    def status(r):
        if r.data_issue: return "Data check"
        if r.hard_fail: return "Fail"
        if r.C: return "Check board"
        if r.A or r.B: return "Review part"
        return "Routine"
    lot["status"] = lot.apply(status, axis=1)

    def reason(r):
        if r.status == "Data check":
            return "Missing or invalid reading in the file; check the test export."
        if r.status == "Fail":
            return f"{r.leak_24h_uA:.1f} µA at 24h is above the {C.LIMIT_UA:.0f} µA limit (existing hard-limit rule)."
        if r.status == "Check board":
            bd = next(x for x in boards if x["board"] == r.board)
            return (f"One of {bd['flags']} flags bunched together on board {r.board} (p = {bd['p_value']:.2f}); "
                    "likely a socket or hot-zone fault. Retest in another board before judging the part.")
        out = []
        if r.A:
            out.append(f"{r.leak_24h_uA:.1f} µA at 24h is {r.leak_24h_uA / med:.1f}x the lot median ({med:.1f} µA), "
                       f"still below the {C.LIMIT_UA:.0f} µA limit.")
        if r.B:
            out.append(f"168h forecast {r.f50:.1f} µA (range {r.f10:.1f}–{r.f90:.1f} µA) is close to the limit.")
        return " ".join(out) or "In line with similar parts; 168h forecast well below the limit."
    lot["reason"] = lot.apply(reason, axis=1)
    rz = np.clip(lot.robust_z.fillna(0) / 25, 0, 1)
    fr = np.clip(lot.f90.fillna(0) / C.LIMIT_UA, 0, 1)
    lot["risk"] = np.clip(60 * rz + 40 * fr, 1, 99).round().astype(int)
    lot.loc[lot.status == "Fail", "risk"] = 100

    # lot outlook (supports the existing PDA lot check; it does not replace it)
    at_risk = lot[(lot.status.isin(["Review part", "Fail"])) & ((lot.f90 >= C.LIMIT_UA) | lot.hard_fail)]
    pct = 100 * len(at_risk) / max(int(ok.sum()), 1)
    summary = dict(parts=int(len(lot)), median_uA=med, mad_uA=mad,
                   counts={s: int((lot.status == s).sum()) for s in ["Routine", "Review part", "Check board", "Fail", "Data check"]},
                   boards=boards, limit_uA=C.LIMIT_UA, pda_percent=C.PDA_PERCENT,
                   at_risk_168h=int(len(at_risk)), at_risk_percent=pct, pda_warning=bool(pct >= C.PDA_PERCENT))
    return lot, summary


def check_actuals(results: pd.DataFrame, actual: pd.DataFrame) -> dict:
    """Compare forecasts with the real 168h readings (the 'reveal' step)."""
    actual, _ = _convert_units(actual.copy())
    if not {"part_id", "leak_168h_uA"} <= set(actual.columns):
        raise DataError("The 168h file needs columns part_id and leak_168h_uA.")
    m = results.merge(actual[["part_id", "leak_168h_uA"]], on="part_id", how="inner")
    if m.empty:
        raise DataError("None of the part_id values match this lot.")
    fc = m[m.status.isin(["Routine", "Review part"]) & m.f50.notna()]
    over = m[m.leak_168h_uA > C.LIMIT_UA]
    caught = over[over.status.isin(["Review part", "Fail", "Check board"])]
    return dict(parts=int(len(m)),
                mae_uA=float(np.mean(np.abs(fc.f50 - fc.leak_168h_uA))) if len(fc) else None,
                coverage=float(np.mean((fc.leak_168h_uA >= fc.f10) & (fc.leak_168h_uA <= fc.f90))) if len(fc) else None,
                over_limit_168h=int(len(over)), over_limit_flagged_at_24h=int(len(caught)),
                over_limit_parts=over.part_id.tolist(),
                fixed_limit_caught_at_24h=int((over.leak_24h_uA > C.LIMIT_UA).sum()))
