..
   Konzept: FMU & generischer Controller — Lib als Semantik, Plugin als Ausführung (v0.2).

================================================================================
FMU, Standard-Library und Plugins: Architekturkonzept (v0.2)
================================================================================

:Status: **Superseded** — siehe :doc:`fmu_library_plugin_concept_v0_2_1` (v0.2.1).
:Version: 0.2 (eingefroren; nur noch historischer Vergleich)
:Sprache: Deutsch (technische Begriffe englisch wo etabliert, z. B. ``type_key``, ``sync``)

--------------------------------------------------------------------------------
1. Zweck und Abgrenzung
--------------------------------------------------------------------------------

Dieses Dokument präzisiert die **langfristige Zielarchitektur** für FMU-Funktionalität
und die Rolle von **Bibliothek (Lib)**, **Plugin** und **Synarius-Core** (Controller,
CCP, MinimalController). Es **ersetzt** die :doc:`plugin_api` **nicht**; v0.1
beschreibt weiterhin das minimale Plugin-Layout (Manifest, Capabilities,
Laufzeit-Hooks). **v0.2** ergänzt die **fachliche und organisatorische Einordnung**
für den Umbau weg von FMU-Sonderlogik im Controller hin zu **generischen Operationen**
mit **Lib-Metadaten** und **registrierten Implementierungen**.

**Zielbild (Kurz):** FMU-Verhalten wird ausschließlich über eine **dedizierte Synarius-Lib**
(ggf. in Kombination mit einem **FMU-Plugin**) abgebildet. **MinimalController** und
**CCP** enthalten **keine** FMU-spezifischen Codepfade mehr (kein direktes
``new FmuInstance``, keine fest eingebauten ``fmu_*``-Kommandoketten, keine
``inspect_fmu_path`` / Bind-Logik im Controller). Stattdessen: **generische**
Operationen (``new``, ``set``, ``get``, ``inspect``, ``sync`` am Ziel), deren Verhalten
aus **Library-Descriptors**, **Versionen** und **registrierten Factories/Hooks** folgt.

**Strukturell unverändert:** ``ElementaryInstance``, Pins, Geometrie bleiben allgemein.
**Semantik FMU:** Unterbaum ``fmu.*``, Variablenkatalog, Co-Simulation — nur über
**Lib-Descriptor** und **Laufzeit-Plugin** (Capability ``runtime:fmu``), nicht durch
Controller-Sonderlogik.

--------------------------------------------------------------------------------
2. Grenze Library vs. Plugin (v0.2)
--------------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - **Library (Descriptors)**
     - **Plugin (z. B. ``runtime:fmu``)**
   * - *Was* der Typ im Modell bedeutet: ``type_key``, Pins, Ressourcen-Slots,
       welche Attribute „einbuchen“, welche Operationen (``inspect``, ``sync``)
       **sinnvoll** und **erlaubt** sind.
     - *Wie* die FMU zur Laufzeit ausgeführt wird: laden, schrittweise Ausführung,
       I/O zum Solver, FMI-Fehlerbehandlung — **ohne** FMU-Hardcoding im Controller.
   * - Version **Lib** (und Overlay-Pfade).
     - Version **Plugin**; gemeinsam mit Core-Version definiert Kompatibilitätsregeln.

**Kernaussage:** Die Lib ist die **Single Source of Truth für das Modell** (was Studio,
Skripte und Persistenz sehen). Das Plugin ist die **Ausführungsschicht**; der Core
**dispatcht** generisch und ruft die über Descriptor/Registry gebundene Implementierung
auf.

--------------------------------------------------------------------------------
3. Library als Single Source of Truth
--------------------------------------------------------------------------------

* **Eigene Synarius-Lib** für FMUs (Paket-/Repo-Schnitt **festzulegen** im Rahmen der
  Umsetzung), im Verhältnis zu :doc:`library_catalog` und ggf.
  ``synarius_core.standard_library`` als **Default-Lieferung** („Core shippt eine
  Default-Lib“).
* **Optionale Overlay-Pfade** auf Projektebene: zusätzliche oder überschreibende
  Descriptors ohne Core-Release.
* **Versionierung:** **Core**, **Lib** und **Plugin** werden **jeweils versioniert**;
  Kompatibilität (z. B. welche Lib-Minor zu welchem Plugin) ist **explizit**
  festzuhalten (Changelog, ggf. Constraints im Descriptor).
* **Drop-in-Registrierung:** Nutzer und Drittanbieter-Plugins können **zusätzliche
  Typen** durch **Drop-in-Descriptors** (plus ggf. zugehöriges Plugin-Modul)
  registrieren — ohne Fork von Core.

--------------------------------------------------------------------------------
4. Plugin- und Lib-API (Erzeugung, Inspect, Sync)
--------------------------------------------------------------------------------

Für **neue Blöcke** in einem Synarius-Modell stellt der Entwickler typischerweise ein
**Modul** bereit (eine oder mehrere Klassen) und implementiert die vereinbarten
Einstiegspunkte — insbesondere die konkreten Pfade für:

* **new** — Erzeugung/Initialisierung aus generischen Argumenten (z. B. generisches
  ``resource_path`` / rollenbezogene Zuordnung aus dem Descriptor, keine langen
  expliziten FMU-Parameterlisten im Controller).
