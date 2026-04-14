"""Dev helper: cProfile for DCM parse, import, and table-summary reads.

Run from repo root:
  python scripts/profile_dcm_backend.py
"""

from __future__ import annotations

import cProfile
import pstats
import sys
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synarius_core.controller import SynariusController  # noqa: E402
from synarius_core.model.data_model import ComplexInstance  # noqa: E402
from synarius_core.parameters.dcm_io import import_dcm_for_dataset, parse_dcm_specs  # noqa: E402

DCM_MAX = ROOT / "tests" / "testdata" / "parameter_formats" / "dcm" / "dcm2_maximal_10000_kennwerte.dcm"


def _print_top(label: str, profiler: cProfile.Profile, n: int = 30) -> None:
    buf = StringIO()
    pstats.Stats(profiler, stream=buf).sort_stats(pstats.SortKey.CUMULATIVE).print_stats(n)
    print("=" * 72)
    print(label)
    print("=" * 72)
    print(buf.getvalue())


def _cal_param_ids(ctl: SynariusController) -> list:
    out = []
    for node in ctl.model.iter_objects():
        if not isinstance(node, ComplexInstance) or node.id is None:
            continue
        try:
            if str(node.get("type")) != "MODEL.CAL_PARAM":
                continue
        except KeyError:
            continue
        out.append(node.id)
    return out


def main() -> None:
    if not DCM_MAX.is_file():
        print("Missing fixture:", DCM_MAX)
        sys.exit(1)

    text = DCM_MAX.read_text(encoding="utf-8")
    pr1 = cProfile.Profile()
    pr1.enable()
    specs = parse_dcm_specs(text)
    pr1.disable()
    print(f"parse_dcm_specs: {len(specs)} specs from {DCM_MAX.name} (~{len(text) // 1024} KiB text)\n")
    _print_top("A) parse_dcm_specs only — top 30 cumulative", pr1)

    ctl = SynariusController()
    ctl.execute("cd @main/parameters/data_sets")
    cli_path = DCM_MAX.as_posix()
    ds_ref = (ctl.execute(f'new DataSet ProfMax source_path="{cli_path}" source_format=dcm') or "").strip()

    pr2 = cProfile.Profile()
    pr2.enable()
    n_imported = import_dcm_for_dataset(ctl, ds_ref, str(DCM_MAX.resolve()))
    pr2.disable()
    print(f"\nimport_dcm_for_dataset: {n_imported} parameters\n")
    _print_top("B) full import (parse + DuckDB + model.attach) — top 30 cumulative", pr2)

    ids = _cal_param_ids(ctl)
    repo = ctl.model.parameter_runtime().repo

    pr3 = cProfile.Profile()
    pr3.enable()
    for pid in ids:
        repo.get_parameter_table_summary(pid)
    pr3.disable()
    print(f"\nget_parameter_table_summary x {len(ids)} (ParaWiz-style list)\n")
    _print_top("C) table summaries only — top 30 cumulative", pr3)


if __name__ == "__main__":
    main()
