..
   FMU / Synarius-Library / Plugin — Architekturkonzept v0.2.5 (Qualitätspass).

================================================================================
FMU, Synarius-Library und Plugins: Architekturkonzept (v0.2.5)
================================================================================

:Status: **Superseded** — siehe :doc:`fmu_library_plugin_concept_v0_2_7` (v0.2.7).
:Version: 0.2.5 (eingefroren; nur noch historischer Vergleich)
:Vorgänger: :doc:`fmu_library_plugin_concept_v0_2_4` (v0.2.4)
:Bezug: :doc:`plugin_api` (v0.1) — Ladeschema und Capabilities unverändert gültig

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

* [FUTURE WORK] Finale API: Signaturen, ``@abstractmethod``-Set, Registrierungskontrakt,
  Parser-Grammatik — **v0.3** und :doc:`controller_command_protocol`.

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

[PROVISIONAL] Pro ``type_key`` zuständige Instanz für die Operationen ``new``, ``inspect``,
``sync`` (Arbeitsname ``ElementTypeHandler``). Klassenname und Signaturen: [FUTURE WORK] v0.3.

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
     - Metadaten maschinenlesbar; Kompatibilitätsprüfung — [OPEN QUESTION] Zuständigkeit (Abschnitt 5).

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
* [PROVISIONAL] Für einen ``type_key`` existiert ein **Handler**, der die zum Typ gehörigen
  Schritte ausführt. Ob ein Handler eine Plugin-Instanz kapselt oder anders gebunden wird:
  [FUTURE WORK] Implementierung / v0.3.

**4.2 Mechanismus — Verbindung [PROVISIONAL] / [OPEN QUESTION]**

* [PROVISIONAL] CCP-Operationen ``new``, ``inspect``, ``sync`` werden an den zum ``type_key``
  passenden **Handler** geleitet (Abbildung ``type_key → Handler``).
* [OPEN QUESTION] Besitz der Registrierung, Lebenszyklus der Handler — Abschnitt 5.1.
* [NORMATIVE] Versionen von Synarius Core, Lib und Plugin sind erfassbar; wechselseitige
  Abhängigkeiten dokumentierbar. [OPEN QUESTION] Ladezeit-Prüfung — Abschnitt 5.1.

**4.3 Symmetrie CCP ↔ Handler [PROVISIONAL]**

.. code-block:: text

   CCP:     new     inspect     sync
   Handler: new     inspect     sync

**4.4 Abstrakte Basisklasse [PROVISIONAL] / [FUTURE WORK]**

* [PROVISIONAL] Arbeitsannahme: ABC ``ElementTypeHandler`` in ``synarius_core`` zur frühen
  Erkennung unvollständiger Implementierungen.
* [FUTURE WORK] Welche Methoden verpflichtend sind, Registrierung, genaue Signaturen — **v0.3**.
  **Keine** stillschweigende Verpflichtung aus diesem Konzept.

**4.5 Randfälle [NORMATIVE]**

* **Lib-only:** deklarative / FMFL-Typen ohne Runtime-Backend sind zulässig.
* **Plugin ohne passende FMU-Lib:** andere Domänen bleiben möglich, sofern Capabilities und
  Registry das erlauben.

*Übergang:* Welche Punkte **noch offen** sind (Besitz, API-Form, ``resource_path``-Struktur,
Namensraum) stehen **nicht** in Widerspruch zu Abschnitt 3–4, sondern sind bewusst
**ausstehend** — Abschnitt 5.

--------------------------------------------------------------------------------
5. Offene Architekturentscheidungen
--------------------------------------------------------------------------------

**5.1 Besitz und Lebenszyklus [OPEN QUESTION] / [FUTURE WORK]**

* Handler-Registrierung: SynariusController, :class:`~synarius_core.plugins.registry.PluginRegistry`
  oder ``ElementTypeRegistry`` — **eine** autoritative Stelle [OPEN QUESTION].
* Lebenszyklus der Handler [FUTURE WORK] v0.3 / Implementierung.
* Lib↔Plugin-Validierung zur Ladezeit: **wer** prüft [OPEN QUESTION] (hängt mit Besitz zusammen).

**5.2 API-Form (new / inspect / sync) [PROVISIONAL] / [FUTURE WORK]**

* [PROVISIONAL] Namen ``new``, ``inspect``, ``sync`` parallel zu CCP.
* [FUTURE WORK] ``@abstractmethod``-Set, Vererbung bei hierarchischen ``type_keys``, Fehlerbild
  unbekannter ``type_key`` — v0.3.

**5.3 ``resource_path`` [PROVISIONAL] / [NORMATIVE] / [OPEN QUESTION]**

