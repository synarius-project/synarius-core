..
   FMU / Synarius-Library / Plugin — Architekturkonzept v0.2.8.

================================================================================
FMU, Synarius-Library und Plugins: Architekturkonzept (v0.2.8)
================================================================================

:Status: **Superseded** — siehe :doc:`fmu_library_plugin_concept_v0_2_9` (v0.2.9) und
  :doc:`fmu_library_plugin_api_v0_3_draft`.
:Version: 0.2.8 (eingefroren; nur noch historischer Vergleich)
:Vorgänger: :doc:`fmu_library_plugin_concept_v0_2_7` (v0.2.7)
:Bezug: :doc:`plugin_api` (v0.1) — Ladeschema und Capabilities unverändert gültig
:API-Skizze: :doc:`fmu_library_plugin_api_v0_3_draft` — Python-Interfaces (Entwurf, kein Freeze)

**Tags** (Verbindlichkeit):

* **[NORMATIVE]** — Architekturregel; Abweichung nur bewusst und dokumentiert.
* **[PROVISIONAL]** — beabsichtigte Richtung; Details in v0.3 oder bei der Implementierung.
* **[OPEN QUESTION]** — Entscheidung ausstehend; hier nur benannt.
* **[FUTURE WORK]** — Konzept **v0.3** oder nachgelagerte Specs.
* **[ARCHITECTURE BLOCKER]** — Klärung erforderlich, bevor abhängige Arbeiten abgeschlossen werden können.

--------------------------------------------------------------------------------
1. Zweck und Geltungsbereich
--------------------------------------------------------------------------------

**Inhalt**

* [NORMATIVE] Zielarchitektur für **FMU** unter Synarius: Zusammenwirken von
  **Synarius-Library**, **Plugin**, **Synarius Core** und **Handler**.
* [PROVISIONAL] Zusammenspiel, Versionierung, Phasenplan und Migration — ohne v0.3
  vorwegzunehmen.

**Grenzen**

* [PROVISIONAL] **API-Entwurf** (Kontexte, ABCs, ``SynariusPlugin``): :doc:`fmu_library_plugin_api_v0_3_draft`
  — noch **kein** normatives Einfrieren; Abgleich mit Implementierung in **v0.3**.
* [FUTURE WORK] Finale, normierte API + Parser-Grammatik — **v0.3** und :doc:`controller_command_protocol`.

**Bezug :doc:`plugin_api` (v0.1)**

* [NORMATIVE] v0.1 regelt **Entdeckung** und **Capabilities** (``Plugins/``, Manifest).
  Dieses Konzept ersetzt v0.1 nicht. Die **FMU-spezifische** Ausgestaltung (generischer Core,
  keine FMU-Sonderlogik dort) folgt **Abschnitt 3**; keine Wiederholung der Leitlinien hier.

**Begriff „MinimalController“** (ältere Texte): keine Klasse — gemeint ist der generische
Anteil; Implementierung: :class:`~synarius_core.controller.synarius_controller.SynariusController`.

--------------------------------------------------------------------------------
2. Terminologie und Systemschichten
--------------------------------------------------------------------------------

Die **normativen** Rollen sind ausschließlich in **Abschnitt 3** zusammengefasst. Dieser
Abschnitt definiert **Begriffe** und **Einordnung** — ohne sie erneut zu begründen.

**Synarius Core**

Laufzeit- und Steuerungskern (u. a. **SynariusController**, generisches Modell-IR).
**CCP** (Controller Command Protocol): textuelle Kommandoschnittstelle des Controllers.

**Synarius-Library**

Deskriptive Ebene: ``type_key``, Namensräume, Metadaten zu Typen und erlaubten Operationen.
Im Folgenden abgekürzt **Lib**, sobald der Begriff eingeführt ist.

**Plugin**

Erweiterung gemäß :doc:`plugin_api` — Laufzeit- und ggf. Build-/Tool-Verhalten über
**Capabilities**; keine Definition von Modellsemantik durch Plugin-Logik im Core.

**Handler**

