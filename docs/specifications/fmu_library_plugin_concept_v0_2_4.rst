..
   FMU / Synarius-Library / Plugin — Architekturkonzept v0.2.4 (restrukturiert).

================================================================================
FMU, Synarius-Library und Plugins: Architekturkonzept (v0.2.4)
================================================================================

:Status: **Superseded** — siehe :doc:`fmu_library_plugin_concept_v0_2_5` (v0.2.5).
:Version: 0.2.4 (eingefroren; nur noch historischer Vergleich)
:Vorgänger: :doc:`fmu_library_plugin_concept_v0_2_3` (v0.2.3)
:Bezug: :doc:`plugin_api` (v0.1) — Ladeschema und Capabilities unverändert gültig

In diesem Dokument kennzeichnen **Tags** die Verbindlichkeit:

* **[NORMATIVE]** — Architekturregel; Abweichung nur bewusst und dokumentiert.
* **[PROVISIONAL]** — beabsichtigte Richtung; Details folgen in v0.3 / Implementierung.
* **[OPEN QUESTION]** — bewusst unentschieden; benannt zur Entscheidung.
* **[FUTURE WORK]** — explizit **Konzept v0.3** oder nachgelagerte Specs.
* **[ARCHITECTURE BLOCKER]** — Klärung erforderlich, bevor abhängige Arbeiten finalisiert werden können.

--------------------------------------------------------------------------------
1. Zweck und Geltungsbereich
--------------------------------------------------------------------------------

**Was dieses Dokument definiert**

* [NORMATIVE] Zielarchitektur für **FMU** im Synarius-Ökosystem: Rollen von
  **Synarius-Library**, **Plugin**, **Synarius Core** (Controller, CCP) und **Handler**.
* [PROVISIONAL] Zusammenspiel, Versionierung, Roadmap-Phasen und **Migration** vom
  Ist-Zustand — ohne v0.3 vorwegzunehmen.

**Was es nicht definiert**

* [FUTURE WORK] **Finale API**: vollständige Signaturen, ``@abstractmethod``-Matrix,
  konkrete Registrierungs-API, Parser-Grammatik — Gegenstand von **Konzept v0.3** und
  :doc:`controller_command_protocol`.

**Verhältnis zu :doc:`plugin_api` (v0.1)**

* [NORMATIVE] v0.1 bleibt maßgeblich für **Plugin-Entdeckung** (``Plugins/``,
  ``pluginDescription.xml``, **Capabilities**).
* Dieses Konzept **ersetzt** v0.1 nicht; es **schränkt** die Semantik für den
  FMU/Lib-Pfad ein (Core generisch, keine FMU-Sonderlogik im Controller).

**Historischer Begriff:** „MinimalController“ (ältere Texte) meint **nicht** eine Klasse,
sondern den generisch zu haltenden Teil — die Implementierung heißt
:class:`~synarius_core.controller.synarius_controller.SynariusController`.

--------------------------------------------------------------------------------
2. Terminologie und Systemschichten
--------------------------------------------------------------------------------

**Synarius Core**

* Laufzeit- und Steuerungskern: u. a. **SynariusController**, **CCP** (Kommandointerpretation),
  generisches Modell-IR. **Keine** fachliche FMU-Semantik im Core-Codepfad [NORMATIVE].

**Synarius-Library (Lib)**

* **Deskriptive** Ebene: Typen, Namensräume, Metadaten, welche Attribute und Operationen
  ein Element **bedeutet**. **Single Source of Truth** für Modellsemantik [NORMATIVE].
  Kurz: **Lib**.

**Plugin**

* **Ausführungs- und Erweiterungs**ebene gemäß :doc:`plugin_api`: lädt Verhalten zur
  Laufzeit (und ggf. Kompilat/Backend), **definiert** aber **keine** Modellsemantik
  [NORMATIVE]. Bindung an Lib über Versionierung und Handler.

**Handler (ElementTypeHandler — Arbeitsname)**

