Code coverage (pytest-cov)
==========================

Die Übersicht wird im **Monorepo-Wurzelverzeichnis** als Markdown gepflegt und hier eingebunden.

**Aktualisieren** (aus dem Synarius-Wurzelverzeichnis, Geschwister-Repos installiert):

.. code-block:: text

   cd synarius-core && pip install -e ".[timeseries,fmu,dev]"
   cd ../synarius-apps && pip install -e ".[dev]"
   cd ../synarius-studio && pip install ".[dev]"
   cd .. && python scripts/refresh_coverage_overview.py

.. literalinclude:: ../../../COVERAGE.md
   :language: markdown