[PROVISIONAL] Pro ``type_key`` zuständige Instanz für ``new``, ``inspect``, ``sync``
(``ElementTypeHandler``). Konkrete Signaturen und Kontexte: :doc:`fmu_library_plugin_api_v0_3_draft`
Abschnitt 5; normatives Einfrieren: [FUTURE WORK] v0.3.

**Bibliothekskatalog (Catalog)**

Mechanismus zum Laden von Library-Descriptors (:doc:`library_catalog`). [PROVISIONAL]
Schnittstelle zum FMU-Lib-Descriptor.

**Plugin-Rollen (beschreibend)**

Die folgende Tabelle **ordnet ein** — sie **ersetzt** keine Norm: Ein Plugin wird weiterhin
über **Capabilities** und :doc:`plugin_api` definiert; die Rollen sind **informelle Kategorien**
zur Lesbarkeit dieses Konzepts.

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Kategorie
     - Hinweis
   * - Backend / Codegen
     - Typisch ``backend:*`` — Übersetzung, Codegenerierung.
   * - Runtime
     - Typisch ``runtime:*`` — Ausführung (z. B. FMU).
   * - Tool / IDE
     - UI, Studio — oft außerhalb des Simulationskerns.
   * - Library-Lieferung
     - Deskriptoren der Synarius-Library (Paket/Overlay); gekoppelt an Plugins über Versionen,
       **nicht** identisch mit einem Runtime-Plugin.

--------------------------------------------------------------------------------
3. Architekturprinzipien [NORMATIVE]
--------------------------------------------------------------------------------

Die nachstehende Tabelle ist die **einzige** normative Konsolidierung der Kernregeln; spätere
Abschnitte verweisen darauf, statt die Regeln zu wiederholen.

.. list-table::
   :header-rows: 1
   :widths: 32 68

   * - Prinzip
     - Aussage
   * - **Synarius-Library als Single Source of Truth**
     - Modellsemantik (Typen, Pins, erlaubte Operationen) steht in der Lib / ihren Descriptors.
   * - **Plugin als Ausführungsschicht**
     - Laufzeitverhalten liegt in Plugins und Handlern, nicht in FMU-spezifischen Pfaden des Synarius Core.
   * - **Synarius Core bleibt generisch**
     - SynariusController und CCP führen generische Operationen aus und dispatchen; kein eingebautes FMU-Bind- oder FMUspezial-Inspect im Zielbild.
   * - **Trennung der Verantwortlichkeiten**
     - Semantik (Lib) · Ausführung (Plugin/Handler) · Orchestrierung (Synarius Core).
   * - **Plugins erweitern Verhalten, nicht Semantik**
     - Neue Bedeutung im Modell: Lib (Descriptor/FMFL), nicht verdeckte Plugin-Logik im Core.
   * - **Lib und Plugin entkoppelt, kompatibel über Versionen**
     - Metadaten maschinenlesbar; Kompatibilitätsprüfung — [PROVISIONAL] Anbindung an Ladekette
       und Validierung (Abschnitte 5.1, 7).

*Übergang:* Abschnitt 4 präzisiert, **wie** Lib, Plugin und Synarius Core im Zusammenspiel
funktionieren — weiterhin auf Konzeptebene, ohne API-Finalisierung.

--------------------------------------------------------------------------------
4. Zusammenspiel Synarius-Library ↔ Plugin ↔ Synarius Core
--------------------------------------------------------------------------------

**4.1 Konzeptmodell — was geschieht [NORMATIVE] / [PROVISIONAL]**

* [NORMATIVE] Ein Elementtyp wird **semantisch** durch die Synarius-Library (Descriptor,
  ``type_key``, ggf. Namensraum) beschrieben.
* [NORMATIVE] **Ausführung** (z. B. FMU) liegt außerhalb des Synarius Core in Plugins; der Core
  orchestriert generische Schritte.
