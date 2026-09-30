"""Settings for AstraScreen. Change values here, not in the code."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
SAMPLE_DIR = ROOT / "sample_data"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "astrascreen.db"
HISTORY_FILE = SAMPLE_DIR / "history_lots.csv"

LIMIT_UA = 50.0          # datasheet maximum leakage (µA); hard limit always applies
PDA_PERCENT = 5.0        # lot percent-defective-allowable used for the lot outlook
BOARD_COLS = 8           # sockets per row on a burn-in board (used if row/col not given)

# Module A (unusual part?)
A_ROBUST_Z = 5.0         # robust z-score that alone triggers review
A_ISO_Z = 3.0            # robust z needed when Isolation Forest also flags the part
A_CONTAMINATION = 0.08

# Module B (168h forecast)
B_NEAR_LIMIT = 0.8       # review if the upper forecast >= 80% of the limit
B_MAX_RANGE_UA = 12.0    # review if the forecast range is wider than this

# Module C (part or board?)
C_P_VALUE = 0.05         # binomial test: more flags on this board than on others?
C_MIN_NEIGHBOURS = 3     # flagged parts that touch another flagged part

MODEL_VERSION = "astrascreen-1.0"
