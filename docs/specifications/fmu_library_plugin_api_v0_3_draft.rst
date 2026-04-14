..
   Synarius Plugin — API-Entwurf v0.3-draft (Python-Schnittstellen, englisch).

================================================================================
Synarius Plugin Architecture — API-Konzept (v0.3-draft)
================================================================================

:Status: Architektur-/Implementierungskonzept; **keine** finale API-Spezifikation
:Version: 0.3-draft
:Bezug: :doc:`plugin_api` (v0.1); Architekturüberbau :doc:`fmu_library_plugin_concept_v0_2_9`
:Sprache: Englisch (Interfaces, Code); Erläuterungen deutsch

Dieses Dokument konkretisiert **Python-Interfaces** und **Datenkontexte** für Plugins und
Contributions. Es **ersetzt** :doc:`plugin_api` **nicht** (Manifest, Ordnerlayout). Es
**verfeinert** die Handler-/Registry-Skizze aus dem FMU/Lib-Konzept (v0.2.x) durch ein
**Contribution-Modell** (``SynariusPlugin``).

--------------------------------------------------------------------------------
1. Plugin-Kompositionsmodell
--------------------------------------------------------------------------------

Ein **Plugin** ist die Einheit der **Distribution** und **Entdeckung**:

* ein Ordner + ``pluginDescription.xml`` + eine instanziierbare Python-Klasse;
* wird von der **PluginRegistry** geladen und nach **Capabilities** registriert (:doc:`plugin_api`).

Ein Plugin **kann** mehrere **Contributions** bereitstellen. **Contributions** sind interne
Erweiterungspunkte von Synarius — **nicht** nutzerseitige Plugin-Typen.

**Contribution-Kategorien** (intern, beschreibend):

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Kategorie
     - Rolle
   * - **CompilerPass**
     - Build-Pipeline; Schnittstelle ``CompilerPass`` (``name``, ``stage``, ``run``).
   * - **ElementTypeHandler**
     - Dispatch durch SynariusController; Operationen ``new`` / ``inspect`` / ``sync``.
   * - **SimulationRuntimePlugin**
     - Simulations-Orchestrator; Lifecycle ``runtime_init`` / ``runtime_step`` / ``runtime_shutdown``.

**Hinweis:** Nach außen gibt es weiterhin nur **ein Plugin** und deklarierte **Capabilities**
im XML — keine zusätzlichen „Plugin-Typen“ für Endnutzer.

--------------------------------------------------------------------------------
2. Capabilities vs. Contributions
--------------------------------------------------------------------------------

**Capabilities** (extern, im Manifest)

* signalisieren Fähigkeiten (z. B. ``runtime:fmu``, ``backend:python``);
* die PluginRegistry nutzt sie für Suche/Filterung.

**Contributions** (intern, im Code)

* konkrete Erweiterungspunkte, die der Synarius Core aufruft;
* Beispiele: ``SimulationRuntimePlugin``, ``ElementTypeHandler``, ``CompilerPass``.

**Zusammenhang (illustrativ):**

* Capability ``runtime:fmu`` → Contribution: ``SimulationRuntimePlugin``
* Capability ``backend:python`` → Contribution: ``CompilerPass`` (z. B. ``stage="codegen"``)

Das Plugin deklariert Capabilities im XML; Contributions liefert die Plugin-Klasse über
Methoden der Basis-ABC ``SynariusPlugin`` (siehe Abschnitt 7).

--------------------------------------------------------------------------------
3. Diagnostics (konzeptuell)
--------------------------------------------------------------------------------

* **Aktuell:** ``list[str]`` in Kontexten (implizit).
* **Ziel:** strukturierte Diagnoseobjekte (``severity``, ``message``, optional ``location``) —
  [FUTURE WORK] Formalisierung.
* **Übergang:** Bis zur Formalisierung bleibt ``list[str]`` die Implementierungsbasis; neue
  Kontexte können ``Diagnostic | str`` vorbereiten.

