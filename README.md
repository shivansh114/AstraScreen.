# AstraScreen – working demo (SIH26170, Team Astra)

AI-driven anomaly detection in component burn-in and screening. AstraScreen reads the **0h + 24h**
burn-in readings of a lot and, for every part, answers three questions:

| Module | Question | Method |
|---|---|---|
| A | Is this part unusual today? | robust z-score vs the lot median + Isolation Forest |
| B | Where will it be at 168h? | linear quantile regression (10/50/90%) + conformal range calibration |
| C | Is it the part or the board? | binomial test + neighbour check on the burn-in board |

Hard limits always apply. AstraScreen advises; the QA engineer decides, and every action is logged.

## Start (Windows)
1. Install Python 3.9 or newer from python.org (tick "Add Python to PATH").
2. Double-click **start_windows.bat**. It installs the packages and opens http://localhost:8000.


## Try it
1. Sign in with any name and a role (Reliability / QA engineer can do everything).
2. **Lots** → *Load sample lot L07*. Watch the four screening steps.
3. Dashboard: review queue, board map, evidence charts for each part. Board 3 has a socket fault.
4. Record QA decisions (with notes). Roles decide what you may do.
5. **Reveal real 168h readings** → forecast error and "flagged at 24h" check against the real values.
6. **QA report** (print / save as PDF) and **Download CSV**. See **Audit log** and **Model**.
7. Try **L08** (an Excel file) and upload your own CSV/XLSX.

## File format (one row per part)
Required: `part_id, board, socket, leak_0h_uA, leak_24h_uA`
Optional: `lot_id, row, col, current_24h_mA`. Columns in nA (`leak_24h_nA`) are converted to µA.
For the 168h check: `part_id, leak_168h_uA`.

## Project structure
```
run.py                  start the app
app/config.py           limits and thresholds (change here)
app/engine.py           Modules A, B, C + file checks
app/api.py              all API logic (used by both servers)
app/server_fastapi.py   FastAPI server
app/server_basic.py     built-in fallback server
app/db.py               SQLite: lots, decisions, audit log  (data/astrascreen.db)
web/                    HTML, CSS, JavaScript front end (no external libraries)
sample_data/            simulated lots + history used to train Module B
tools/make_sample_data.py   regenerate the simulated data
tests/smoke_test.py     quick self-check:  python tests/smoke_test.py
```

## Honest notes
- All sample data is **simulated**; the faults are injected on purpose. Results on real ISRO lots
  will differ and must be measured the same way (whole lots held out).
- Sign-in is a demo role switch, not real security. Add proper authentication before real use.
- To start fresh, stop the app and delete `data/astrascreen.db`.