* [PROVISIONAL] Für einen ``type_key`` existiert ein **Handler** (``ElementTypeHandler``). Die
  Plugin-Klasse liefert Handler-Instanzen über ``SynariusPlugin.element_type_handlers()`` — siehe
  :doc:`fmu_library_plugin_api_v0_3_draft` Abschnitte 5 und 7.

**4.2 Mechanismus — Verbindung [PROVISIONAL] / [NORMATIVE]**

* [PROVISIONAL] CCP-Operationen ``new``, ``inspect``, ``sync`` werden an den zum ``type_key``
  passenden **Handler** geleitet (Abbildung ``type_key → Handler``).
* [NORMATIVE] Besitz der Registrierung und Dispatch — **Abschnitt 5.1** (``ElementTypeRegistry``).
* [NORMATIVE] Versionen von Synarius Core, Lib und Plugin sind erfassbar; wechselseitige
  Abhängigkeiten dokumentierbar. [PROVISIONAL] Ladezeit-Prüfung Lib↔Plugin — Details
  Validierungsmodul / Implementierung (Abschnitte 5.1, 7).

**4.3 Symmetrie CCP ↔ Handler [PROVISIONAL]**

.. code-block:: text

   CCP:     new     inspect     sync
   Handler: new     inspect     sync

**4.4 Abstrakte Basisklasse und API-Skizze [PROVISIONAL]**

* [PROVISIONAL] ABC ``ElementTypeHandler`` sowie Kontexte ``NewContext`` / ``InspectContext`` /
  ``SyncContext`` — dokumentiert in :doc:`fmu_library_plugin_api_v0_3_draft` (Abschnitte 4–7).
* [PROVISIONAL] ``new`` erhält ``args`` und ``kwargs`` (CCP-Argumente); damit ist die Übergabe von
  ``resource_path`` **als Keyword** ohne Widerspruch zum Konzept Abschnitt 5.3 absichtsfähig —
  endgültige Norm: [FUTURE WORK] v0.3.
* [FUTURE WORK] Vererbung bei hierarchischen ``type_keys``, Fehlerbild unbekannter ``type_key`` —
  **v0.3** nach Pilotimplementierung.

**4.5 Randfälle [NORMATIVE]**

* **Lib-only:** deklarative / FMFL-Typen ohne Runtime-Backend sind zulässig.
* **Plugin ohne passende FMU-Lib:** andere Domänen bleiben möglich, sofern Capabilities und
  Registry das erlauben.

*Übergang:* Offene Punkte zu API-Form und ``resource_path``-Struktur (Abschnitt 5). Besitz/Dispatch:
**5.1**; Typ-Token vs. Attributpfad: **5.4**.

--------------------------------------------------------------------------------
5. Offene Architekturentscheidungen
--------------------------------------------------------------------------------

**5.1 Besitz, Registrierung und Lebenszyklus**

**Besitz — [NORMATIVE]**

Der **SynariusController** hält **PluginRegistry** und **ElementTypeRegistry** als eigenständige
Subsysteme. Die **PluginRegistry** lädt Plugins gemäß :doc:`plugin_api` (v0.1), instanziiert die
deklarierte Plugin-Klasse (Basis-ABC ``SynariusPlugin``, siehe
:doc:`fmu_library_plugin_api_v0_3_draft` Abschnitt 7) **parameterlos** und bezieht **Contributions**:

* ``element_type_handlers()`` — jeder zurückgegebene ``ElementTypeHandler`` wird unter seinem
  ``type_key`` in der **ElementTypeRegistry** eingetragen;
* optional ``compile_passes()`` und ``simulation_runtime()`` für andere Subsysteme.

Die **ElementTypeRegistry** hält die Abbildung ``type_key → Handler`` und ist die **autoritative**
Stelle für den Dispatch von ``new``, ``inspect``, ``sync``. Die frühere Skizze eines Callbacks
``register_handlers(type_registry)`` ist durch dieses **Contribution-Modell** ersetzt; die
Implementierung darf intern weiterhin eine Hilfsmethode ``register_handlers`` verwenden, sofern
sie die gleiche Wirkung wie die Auswertung von ``element_type_handlers()`` hat.