--------------------------------------------------------------------------------
4. Compile-Kontext und Compiler-Passes
--------------------------------------------------------------------------------

.. code-block:: python

   from __future__ import annotations

   from abc import ABC, abstractmethod
   from dataclasses import dataclass, field
   from typing import Any


   @dataclass
   class CompileContext:
       """Gemeinsamer Kontext durch die Build-Pipeline."""

       model: Any
       artifacts: dict[str, Any] = field(default_factory=dict)
       options: dict[str, Any] = field(default_factory=dict)
       diagnostics: list[str] = field(default_factory=list)


   class CompilerPass(ABC):
       """Ein Pass mutiert ``ctx`` in ``run()``; kein festes „return-neues-ctx“-Modell."""

       name: str
       stage: str

       @abstractmethod
       def run(self, ctx: CompileContext) -> None:
           ...

**Mutation:** ``run()`` ändert ``ctx`` direkt; gemischte Semantik (mal Rückgabe, mal Mutation)
ist zu vermeiden.

--------------------------------------------------------------------------------
5. ElementTypeHandler — Modell-Ebene
--------------------------------------------------------------------------------

Kontexte und Ergebnisse (Auszug; vollständige Typen siehe unten):

* ``NewContext`` — ``controller``, ``model``, ``options``, ``diagnostics``
* ``InspectContext`` — read-only Introspection, ohne Artifact-Zugriff
* ``SyncContext`` — wie ``InspectContext``, zusätzlich ``artifacts`` (z. B. kompiliertes Diagramm)
* ``InspectResult`` — ``type_key``, ``ref``, ``attributes``, ``pins`` (konzeptuell Liste von
  Pin-Deskriptoren; derzeit ``list[dict[str, Any]]`` mit Schlüsseln wie ``name`` / ``direction`` /
  ``kind`` / ``metadata``), ``raw``

**Pin-Deskriptor:** [FUTURE WORK] eigenes ``PinDescriptor``-Typisierungsschema; bis dahin
``list[dict[str, Any]]``.

.. code-block:: python

   from abc import ABC, abstractmethod
   from dataclasses import dataclass, field
   from typing import Any


   @dataclass
   class NewContext:
       controller: Any
       model: Any
       options: dict[str, Any] = field(default_factory=dict)
       diagnostics: list[str] = field(default_factory=list)


   @dataclass
   class InspectContext:
       controller: Any
       model: Any
       options: dict[str, Any] = field(default_factory=dict)
       diagnostics: list[str] = field(default_factory=list)


   @dataclass
   class InspectResult:
       type_key: str
       ref: str
       attributes: dict[str, Any] = field(default_factory=dict)
       pins: list[dict[str, Any]] = field(default_factory=list)
       raw: dict[str, Any] = field(default_factory=dict)


   @dataclass
   class SyncContext:
       controller: Any
       model: Any
       artifacts: dict[str, Any] = field(default_factory=dict)
       options: dict[str, Any] = field(default_factory=dict)
       diagnostics: list[str] = field(default_factory=list)


   class ElementTypeHandler(ABC):
       """Contribution für einen ``type_key``; Dispatch über ElementTypeRegistry."""

       type_key: str

       @abstractmethod
       def new(
           self,
           ctx: NewContext,
           ref: str,
           args: list[Any],
           kwargs: dict[str, Any],
       ) -> Any:
           """Erzeugt Element; ``kwargs`` z. B. ``resource_path``."""

       def inspect(self, ctx: InspectContext, ref: str) -> InspectResult:
           raise NotImplementedError(
               f"{type(self).__name__} does not implement inspect"
           )

       def sync(self, ctx: SyncContext, ref: str) -> None:
           """Default: no-op (keine externe Ressource)."""
           pass

**CCP-Symmetrie:** ``new`` / ``inspect`` / ``sync`` auf dem Handler entsprechen den CCP-Befehlen.

