# synarius-core

![Synarius title image](docs/_static/synarius-title.png)

**synarius-core is the GUI-free Python engine behind Synarius**: projects, simulation services, parameters, measurements, and file-oriented workflows that **Synarius Studio** and **Synarius Apps** build on.

**Python 3.11–3.14** is supported (see `requires-python` in `pyproject.toml`).

**Contributing:** follow the **[Synarius programming guidelines](https://synarius-project.github.io/synarius-guidelines/programming_guidelines.html)** (HTML) and this repository’s **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## What is this?

If Synarius Studio is the **dashboard**, synarius-core is the **motor**. It is meant to be **imported, scripted, tested, and deployed** without pulling in Qt or other desktop UI stacks (unless you add them yourself in your own app).

## When should I use it?

- You want **automation** (CI, batch runs, headless services) around the same models Studio edits.  
- You are building **your own UI** or integration and need a **stable Python API** for simulation-related data and behavior.  
- You need **measurement / time-series I/O** (optional extras) for tools like the DataViewer—implemented here so all frontends share one implementation.

## Quick example

**Install (development, from `synarius-core/`):**

```bash
python -m pip install -U pip
python -m pip install -e .
```

**Smoke-check:**

```bash
python -m synarius_core
```

**Optional measurement file support** (CSV, Parquet, MDF, etc.—see `synarius_core.io` in the docs):

```bash
python -m pip install -e ".[timeseries]"
```

**Load a measurement file in Python** (requires the `[timeseries]` extra; see live docs for exact types):

```python
from synarius_core.io.timeseries import load_timeseries_file

bundle = load_timeseries_file("path/to/measurements.parquet")
```

## Relationship to Studio

- **Studio** owns menus, diagrams, and Qt-specific UX.  
- **synarius-core** owns the **data model and backend-facing operations** Studio calls into.  
- **Rule of thumb:** if it is **simulation logic** or **shared persistence rules**, it belongs here; if it is **pixels and widgets**, it belongs in Studio or Apps.

## Contributing

We care about **clear APIs, tests, and documentation** because every frontend depends on this package.

- **Issues:** https://github.com/synarius-project/synarius-core/issues  
- **Guidelines:** https://synarius-project.github.io/synarius-guidelines/programming_guidelines.html  
- **This repo:** [CONTRIBUTING.md](CONTRIBUTING.md)

## Documentation

- **Live docs:** https://synarius-project.github.io/synarius-core/  
- **Sources:** https://github.com/synarius-project/synarius-core/tree/main/docs  

In a **full Synarius monorepo checkout**, Sphinx may also pull in repo-root `COVERAGE.md` and `synarius-guidelines/docs/programming_guidelines.rst` under **Developer documentation** (see `docs/developer/`).

**Build locally** (from `synarius-core/`):

```bash
python -m pip install -e ".[docs]"
sphinx-build -b html docs docs/_build/html
```

Open `docs/_build/html/index.html` in a browser.

Draft specifications in-repo include **AttributeDict / `AttributeEntry` refactor** — see `docs/specifications/attribute_entry_typing_refactor_concept.rst` and `docs/developer/attribute_dict_contributor_notes.rst`.

## License

- The core system is open source.  
- Extended commercial licensing models for add-on modules or enterprise requirements remain optional for the future.

## Branching strategy

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
5. Direct pushes: allowed on `dev` (for now); avoided on `main` (use PR from `dev` to `main`).

### GitHub branch protection (recommended)

- **`main`:** require pull request before merge; require status checks to pass; approvals not required (for now); no force pushes, no branch deletion.  
- **`dev`:** keep permissive for now (direct pushes allowed); optionally block force pushes and deletion.

## Goals, roadmap, and architecture notes (optional)

SN Core should provide a clean, stable backend that Synarius Studio (and later other frontends) can use: **GUI-less simulation** (data- and step-oriented), **project load/save**, **stimulation and measurement**, **saving results**, **simple math blocks**, and **room to grow via plugins**.

**Roadmap (summary):** multi-FMU simulation with connectors; load/save projects; stimulation/measurement; saving measurement results; simple mathematical operations; data for graphical oscilloscopes; signal generators and measurement files. Later: plugin interfaces, richer modeling formats, Arduino as a plugin, lookup tables, more file formats (DCM, HDF5, optional ASAM/CANape-style paths).

**Architecture:** the GUI is intentionally not implemented in synarius-core. Core provides data, models, and simulation services; Studio orchestrates visualization and user input.