* [PROVISIONAL] Objekt, das für einen ``type_key`` die CCP-Operationen **``new``** /
  **``inspect``** / **``sync``** ausführt. Konkrete Klasse und Signatur: [FUTURE WORK] v0.3.

**CCP (Controller Command Protocol)**

* Textuelle Kommandoschnittstelle; muss **generisch** bleiben und an Handler dispatchen
  [NORMATIVE] (Zielzustand; siehe Abschnitt 6).

**Catalog (Bibliothekskatalog)**

* Mechanismus zum Laden/Auflösen von Library-Descriptors (siehe :doc:`library_catalog`).
  [PROVISIONAL] genaue Schnittstelle zum FMU-Lib-Descriptor.

**Plugin-Rollen (Begriffsklärung, nicht neue Produktkategorien)**

Zur Einordnung in :doc:`plugin_api` — **ohne** die v0.1-Capabilities aufzublähen:

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Rolle
     - Kurzbeschreibung
   * - **Backend / Codegen**
     - Übersetzung, Codeerzeugung, Anbindung an Ziele — typisch ``backend:*``-Capabilities.
   * - **Runtime**
     - Ausführung (z. B. FMU-Schritte) — typisch ``runtime:*``.
   * - **Tool / IDE**
     - UI, Assistenten, Studio-Erweiterungen — oft getrennt vom Simulationskern.
   * - **Library (Deskriptor-Lieferung)**
     - Synarius-Library liefert **Modellsemantik** (Descriptors); kann mit ausgeliefertem
       Paket oder Overlay kommen — **nicht** dasselbe wie ein Runtime-Plugin, aber **gekoppelt**
       über Versionen.

--------------------------------------------------------------------------------
3. Architekturprinzipien [NORMATIVE]
--------------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Prinzip
     - Aussage
   * - **Library als SoT**
     - Modellbedeutung (Typen, Pins, erlaubte Operationen) steht in der **Synarius-Library** /
       ihren Descriptors.
   * - **Plugin als Ausführungsschicht**
     - Laufzeitverhalten (FMU laden, schreiten, …) liegt in **Plugins** / Handlern, **nicht**
       in FMU-spezifischen Pfaden des Core.
   * - **Generischer Core**
     - SynariusController/CCP kennen **generische** Operationen (``new``, ``set``, ``get``,
       ``inspect``, ``sync``) und **dispatchen** — ohne eingebaute FMU-Bind- oder Inspect-Sonderlogik
       im Zielbild.
   * - **Trennung der Verantwortlichkeiten**
     - Semantik (Lib) vs. Ausführung (Plugin/Handler) vs. Orchestrierung (Core) — klar getrennt.
   * - **Plugins erweitern Verhalten, nicht Semantik**
     - Neue **Bedeutung** im Modell kommt aus der Lib (Descriptor/FMFL), nicht aus versteckter
       Plugin-Logik im Core.
   * - **Entkopplung Lib ↔ Plugin, Verträge über Versionen**
     - Lib- und Plugin-Metadaten sind **maschinenlesbar** versioniert; Kompatibilität wird
       **geprüft** — [OPEN QUESTION] *wer* prüft und *wo* (siehe Abschnitt 5).

--------------------------------------------------------------------------------
4. Zusammenspiel Lib ↔ Plugin ↔ Core
--------------------------------------------------------------------------------

**Wie ein Typ definiert ist (Lib)**

* [NORMATIVE] Der ``type_key`` (ggf. namensraumqualifiziert), Pins, Ressourcenrollen und
  Metadaten stammen aus dem **Library-Descriptor** / Katalog — nicht aus Hardcoding im Core.

**Wie ein Typ ausgeführt wird (Plugin / Handler)**

* [PROVISIONAL] Ein **Runtime**-Plugin (z. B. Capability ``runtime:fmu``) stellt die
  Ausführung bereit; der **Handler** implementiert ``new``/``inspect``/``sync`` für den
  jeweiligen ``type_key``.

**Verbindung: Handler-Konzept**

