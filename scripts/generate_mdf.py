#!/usr/bin/env python3
"""
Erzeugt MDF-Testdateien (1/10/100 MB, 1 GB) in zwei Szenarien.

Ruft ``profile_mdf.py --generate-only`` auf (gemeinsame Implementierung).

Beispiel:
    python generate_mdf.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    script = Path(__file__).resolve().parent / "profile_mdf.py"
    r = subprocess.run(
        [sys.executable, str(script), "--generate-only"],
        check=False,
    )
    raise SystemExit(r.returncode)


if __name__ == "__main__":
    main()
