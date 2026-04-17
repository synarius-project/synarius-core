import sys
from pathlib import Path

# Insert the local src/ directory before any installed synarius_core so that
# all test modules pick up the development version regardless of collection order.
_src = str(Path(__file__).resolve().parents[1] / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