* [PROVISIONAL] Der Core leitet CCP-Operationen an einen **Handler** weiter, der zum
  ``type_key`` passt (Abbildung ``type_key → Handler``). **Details** (Besitz der Registry,
  Lebenszyklus): [OPEN QUESTION] Abschnitt 5.

**Versionierung und Kompatibilität**

* [NORMATIVE] Core-, Lib- und Plugin-Versionen sind in Metadaten erfassbar; wechselseitige
  Abhängigkeiten (Lib braucht Plugin ≥ …) sind **dokumentierbar**.
* [OPEN QUESTION] **Wo** die Paarungsprüfung zur Ladezeit erfolgt und **wer** dafür zuständig
  ist — Abschnitt 5.

**Konzeptmodell Handler (vor API-Fixierung)**

* [PROVISIONAL] Symmetrie CCP ↔ Handler:

  .. code-block:: text

     CCP:     new     inspect     sync
     Handler: new     inspect     sync

* [PROVISIONAL] Abstrakte Basisklasse ``ElementTypeHandler`` (ABC) in ``synarius_core`` —
  Begründung: frühzeitige Fehler bei fehlenden Methoden; [FUTURE WORK] exakte ABC-Regeln v0.3.

**Randfälle Lib-only / Plugin-only**

* [NORMATIVE] **Lib-only:** rein deklarative / FMFL-Typen **ohne** Runtime-Backend sind
  zulässig (kein Plugin nötig).
* [NORMATIVE] **Plugin ohne passende FMU-Lib:** andere Domänen (z. B. Tooling) bleiben
  möglich, sofern Capabilities/Registry das abbilden.

--------------------------------------------------------------------------------
5. Offene Architekturentscheidungen
--------------------------------------------------------------------------------

Dieser Abschnitt **bündelt** Entscheidungen, die in v0.2.x noch im Text verteilt waren.
**Keine** vorzeitige Finalisierung — nur **Benennung** und Einordnung.

**5.1 Besitz und Lebenszyklus [OPEN QUESTION]**

* **Handler-Registrierung:** Wer hält ``dict[type_key → Handler]`` — SynariusController,
  :class:`~synarius_core.plugins.registry.PluginRegistry`, oder eine neue
  ``ElementTypeRegistry``? Eine **autoritative** Stelle [OPEN QUESTION].
* **Lebenszyklus:** Wann werden Handler instanziiert, wann entladen — [FUTURE WORK] v0.3 /
  Implementierung.

**5.2 API-Form (new / inspect / sync) [PROVISIONAL] / [FUTURE WORK]**

* [PROVISIONAL] Methodennamen **``new``**, **``inspect``**, **``sync``** (Symmetrie zu CCP).
* [FUTURE WORK] Welche Methoden ``@abstractmethod`` sind vs. Default-Implementierungen —
  v0.3.
* [FUTURE WORK] Vererbungsmodell bei hierarchischen ``type_keys`` (ein Handler pro Key vs.
  Vererbung) — Dispatch ohne Mehrdeutigkeit.
* [FUTURE WORK] Unbekannter ``type_key``: Fehlerbild Ladezeit vs. Ausführungszeit.

**5.3 Semantik und Struktur von ``resource_path`` [PROVISIONAL] / [OPEN QUESTION]**

* [PROVISIONAL] ``resource_path`` ist ein **generischer Verweis** auf eine datei- oder
  pfadbasierte Ressource (ersetzt typspezifisches ``fmu_path`` in der Zielrichtung).
* [NORMATIVE] **Kein** „alles in einem Slot“: Der Slot ist **generisch**, aber **nicht**
  als Sammelbecken für beliebige unstrukturierte Daten gedacht — weitere Felder bleiben
  über Descriptor und ``type_key`` abbildbar.
* [OPEN QUESTION] **Übergabe an ``handler.new``:** benannter Parameter vs. Eintrag in einem
  generischen Keyword-/Options-Mapping — [FUTURE WORK] v0.3 (beeinflusst Signatur).

