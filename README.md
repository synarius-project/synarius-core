# synarius-core (SN Core)

![Synarius title image](docs/_static/synarius-title.png)

GUI-less simulation backend for Synarius.

**Python 3.11–3.14** is supported (see `requires-python` in `pyproject.toml`).

**Contributing:** follow the **[Synarius programming guidelines](https://synarius-project.github.io/synarius-guidelines/programming_guidelines.html)** (HTML) and this repository’s **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## Vision

- Synarius Studio (SN Studio) is the graphical simulation modeling and visualization environment.
- SN Core is a GUI-less simulation backend that provides the simulation functionality.
- Over time, system modeling should become more general (system modeling as a reusable process- and ontology-oriented approach).
  - In SN Studio, this will enable "regional dialects" for graphical simulation that can be adapted to different use cases (e.g. MBSE, audio processing, microcontroller programming, dynamic system simulation, load flow, optimization, ...).

## Goals (scope)

SN Core should provide a clean, stable backend that SN Studio (and later other frontends) can use.

- GUI-less simulation (data- and step-oriented).
- Project load/save and persistence (simulation configuration, FMU wiring, parameters, measurements).
- Stimulation and measurement within the simulation environment.
- Saving measurement results.
- Simple mathematical operations as building blocks.
- Plugin-ability as a foundation for further modularization.

## Roadmap

### 1.0

- Simulation of multiple FMUs that can be connected via connectors.
- Loading and saving such projects.
- Stimulation and measurement in the simulation environment.
- Saving measurement results.
- Implementation of simple mathematical operations.
- Data provision for graphical oscilloscopes (real-time observation) from the backend (consumed by SN Studio UI).
- Stimulation possible via signal generators and measurement files.

### 1.X

- Modularization via a plugin interface (core plugins and, in the future, extended backend functionality).
- Extension of the initial MH syntax towards a flexible modeling format.
- Arduino support as a plugin.
- Support for lookup tables and characteristic curves.
- DCM and HDF5 files (optional extensions: par [CANape], ASAM CDF/CDFX, CSV).

## Architecture (high-level)

- GUI is intentionally not implemented in SN Core.
- SN Core provides data, models and simulation services; SN Studio orchestrates visualization and user input.

## License

- The core system is open source.
- Extended commercial licensing models for add-on modules or enterprise requirements remain optional for the future.

## Develop / Run (minimal)

```bash
python -m synarius_core
```

## Measurement time-series I/O (optional)

Loading measurement files (CSV, Parquet, MDF) for tools such as **Synarius Apps / Dataviewer** is implemented in ``synarius_core.io`` (:class:`~synarius_core.io.timeseries.TimeSeriesBundle`, :func:`~synarius_core.io.timeseries.load_timeseries_file`). Dependencies are **not** installed by default; use the extra:

```bash
pip install -e ".[timeseries]"
```

## Documentation

- Live docs: https://synarius-project.github.io/synarius-core/
- Docs source: https://github.com/synarius-project/synarius-core/tree/main/docs

In a **full Synarius monorepo checkout**, the Sphinx docs also pull in the repo-root ``COVERAGE.md`` and ``synarius-guidelines/docs/programming_guidelines.rst`` under **Developer documentation** (see ``docs/developer/``). Build locally:

```bash
cd synarius-core
pip install -e ".[docs]"
sphinx-build -b html docs docs/_build/html
```

Open ``docs/_build/html/index.html`` in a browser.

## Branching Strategy

This repository uses a simple branching model that fits a solo-developer phase and can be tightened later without changing the overall flow.

### Branch roles

- `main`: stable, release-ready branch
- `dev`: ongoing integration branch for daily development
- `feature/*`: short-lived branches for features
- optional short-lived branch prefixes: `fix/*`, `docs/*`, `refactor/*`

### Practical rules

1. Create new work branches from `dev`.
2. Merge `feature/*` (and optional `fix/*`, `docs/*`, `refactor/*`) into `dev`.
3. Merge `dev` into `main` when `dev` is stable and CI is green.
4. Create release tags (`v*`) from `main` only.
5. Direct pushes:
   - allowed on `dev` (for now)
   - avoided on `main` (use PR from `dev` to `main`)

### GitHub branch protection (recommended)

- `main`:
  - require pull request before merge
  - require status checks to pass
  - approvals not required (for now)
  - no force pushes, no branch deletion
- `dev`:
  - keep permissive for now (direct pushes allowed)
  - optionally block force pushes and deletion

