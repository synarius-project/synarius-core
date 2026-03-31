# FMU test fixtures

## Layout

| Path | Purpose |
|------|---------|
| `win64/BouncingBall.fmu`, `linux64/…`, `darwin64/…` | FMI 2.0 co-simulation binary for the current CI/host OS (from FMI Cross-Check Test-FMUs). |
| `BouncingBall.fmu` (optional) | Additional copy from another upstream (e.g. tutorial); tests prefer the platform subfolder. |
| `Controller_FMI3.fmu`, `Stimuli.fmu` | FMI 3 examples for inspection/import tests where applicable (not used by the FMI 2 CS runtime plugin). |

Integration tests that load native binaries **must** pick the FMU matching `sys.platform` (see `test_fmu_fmpy_integration.py`).

## Optional extra

FMU stepping requires **FMPy** (`pip install 'synarius-core[fmu]'` or `pip install fmpy`). Without it, the bundled `runtime:fmu` plugin skips instantiation and records a diagnostic.

## Notices

Third-party provenance and licenses: `THIRD_PARTY_NOTICES.md`.
