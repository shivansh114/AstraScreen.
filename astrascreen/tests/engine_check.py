import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from app import engine, config as C
m = engine.ForecastModel(); print("model", m.train(pd.read_csv(C.HISTORY_FILE)))
for lot, f, act in [("L07", "L07_readings_24h.csv", "L07_actual_168h.csv"), ("L08", "L08_readings_24h.xlsx", "L08_actual_168h.csv")]:
    raw = (C.SAMPLE_DIR / f).read_bytes()
    df, info = engine.validate_readings(engine.read_table(f, raw), lot)
    res, summ = engine.screen(df, m)
    truth = pd.read_csv(C.ROOT / "tests" / f"truth_{lot}.csv")
    j = res.merge(truth, on="part_id")
    print(lot, summ["counts"], "at_risk", summ["at_risk_168h"], "pda", summ["pda_warning"], [ (b['board'],b['flags'],round(b['p_value'],3),b['board_fault']) for b in summ['boards']])
    print("  part faults flagged:", int((j.truth.eq("part_fault") & j.status.isin(["Review part","Fail"])).sum()), "/", int(j.truth.eq("part_fault").sum()),
          "| board faults to board check:", int((j.truth.eq("board_fault") & j.status.eq("Check board")).sum()), "/", int(j.truth.eq("board_fault").sum()),
          "| healthy flagged:", int((j.truth.eq("ok") & ~j.status.eq("Routine")).sum()))
    print("  actuals:", engine.check_actuals(res, pd.read_csv(C.SAMPLE_DIR / act)))
    print(res[res.status != "Routine"][["part_id","leak_24h_uA","f10","f50","f90","status","risk"]].round(1).to_string(index=False))