**5.4 Namensraum vs. Attributpfad — Architekturblocker [OPEN QUESTION] / [ARCHITECTURE BLOCKER]**

* [NORMATIVE] Zielsyntax skizziert ``new fmulib.FmuInstance …`` — **ein** qualifizierter
  Typbezeichner mit Punkt.
* [ARCHITECTURE BLOCKER] Der CCP-**Sprach**- und **Parser**-Kontext trennt aktuell nicht
  formal: **Typ-Namensraum** (``fmulib.FmuInstance`` als Typ-Token) vs. **Attributpfad**
  (z. B. ``diagram.subtitle``, ``fmu.path``). Das ist eine **Sprachdesign**-Frage, nicht
  nur ein Implementierungsdetail: ohne Klärung sind **Descriptor-Format** für Namensräume
  und **CLI-Oberfläche** nicht unabhängig festlegbar.
* Bearbeitung: :doc:`controller_command_protocol` und Parser; **Voraussetzung für Phase 1**
  (Roadmap, Abschnitt 8).

--------------------------------------------------------------------------------
6. Migration vom Ist-Zustand
--------------------------------------------------------------------------------

Dieser Abschnitt bündelt **Übergang** vom heutigen Verhalten — getrennt von den
Architekturprinzipien (Abschnitte 3–5).

**6.1 CCP: generisch vs. FMU-Sonderlogik (qualitativ)**

.. list-table::
   :header-rows: 1
   :widths: 28 36 36

   * - Mechanismus
     - Ist (Richtung)
     - Soll (Konzept)
   * - ``inspect`` / ``_cmd_inspect``
     - Einstieg generisch; **kann** noch typspezifische Zweige haben.
     - Vollständig **generisch**; Fachlogik in **Handlern**.
   * - ``sync`` / ``_cmd_sync``
     - Analog.
     - Analog; Nutzerbegriff **``sync``** (nicht „reload“/„bind“ als Primärbegriffe).

**6.2 Entfernung ``fmu bind`` / ``fmu reload``**

* [PROVISIONAL] **Zeitpunkt:** **Phase 3** der Roadmap — **nach** Phase 2 (Handler-Dispatch
  für ``new``/``inspect``/``sync``). Ohne Ersatz über generische Kommandos wäre eine
  vorzeitige Entfernung inkonsistent.
* [NORMATIVE] Kein gesondertes Deprecation-Fenster für diese Befehle (Projekte migrieren
  aktiv).

**6.3 Skripte und ``.syn``**

* [PROVISIONAL] **Minimale Zeilen:** Layout-Argumente plus **``resource_path=…``** statt
  FMU-spezifischer Ketten im Controller; Beispiel Ist → Ziel:

  .. code-block:: text

     new FmuInstance … fmu_path=…
     new fmulib.FmuInstance … resource_path=…

* [NORMATIVE] Bestehende ``.syn`` in Projektrepos: **Migration**, keine dauerhafte
  Kompatibilitätsschicht (früherer Teamentscheid).

* [FUTURE WORK] Exakte Grammatik: CCP-/Parser-Spec.

--------------------------------------------------------------------------------
7. Validierung und Teststrategie
--------------------------------------------------------------------------------

**Validierung (Deskriptoren, Manifeste)**

* [PROVISIONAL] Eigenes Modul in **synarius-core** für maschinenlesbare Prüfung von
  Lib-Descriptors und Plugin-Manifesten (Pflichtfelder, Konsistenz, Versionsconstraints).
* [OPEN QUESTION] Schema-Technologie (XSD, JSON Schema, Python-Klassen, …) — Festlegung
  nachgereicht, sobald das Architekturbild ansonsten steht.

**CI**

* [PROVISIONAL] Validierung soll in **CI** anschließbar sein (ohne GUI-Pflicht).

**Referenz-FMUs und Tests**