* [PROVISIONAL] ``resource_path`` bezeichnet einen **generischen Ressourcenverweis** für Typen,
  die eine externe Ressource binden (Zielrichtung: statt ausschließlich ``fmu_path``). Der Verweis
  kann — je nach Typ und Descriptor — auf **Dateipfade**, **URIs** oder **Katalogeinträge**
  (Bibliotheksreferenzen) zeigen. Die Abstraktion ist **bewusst** auf dieser Konzeptstufe; **weitere
  Verfeinerung** ist vorgesehen [FUTURE WORK] v0.3 / Deskriptorformat.
* [NORMATIVE] Der Slot dient **nicht** als Ablage beliebiger unstrukturierter Daten; zusätzliche
  Attribute bleiben über Descriptor und ``type_key`` modellierbar.
* [OPEN QUESTION] Übergabe an ``handler.new``: benannter Parameter vs. generisches Mapping —
  [FUTURE WORK] v0.3.

**5.4 Namensraum vs. Attributpfad [ARCHITECTURE BLOCKER]**

* [NORMATIVE] Zielnotation enthält qualifizierte Typbezeichner (z. B. ``fmulib.FmuInstance``).
* [ARCHITECTURE BLOCKER] **Sprachdesign**, nicht „nur Parser“: CCP nutzt Punkt-Notation bereits für
  **Attributpfade** (z. B. ``diagram.subtitle``, ``fmu.path``). Qualifizierte **Typ-Tokens** müssen
  davon **unterscheidbar** sein. Ohne diese Klärung sind **CCP**, **Modellierungsoberfläche** und
  **Descriptor-Layout** für Namensräume nicht stabil festlegbar. **Voraussetzung** vor weiterer
  API-Stabilisierung (inkl. v0.3-Detailarbeit zu Tokens und Signaturen). Bearbeitung:
  :doc:`controller_command_protocol` und Parser; Bezug Roadmap Abschnitt 8, Phase 1.

*Übergang:* Abschnitt 6 beschreibt den **Übergang** vom Ist-Code zum Zielbild — getrennt von den
Architekturregeln in den Abschnitten 3–5.

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
     - Kein fertiges ABC / keine vollständige v0.3 für Handler nötig. **[ARCHITECTURE BLOCKER]**
       Klärung Typ-Namensraum vs. Attributpfad (:doc:`controller_command_protocol`, Abschnitt 5.4).
   * - **2**
     - Dispatch ``new``/``inspect``/``sync`` über ``type_key → Handler``; ABC nach v0.3.
     - **Blockiert** bis v0.3 die API-/ABC-Punkte aus Abschnitt 5 lieferbar macht.
   * - **3**
     - FMU-Speziallogik im Synarius Core entfernen; ``fmu bind``/``fmu reload`` entfernen;
       ``.syn``/Skripte migrieren.
     - Nach Phase 2.

**Reihenfolge [FUTURE WORK]:** v0.3 (API/ABC/Validierung) → Einfrieren ``ElementTypeHandler`` →
Implementierungen.

--------------------------------------------------------------------------------
Verhältnis zu :doc:`plugin_api` (v0.1)
--------------------------------------------------------------------------------

v0.1 bleibt Referenz für Laden und Capabilities. **Dieses Dokument (v0.2.5)** ist die aktuelle
Architektur- und Roadmap-Grundlage für FMU/Lib/Synarius Core; :doc:`fmu_library_plugin_concept_v0_2_4`
und ältere Versionen nur historisch.

--------------------------------------------------------------------------------
Änderungen gegenüber v0.2.4 (Kurz)
--------------------------------------------------------------------------------

* Redundanzen gestrichen: Kernregeln nur noch in Abschnitt 3; Abschnitt 1/2 ohne Wiederholung der
  Leitlinien.
* Abschnitt 4 in **Konzeptmodell**, **Mechanismus**, **Symmetrie**, **ABC**, **Randfälle** gegliedert;
  API-Verpflichtungen nur als [FUTURE WORK] gekennzeichnet.
* Plugin-Rollen: **beschreibend**, Norm bleiben **Capabilities**.
* ``resource_path``: Verweise auf Datei, URI, Katalogeintrag; Abstraktion bewusst; Verfeinerung v0.3.
* Namensraum-Blocker: **Sprachdesign** und Voraussetzung vor API-Stabilisierung explizit gemacht.
* Übergänge zwischen den Hauptabschnitten ergänzt; Terminologie vereinheitlicht.

--------------------------------------------------------------------------------
Siehe auch
--------------------------------------------------------------------------------

* :doc:`plugin_api` — Plugin API (minimal v0.1)
* :doc:`fmu_library_plugin_concept_v0_2_4` — Konzept v0.2.4 (Vorgänger)
* :doc:`library_catalog` — Bibliothekskatalog
* :doc:`controller_command_protocol` — CCP