**CCP-Transparenz — [NORMATIVE]**

Beide Subsysteme sind über **Alias-Roots** im CCP-Adressraum navigierbar — analog zum bestehenden
Muster ``@libraries`` → LibraryCatalog. Vorgesehene Alias-Roots: ``@plugins`` → PluginRegistry,
``@types`` → ElementTypeRegistry. Die bestehenden Kommandos ``ls``, ``lsattr``, ``cd``, ``get``
funktionieren auf diesen Teilbäumen **ohne neue Kommandos**. Plugin-Elemente exponieren Attribute
wie ``version``, ``state``, ``capabilities``; Handler-Elemente exponieren ``type_key`` und
Metadaten aus dem Lib-Descriptor.

**Navigationspfade — [NORMATIVE]**

Der Namespace-Separator in ``type_key``-Strings (z. B. ``fmulib.FmuInstance``) wird in der
**ElementTypeRegistry** als **echte Baumhierarchie** abgebildet: ``fmulib`` ist ein Containerknoten,
``FmuInstance`` ein Blattknoten. Der Navigationspfad lautet damit ``@types/fmulib/FmuInstance``.
Ein **flacher** Schlüssel mit Punkt im Segmentnamen (z. B. ``@types/fmulib.FmuInstance``) ist
**unzulässig**, da er mit der Attributpfad-Syntax des CCP kollidiert. Dieselbe Hierarchie gilt
konsistent für Lib-Katalog-Pfade (``@libraries/fmulib/FmuInstance``). Der **Typ-Token** im
``new``-Kommando (``new fmulib.FmuInstance …``) bleibt davon unberührt — er ist ein einzelnes
**leerzeichenbegrenztes** Token und unterliegt **nicht** der Navigationspfad-Syntax.

**state-Attribut — [PROVISIONAL]**

``state`` ist zunächst ein **read-only** virtuelles Attribut auf Plugin-Elementen (mögliche Werte
z. B. ``loaded``, ``failed``). Schreibbarer Zugriff — und damit dynamisches Entladen zur Laufzeit —
ist für v0.3 **nicht** vorgesehen: Handler-Referenzen in der ElementTypeRegistry würden sonst
**dangling**. Explizite Lade-/Entladebefehle können in einer späteren Iteration normiert werden.

**Lebenszyklus — [PROVISIONAL] / [FUTURE WORK]**

Instanziierung der Handler-Objekte beim Laden des Plugins (Rückgabe von
``element_type_handlers()`` und Eintrag in die ElementTypeRegistry); Entladen nur im Rahmen eines
vollständigen ``PluginRegistry.reload()``. Feinere Lebenszyklussteuerung: [FUTURE WORK] v0.3 /
Implementierung.

**5.2 API-Form (new / inspect / sync) [PROVISIONAL] / [FUTURE WORK]**

* [PROVISIONAL] Namen ``new``, ``inspect``, ``sync`` parallel zu CCP; Default-Verhalten für
  ``inspect`` (``NotImplementedError``) und ``sync`` (no-op) siehe
  :doc:`fmu_library_plugin_api_v0_3_draft` Abschnitt 5.
* [FUTURE WORK] ``@abstractmethod``-Matrix nach Pilot, Vererbung bei hierarchischen ``type_keys``,
  Fehlerbild unbekannter ``type_key`` — v0.3.

**5.3 ``resource_path`` [PROVISIONAL] / [NORMATIVE] / [OPEN QUESTION]**

* [PROVISIONAL] ``resource_path`` bezeichnet einen **generischen Ressourcenverweis** für Typen,
  die eine externe Ressource binden (Zielrichtung: statt ausschließlich ``fmu_path``). Der Verweis
  kann — je nach Typ und Descriptor — auf **Dateipfade**, **URIs** oder **Katalogeinträge**
  (Bibliotheksreferenzen) zeigen. Die Abstraktion ist **bewusst** auf dieser Konzeptstufe; **weitere
  Verfeinerung** ist vorgesehen [FUTURE WORK] v0.3 / Deskriptorformat.