* Weitere FMUs nur bei **lizenzkonformer** Übernahme.
* Testbestand an ``.syn`` für CLI-Abdeckung; schrittweise Ausbau pro Phase.
* ``@main.simulation_steps`` ist in der Codebasis **implementiert** — für kurze stimulierte
  Simulationsläufe in Tests nutzbar.

--------------------------------------------------------------------------------
8. Implementierungsphasen und Roadmap
--------------------------------------------------------------------------------

[PROVISIONAL] Kein Big-Bang; kleine, reviewbare Schritte; bei Unsicherheit Feature-Flags
oder kurzzeitig parallele Pfade. Pro Phase: kurzes Abstract → Umsetzung → Tests → Changelog.

.. list-table::
   :header-rows: 1
   :widths: 10 58 32

   * - Phase
     - Inhalt
     - Voraussetzungen / Blocker
   * - **1**
     - FMU-**Synarius-Library-Descriptor**: Namensräume, maschinenlesbare Versionen/
       Abhängigkeiten. **Lieferobjekt:** (a) ladbarer Descriptor mit Pflichtfeldern;
       (b) mindestens **eine** Stelle im Controller (oder direkt davor), an der ein zuvor
       **hardcodierter** Wert (z. B. Default-``type_key`` für FMU-Elemente) aus dem Descriptor
       gelesen wird.
     - Kein fertiges ABC / keine vollständige v0.3 für Handler nötig. **[ARCHITECTURE BLOCKER]**
       Klärung **Typ-Namensraum vs. Attributpfad** mit :doc:`controller_command_protocol` /
       Parser (Abschnitt 5.4).
   * - **2**
     - Dispatch ``new``/``inspect``/``sync`` über ``type_key → Handler``; erste Handler;
       ABC-Einfrieren erst nach v0.3.
     - **Blockiert**, bis **Konzept v0.3** die in Abschnitt 5 genannten API-/ABC-Punkte
       lieferbar macht.
   * - **3**
     - Entfernen restlicher FMU-Speziallogik im Core; Entfernung ``fmu bind``/``fmu reload``;
       Migration ``.syn``/Skripte.
     - **Nach** Phase 2 (generische Kommandos dispatchen auf Handler).

**Reihenfolge zur API-Fixierung [FUTURE WORK]**

#. Konzept **v0.3** (Signaturen, ABC-Regeln, Registrierung, Besitz/Validierung).
#. Dann Einfrieren ``ElementTypeHandler``.
#. Dann Implementierungen.

--------------------------------------------------------------------------------
Verhältnis zu :doc:`plugin_api` (v0.1)
--------------------------------------------------------------------------------

* v0.1: Manifest, ``Plugins/``, Capabilities — unverändert Referenz für **Laden** von Plugins.
* **Dieses Dokument (v0.2.4)** ist die **aktuelle** Architektur- und Roadmap-Grundlage für
  FMU/Lib/Core; ältere Versionen (v0.2.3 …) nur historisch.

--------------------------------------------------------------------------------
Änderungen gegenüber v0.2.3 (Kurz)
--------------------------------------------------------------------------------

* Neu gliedert in: Zweck, Schichten, **normative** Prinzipien, Zusammenspiel, **offene
  Entscheidungen**, **Migration**, Validierung/Tests, **Roadmap**.
* Plugin-Rollen (Backend, Runtime, Tool, Library-Lieferung) **begrifflich** geklärt.
* Namensraum/Parser als **[ARCHITECTURE BLOCKER]** hervorgehoben.
* ``resource_path``: generischer Verweis, **kein** Catch-All; Struktur v0.3 [OPEN QUESTION].
* v0.3-Mindestinhalt nicht wiederholt als lange Liste — verdichtet in Abschnitte 5 und 8.

--------------------------------------------------------------------------------
Siehe auch
--------------------------------------------------------------------------------

* :doc:`plugin_api` — Plugin API (minimal v0.1)
* :doc:`fmu_library_plugin_concept_v0_2_3` — Konzept v0.2.3 (Vorgänger)
* :doc:`library_catalog` — Bibliothekskatalog
* :doc:`controller_command_protocol` — CCP