* **inspect** — introspection am Ziel (Struktur, Metadaten, was für UI/CCP sichtbar
  ist).
* **sync** — Abgleich Modell ↔ Ressource/Backend (siehe Abschnitt 8).

Die **genaue Signatur und Registrierung** (Registry ``type_key`` / ``MODEL.*`` → Handler)
werden in einer **folgenden API-Spezifikation** normiert; v0.2 fixiert nur die
**Rollen** und die **Pflicht**, Controller und CCP **generisch** zu halten.

--------------------------------------------------------------------------------
5. CCP und generische Befehle
--------------------------------------------------------------------------------

* Bisherige FMU-spezifische Kommandos (z. B. „fmu inspect / bind / reload“) werden
  konzeptionell durch **generische** Befehle ersetzt, z. B. ``inspect <ref>`` /
  ``sync <ref>`` mit **Dispatch** über Descriptor und Registry; wo möglich reines
  ``set`` / ``get``.
* **Terminologie (v0.2):** Nutzer- und Hilfetexte verwenden **``sync``**; die Begriffe
  **``reload``** und **``bind``** werden **nicht** mehr als primäre Nutzerbegriffe
  geführt (siehe auch Doku-Updates in ``controller_command_protocol``, ParaWiz- und
  Studio-Konsole).

--------------------------------------------------------------------------------
6. Skripte und .syn
--------------------------------------------------------------------------------

* **Minimale Zeilen** (z. B. nur Ressourcenpfad) bleiben Ziel; gleiches Modell wie
  heute — ggf. **automatisches** Einbinden aus der Datei beim ``new`` (Separates
  Arbeitspaket, mit Regressionstest).
* **Abwärtskompatibilität:** Für bestehende **``.syn``-Dateien in Projektrepos** ist
  **keine** dauerhafte Kompatibilitätsschicht vorgesehen; Inhalte sind **zu migrieren**
  (einmalige Anpassung / Skripte nach Teamabsprache).

--------------------------------------------------------------------------------
7. Validierung (Build / CI)
--------------------------------------------------------------------------------

In **synarius-core** ist ein **eigenes Modul** vorzusehen, das **Plugin- und/oder
Lib-Descriptors** validiert (Schema, referenzielle Konsistenz, Pflichtfelder). Diese
Validierung soll **perspektivisch in CI-Pipelines** eingebunden werden können
(ohne GUI-Pflicht).

--------------------------------------------------------------------------------
8. Tests und Referenz-FMUs
--------------------------------------------------------------------------------

* **Weitere FMU-Beispiele** sind zu recherchieren; vor **Übernahme ins Synarius-Repo**
  ist die **Lizenz** zu prüfen (nur konforme Artefakte).
* **Tests sukzessive pro Phase:** Aufbau eines **Bestands an .syn-Dateien**, der die
  über das **CLI** erreichbaren Features **abdeckt**.
* **Simulation:** Über ``@main.simulation_steps`` können Simulationszeiten gesetzt und
  **einfache stimulierte Simulationsläufe** ausgeführt werden — solche Szenarien sind
  **Bestandteil** der Teststrategie.
* **Goldene Referenzen** (z. B. BouncingBall) und erweiterte Beispiele sichern nach
  Möglichkeit **gleiches Modell-/Laufzeitverhalten** nach Refactoring-Schritten
  (genaue Vergleichsmetrik pro Phase festlegen).

--------------------------------------------------------------------------------
9. Umsetzungsrahmen
--------------------------------------------------------------------------------

* Umsetzung **nach** Bearbeitung der meisten Review-Befunde; Refactoring **mehrstufig**
  in **kleinen, reviewbaren Schritten** (kein Big-Bang).
* Pro Schritt: **keine Verschlechterung** von Simulations- oder Editor-Funktion; bei
  Unsicherheit **Feature-Flags** oder kurzzeitig **parallele Codepfade**.
* **Lieferung pro Phase:** kurzes Design-Abstract → Implementierung → Tests → Eintrag
  in Spec/Changelog.

--------------------------------------------------------------------------------
10. Verhältnis zu :doc:`plugin_api` (v0.1)
--------------------------------------------------------------------------------

* **plugin_api v0.1** bleibt die Referenz für Manifest, Ordnerlayout ``Plugins/``,
  Capabilities und minimale Runtime-/Compiler-Verträge.
* **v0.2** beschreibt die **Zielarchitektur FMU + Lib + generischer Controller** und
  die **Begriffe** für die nächste Normierung; bei Widerspruch in Detailfragen ist
  bis zur expliziten Aktualisierung der Plugin-Spec **dieses Konzept v0.2** für die
  FMU/Lib-Roadmap maßgeblich, **plugin_api** für das bestehende Ladeschema.

--------------------------------------------------------------------------------
Siehe auch
--------------------------------------------------------------------------------

* :doc:`plugin_api` — Plugin API (minimal v0.1)
* :doc:`library_catalog` — Bibliothekskatalog und ``libraryDescription.xml``
* :doc:`controller_command_protocol` — CCP (Begriffe und Befehle fortlaufend anpassen)