* [NORMATIVE] Der Slot dient **nicht** als Ablage beliebiger unstrukturierter Daten; zusätzliche
  Attribute bleiben über Descriptor und ``type_key`` modellierbar.
* [PROVISIONAL] Übergabe an ``handler.new``: der API-Entwurf nutzt ``args`` + ``kwargs`` (Mapping);
  damit ist ``resource_path`` als Keyword abbildbar — endgültige Norm [FUTURE WORK] v0.3.

**5.4 Namensraum vs. Attributpfad**

**Verhalten von ``new`` — [NORMATIVE]**

Zwischen qualifiziertem **Typ-Token** und **Attributpfad** besteht **kein** harter
grammatischer Konflikt in der üblichen CCP-Auswertung: Das Kommandoverb ``new`` schützt sein
erstes Argument — den Typ-Bezeichner — vor der ``<objectRef>.<attr.path>``-Aufteilungslogik, die
``set`` und ``get`` anwenden. ``fmulib.FmuInstance`` ist ein **einzelnes**, leerzeichenbegrenztes
Token; es wird als **ganzer String** gegen die ElementTypeRegistry nachgeschlagen und unterliegt
**keiner** Attributpfad-Zerlegung.

Die **Navigationspfade** in ``@types/…`` (Abschnitt 5.1) bleiben ein **getrenntes** Konzept vom
Typ-Token in ``new …``.

**Spec-Querabhängigkeit — [NORMATIVE]**

Unabhängig davon benötigen :doc:`controller_command_protocol` und :doc:`attribute_path_semantics`
**je einen normativen Klarstellungssatz**: Das ``<type>``-Argument von ``new`` darf
Namensraum-Qualifier mit Punkt enthalten und **unterliegt nicht** der Attributpfad-Regel. Diese
Spec-Ergänzungen sind **nicht** Gegenstand dieses Konzeptdokuments; sie sind **Voraussetzung**
vor der Parser-Implementierung in Phase 1 (Roadmap, Abschnitt 8).

*Übergang:* Abschnitt 6 beschreibt den **Übergang** vom Ist-Code zum Zielbild — getrennt von den
Architekturregeln in den Abschnitten 3–5. (Namensraum vs. Attributpfad: Abschnitt 5.4.)

--------------------------------------------------------------------------------
6. Migration vom Ist-Zustand
--------------------------------------------------------------------------------

**6.1 CCP (qualitativ)**

.. list-table::
   :header-rows: 1
   :widths: 28 36 36

   * - Mechanismus
     - Ist (Richtung)
     - Soll (Konzept)
   * - ``inspect``
     - Einstieg generisch; typspezifische Zweige möglich.
     - Generisch; Fachlogik in Handlern.
   * - ``sync``
     - Analog.
     - Analog; Nutzerbegriff ``sync``.

**6.2 Entfernung ``fmu bind`` / ``fmu reload``**

* [PROVISIONAL] **Phase 3**, nach Phase 2 (Handler-Dispatch). Ohne generisches Ersatz-Backend keine
  vorzeitige Entfernung.
* [NORMATIVE] Kein separates Deprecation-Fenster; Migration durch Projekte.

**6.3 Skripte und ``.syn``**

* [PROVISIONAL] Ziel: ``resource_path=…`` statt FMU-spezifischer Hardcoding-Ketten; Beispiel::

     new FmuInstance … fmu_path=…
     new fmulib.FmuInstance … resource_path=…

* [NORMATIVE] Bestehende ``.syn``: Migration, keine Dauer-Compat-Schicht.
* [FUTURE WORK] Exakte Grammatik: CCP-Spec.

--------------------------------------------------------------------------------
7. Validierung und Teststrategie
--------------------------------------------------------------------------------

* [PROVISIONAL] Modul in **synarius-core** zur maschinenlesbaren Prüfung von Lib-Descriptors und
  Plugin-Manifesten; anschließbar an CI.