**``type_key``:** vollqualifizierter String (z. B. ``fmulib.FmuInstance``); Namespace mit Punkt;
CCP-Navigationspfade verwenden ``/`` (z. B. ``@types/fmulib/FmuInstance``) — siehe Konzept v0.2.9,
Abschnitt 5.1.

--------------------------------------------------------------------------------
6. Simulations-Runtime — Lifecycle
--------------------------------------------------------------------------------

.. code-block:: python

   from abc import ABC, abstractmethod
   from dataclasses import dataclass
   from typing import Any
   from uuid import UUID


   @dataclass
   class SimContext:
       artifacts: dict[str, Any]
       scalar_workspace: dict[Any, float]
       options: dict[str, Any]
       diagnostics: list[str]
       time_s: float = 0.0


   class SimulationRuntimePlugin(ABC):
       """Capability z. B. ``runtime:fmu``; Zuordnung zu Knoten — [FUTURE WORK] Detail."""

       runtime_capability: str

       @abstractmethod
       def runtime_init(self, ctx: SimContext) -> None: ...

       @abstractmethod
       def runtime_step(self, ctx: SimContext, node_id: UUID) -> None: ...

       @abstractmethod
       def runtime_shutdown(self, ctx: SimContext) -> None: ...

       def runtime_reset(self, ctx: SimContext) -> None:
           self.runtime_shutdown(ctx)
           self.runtime_init(ctx)

--------------------------------------------------------------------------------
7. SynariusPlugin — Contribution Provider
--------------------------------------------------------------------------------

.. code-block:: python

   # CompilerPass, ElementTypeHandler, SimulationRuntimePlugin — siehe Abschnitte 4–6

   class SynariusPlugin(ABC):
       """Von der PluginRegistry instanziiert (parameterlos). Contribution-Provider."""

       name: str  # entspricht <Name> in pluginDescription.xml

       def compile_passes(self) -> list[CompilerPass]:
           return []

       def element_type_handlers(self) -> list[ElementTypeHandler]:
           return []

       def simulation_runtime(self) -> SimulationRuntimePlugin | None:
           return None

**Lebenszyklus (konzeptuell):**

#. ``pluginDescription.xml`` lesen
#. Plugin-Klasse instanziieren
#. Core-Subsysteme rufen ``compile_passes()``, ``element_type_handlers()``,
   ``simulation_runtime()`` auf und registrieren die Rückgaben (Handler → ElementTypeRegistry).

Die **PluginRegistry** trägt jeden zurückgegebenen ``ElementTypeHandler`` unter seinem
``type_key`` in die **ElementTypeRegistry** ein — **ohne** dass Endnutzer eine separate
``register_handlers``-Schnittstelle aufrufen (intern kann die Implementierung trotzdem eine
solche Hilfsfunktion nutzen).

--------------------------------------------------------------------------------
8. Migrationshinweis (FmuRuntimePlugin → v0.3-draft)
--------------------------------------------------------------------------------

Das bestehende FMU-Runtime-Plugin kann **konzeptionell** in drei Rollen gesplittet werden:

#. ``SynariusPlugin`` — Contribution-Provider (Plugin-Klasse im Manifest)
#. ``SimulationRuntimePlugin`` — ``runtime_init`` / ``runtime_step`` / ``runtime_shutdown``
#. ``ElementTypeHandler`` — z. B. ``type_key = "fmulib.FmuInstance"``; Logik aus bisherigem
   FMU-``new``-Pfad im Controller wandert hierher

Illustration::

   class FmuRuntimePlugin(SynariusPlugin):
       name = "fmu_runtime"

       def simulation_runtime(self) -> SimulationRuntimePlugin:
           return FmuSimulationRuntime()

       def element_type_handlers(self) -> list[ElementTypeHandler]:
           return [FmuInstanceHandler()]

--------------------------------------------------------------------------------
Siehe auch
--------------------------------------------------------------------------------

* :doc:`plugin_api` — Plugin API (minimal v0.1)
* :doc:`fmu_library_plugin_concept_v0_2_9` — FMU/Lib-Architekturkonzept (v0.2.9)