* [OPEN QUESTION] Schema-Technologie (XSD, JSON Schema, Python-Klassen, …).
* Referenz-FMUs nur bei Lizenzklarheit; ``.syn``-Testbestand schrittweise; ``@main.simulation_steps``
  für Kurzläufe in Tests (implementiert).

--------------------------------------------------------------------------------
8. Implementierungsphasen und Roadmap
--------------------------------------------------------------------------------

[PROVISIONAL] Kein Big-Bang; kleine Schritte; optional Feature-Flags. Pro Phase: Abstract → Code →
Tests → Changelog.

.. list-table::
   :header-rows: 1
   :widths: 10 58 32

   * - Phase
     - Inhalt
     - Voraussetzungen / Blocker
   * - **1**
     - FMU-Lib-Descriptor (Namensräume, Versionen/Abhängigkeiten). **Lieferobjekt:** (a) ladbarer
       Descriptor; (b) mindestens eine Stelle, an der ein zuvor hardcodierter Wert (z. B.
       Default-``type_key`` für FMU) aus dem Descriptor gelesen wird.
     - Kein fertiges ABC / keine vollständige v0.3 für Handler nötig. **[NORMATIVE]**
       Vor Parser-Arbeit: normative Klarstellungssätze in :doc:`controller_command_protocol` und
       :doc:`attribute_path_semantics` (siehe Abschnitt 5.4 dieses Konzepts).
   * - **2**
     - Dispatch ``new``/``inspect``/``sync`` über ``type_key → Handler``; Anbindung an
       :doc:`fmu_library_plugin_api_v0_3_draft`; ABC/Implementierung abstimmen.
     - **Blockiert** bis API-Entwurf und Implementierung die Punkte aus Abschnitt 5 und dem
       API-Entwurf tragfähig machen (Iteration v0.3).
   * - **3**
     - FMU-Speziallogik im Synarius Core entfernen; ``fmu bind``/``fmu reload`` entfernen;
       ``.syn``/Skripte migrieren.
     - Nach Phase 2.

**Reihenfolge [FUTURE WORK]:** API-Entwurf stabilisieren (:doc:`fmu_library_plugin_api_v0_3_draft`)
→ normative v0.3 → Einfrieren ``ElementTypeHandler`` / ``SynariusPlugin`` → Implementierungen.

--------------------------------------------------------------------------------
Verhältnis zu :doc:`plugin_api` (v0.1)
--------------------------------------------------------------------------------

v0.1 bleibt Referenz für Laden und Capabilities. **Aktuell:** :doc:`fmu_library_plugin_concept_v0_2_9`
(v0.2.9) und :doc:`fmu_library_plugin_api_v0_3_draft`. Diese Version (v0.2.8) nur historisch.

--------------------------------------------------------------------------------
Änderungen gegenüber v0.2.7 (Kurz)
--------------------------------------------------------------------------------

* Neues Dokument :doc:`fmu_library_plugin_api_v0_3_draft` (Contribution-Modell, ``SynariusPlugin``,
  Kontexte, ``SimulationRuntimePlugin``, Migrationsskizze FMU).
* **Abschnitt 5.1:** Registrierung über ``element_type_handlers()`` / ``SynariusPlugin`` statt
  Callback-Skizze ``register_handlers``; konsistent mit API-Entwurf.
* **Abschnitte 4.4, 5.2, 5.3:** Verweis auf API-Entwurf; ``kwargs`` für ``resource_path`` [PROVISIONAL].

--------------------------------------------------------------------------------
Siehe auch
--------------------------------------------------------------------------------

* :doc:`fmu_library_plugin_api_v0_3_draft` — API-Konzept v0.3-draft (Python)
* :doc:`plugin_api` — Plugin API (minimal v0.1)
* :doc:`fmu_library_plugin_concept_v0_2_7` — Konzept v0.2.7 (Vorgänger)
* :doc:`library_catalog` — Bibliothekskatalog
* :doc:`controller_command_protocol` — CCP
* :doc:`attribute_path_semantics` — Attributpfad-Semantik
