..
   Konzept: FMU & generischer Controller — Lib als Semantik, Plugin als Ausführung (v0.2.1).

================================================================================
FMU, Synarius-Library und Plugins: Architekturkonzept (v0.2.1)
================================================================================

:Status: **Superseded** — siehe :doc:`fmu_library_plugin_concept_v0_2_2` (v0.2.2).
:Version: 0.2.1 (eingefroren; nur noch historischer Vergleich)
:Vorgänger: :doc:`fmu_library_plugin_concept_v0_2` (v0.2, ohne Review-Einarbeitung)
:Sprache: Deutsch (technische Begriffe englisch wo etabliert, z. B. ``type_key``, ``sync``)

--------------------------------------------------------------------------------
Terminologie (v0.2.1)
--------------------------------------------------------------------------------

In dieser Spec wird durchgängig **Synarius-Library** (kurz: **Lib**) für die
**deskriptive** Bibliotheksebene (Descriptors, Namensräume, Metadaten) verwendet —
nicht wechselnd mit „Library“ oder „Synarius-Lib“ (ältere Formulierungen in v0.2).

--------------------------------------------------------------------------------
1. Zweck und Abgrenzung
--------------------------------------------------------------------------------

Dieses Dokument präzisiert die **langfristige Zielarchitektur** für FMU-Funktionalität
und die Rolle von **Synarius-Library**, **Plugin** und **Synarius-Core** (insbesondere
:class:`~synarius_core.controller.synarius_controller.SynariusController`, CCP). Es
**ersetzt** die :doc:`plugin_api` **nicht**; v0.1 beschreibt weiterhin das minimale
Plugin-Layout (Manifest, Capabilities, Laufzeit-Hooks).

**Hinweis zum Begriff „MinimalController“:** In v0.2 noch verwendet — dieser Begriff
entspricht **nicht** einer Klasse im Code. Gemeint ist ausschließlich der
**generisch zu haltende Anteil** des Controllers; die konkrete Klasse ist
**SynariusController** (Benennung in Doku und Code: **SynariusController**, nicht
MinimalController).

**Zielbild (Kurz):** FMU-Verhalten wird über eine **dedizierte Synarius-Library** für
FMUs (ggf. mit **FMU-Plugin**) abgebildet. **SynariusController** und **CCP** enthalten
**keine** FMU-spezifischen Codepfade mehr (kein direktes ``new FmuInstance``, keine
fest eingebauten ``fmu_*``-Kommandoketten, keine ``inspect_fmu_path`` / Bind-Logik im
Controller). Stattdessen: **generische** Operationen (``new``, ``set``, ``get``,
``inspect``, ``sync`` am Ziel), deren Verhalten aus **Library-Descriptors**,
**maschinenlesbarer Versionierung** und **registrierten Handlern** folgt.

**Strukturell unverändert:** ``ElementaryInstance``, Pins, Geometrie bleiben allgemein.
**Semantik FMU:** Unterbaum ``fmu.*``, Variablenkatalog, Co-Simulation — über
**Lib-Descriptor** und **Laufzeit-Plugin** (Capability ``runtime:fmu``), nicht durch
Controller-Sonderlogik.

--------------------------------------------------------------------------------
2. Grenze Synarius-Library vs. Plugin (v0.2.1)
--------------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - **Synarius-Library (Descriptors)**
     - **Plugin (z. B. ``runtime:fmu``)**
   * - *Was* der Typ im Modell bedeutet: ``type_key``, Pins, Ressourcen-Slots,
       Namensräume, welche Attribute „einbuchen“, welche Operationen (``inspect``,
       ``sync``) **sinnvoll** und **erlaubt** sind.
     - *Wie* die FMU zur Laufzeit ausgeführt wird: laden, schrittweise Ausführung,
       I/O zum Solver, FMI-Fehlerbehandlung — **ohne** FMU-Hardcoding im Controller.
   * - Version **Lib** (und Overlay-Pfade); **maschinenlesbare** Metadaten und
       **wechselseitige Abhängigkeiten** zu Plugins (siehe Abschnitt 3).
     - Version **Plugin**; Abhängigkeiten zur Lib ebenfalls **maschinenlesbar**;
       **Ladezeit-Prüfung** der Paarung Lib↔Plugin (siehe Abschnitt 3 und 7).

**Kernaussage:** Die Lib ist die **Single Source of Truth für das Modell**. Das Plugin
ist die **Ausführungsschicht**; der Core **dispatcht** generisch.

**Randfall — Lib ohne Plugin / Plugin ohne Lib:**

* **Lib-only (rein deklarativ / FMFL):** Synarius-Libraries, die **ausschließlich**
  FMFL-Code bzw. rein deklarative Typen ohne Laufzeit-Backend bereitstellen, kommen
  **ohne** zugehöriges Plugin aus (neue Blocktypen nur über Descriptor + ggf. FMFL).
* **Plugin ohne Lib:** Perspektivisch sinnvoll für **andere** Synarius-Bereiche
  (z. B. Anforderungsmanagement); Plugins **ohne** passende Lib sind erlaubt, sofern
  das Plugin andere Capabilities nutzt und die Registry das abbildet.

Damit ist „Drop-in-Descriptor **plus ggf.** Plugin-Modul“ **explizit**: Plugin ist
**nicht** immer Pflicht, wenn die Semantik ohne Laufzeit-Implementierung auskommt.

--------------------------------------------------------------------------------
3. Synarius-Library als Single Source of Truth
--------------------------------------------------------------------------------

* **Eigene Synarius-Library** für FMUs (Paket-/Repo-Schnitt im Implementierungsplan
  festzulegen), im Verhältnis zu :doc:`library_catalog` und ggf.
  ``synarius_core.standard_library`` als **Default-Lieferung**.
* **Namensräume:** Libs **führen Namensräume** (Präfixe), damit Typen eindeutig und
  CLI-freundlich adressierbar sind — Beispiel für die **Zielrichtung** nach Umbau::

      new fmulib.FmuInstance …

  (exakte Tokenisierung und Grammatik: CCP-/Parser-Spec; hier nur **Skizze** der
  Einbettung ``<lib-namespace>.<Typ>``).
* **Optionale Overlay-Pfade** auf Projektebene.
* **Versionierung (maschinenlesbar):** Versionen von **Core**, **Lib** und **Plugin**
  sind in den jeweiligen Metadaten **maschinenlesbar** abzulegen. **Wechselseitige
  Abhängigkeiten** (Lib benötigt Plugin ≥ x.y; Plugin benötigt Lib ≥ a.b) sind in den
  **entsprechenden Descriptors/Manifesten** zu dokumentieren.
* **Ladezeit-Prüfung:** Beim Laden ist zu **prüfen**, ob **Plugin und Lib zusammenpassen**
  (Versions- und Abhängigkeitsconstraints). **Wer** die Prüfung technisch ausführt
  (z. B. :class:`~synarius_core.plugins.registry.PluginRegistry`, Library-Catalog-Loader,
  oder das **Validierungsmodul** aus Abschnitt 7) wird in der Implementierung an einer
  Stelle gebündelt — **Wirkung** hat die Prüfung nur, wenn Constraints **nicht nur**
  prose in Changelogs stehen, sondern **strukturiert** ausgewertet werden.
* **Drop-in-Registrierung** zusätzlicher Typen ohne Core-Fork bleibt Ziel.

--------------------------------------------------------------------------------
4. Plugin- und Lib-API: Handler, Dispatch, Registrierung (vorläufiger Rahmen)
--------------------------------------------------------------------------------

Dieser Abschnitt **schließt** die Lücke aus v0.2 (dort: vollständig „folgende Spec“).
**Vollständig eingefrorene** Methodensignaturen (alle Parameter- und Rückgabetypen) sind
Gegenstand von **Konzept v0.3** — **Reihenfolge zwingend:**

#. **Spec v0.3** mit vollständig ausformuliertem Abschnitt 4 (Signaturen, Fehlerbilder).
#. **Dann** Einfrieren der abstrakten Basisklasse ``ElementTypeHandler`` (ABC).
#. **Dann** Plugin-/Core-Implementierungen.

**Warum ABC (Abstract Base Class) statt nur Protocol:** Die harte Import-Abhängigkeit
von Plugins zu ``synarius_core`` ist für FMU-Laufzeit **strukturell unvermeidlich**
(bestehende Muster). **ABC** liefert **Sicherheit zur Instanziierungszeit**: fehlende
Methoden → ``TypeError`` beim Laden, nicht erst beim ersten Aufruf im Betrieb —
verglichen mit rein protokollbasiertem Typing, das veraltete Implementierungen **still**
tolerieren kann, wenn Signaturen zufällig noch passen.

**Vorläufiges Modell (Implementierungsrichtung):**

* **SynariusController** (bzw. eine dedizierte, vom Controller genutzte Registry — **finale
  Zuteilung in v0.3**) hält eine Abbildung ``dict[str, ElementTypeHandler]`` (oder
  gleichwertig), keyed by **``type_key``** (String; ggf. hierarchische / qualifizierte
  Keys wie ``fmulib.FmuInstance`` — **Normierung in v0.3**).
* ``ElementTypeHandler`` ist eine **abstrakte Basisklasse** in ``synarius_core``.
  **Plugins** (und ggf. Core-interne Registrierungen) **subklassieren** sie und melden
  sich für **einen oder mehrere** ``type_key``-Strings an.
* **Dispatch:** ``registry[type_key] → Handler-Instanz``; Aufruf der Methoden für
  **new** / **inspect** / **sync** erfolgt **vom Controller** (CCP-Pfad), **nicht** von
  der Lib als Laufzeit-Orchestrator — die Lib **liefert Metadaten**, der Handler **führt**
  aus.
* **Argumente für „new“:** Mit Wegfall von fest verdrahteten FMU-Parametern im Controller
  werden Argumente **generisch** übergeben (z. B. ``resource_path`` statt ausschließlich
  ``fmu_path``); **konkrete** Zuordnung Namen → Semantik kommt aus **Descriptor** /
  Lib-Metadaten (Mapping-Tabelle in v0.3).
* **Verschachtelte / spezialisierte type_keys** (z. B. FMU-Instanz als Spezialisierung
  einer generischen Elementary-Variante): entweder **ein** Handler pro konkretem Key
  oder **Vererbung** der Handler-Klasse — **festzulegen in v0.3**, damit keine
  Mehrdeutigkeit bei Dispatch bleibt.
* **Unbekannter ``type_key``:** Verhalten **Ladezeit** (Descriptor/Plugin registriert
  nichts Passendes) vs. **Ausführungszeit** (Tippfehler im Skript) — **getrennt**
  spezifizieren in v0.3 (Fehlercodes, Meldungen).

**Pflicht vs. optional:** ``inspect`` und ``sync`` werden **generische** CCP-Kommandos;
die **Implementierung** auf Handler-Seite kann **optional** sein (fehlende Capability →
klarer Fehler oder No-Op nach Policy — **festzulegen in v0.3**). Allgemein muss die
Plugin-/Handler-API definieren, welche Methoden **verpflichtend** und welche **optional**
sind.

**Mindestinhalt von Konzept v0.3 (Anforderung):**

* Vollständige Signaturen von ``ElementTypeHandler`` (Methoden z. B. ``create``,
  ``inspect``, ``sync`` — endgültige Namenswahl in v0.3) inkl. aller Parameter- und
  Rückgabetypen.
* Exakte Signatur der **Registrierung** (wie meldet ein Plugin Handler für ``type_key``?).
* **Besitz** der Handler-Tabelle: SynariusController vs. PluginRegistry vs. neue
  ``ElementTypeRegistry`` — **eine** authoritative Stelle.
* Unbekannter ``type_key``: Ladezeit vs. Ausführungszeit (siehe oben).

--------------------------------------------------------------------------------
5. CCP (generisch), Ist/Soll, Entfernung ``fmu bind`` / ``fmu reload``
--------------------------------------------------------------------------------

**Ziel:** ``inspect`` und ``sync`` sind **generische** Kommandos; die **konkrete**
Implementierung liegt in **Handlern** bzw. Libs und ist wo **optional** (siehe Abschnitt 4).

**In dieser Iteration** werden die CCP-Befehle **``fmu bind``** und **``fmu reload``**
**entfernt** — **ohne** gesondertes Deprecation-Fenster (Projekte migrieren Skripte und
``.syn``; siehe Abschnitt 6). Nutzerterminologie bleibt **``sync``** (nicht „reload“/„bind“
als Primärbegriffe).

**Ist/Soll (qualitativ — Stand der Doku, nicht Ersatz für Code-Audit):**

.. list-table::
   :header-rows: 1
   :widths: 28 36 36

   * - Kommando / Mechanismus
     - Ist (Richtung)
     - Soll (v0.2.1)
   * - ``inspect <ref>`` (``_cmd_inspect``)
     - Einstieg generisch; **kann** noch typspezifische Zweige enthalten.
     - Vollständig **generisch**; FMU-Logik nur in **Handlern**, nicht im Controller.
   * - ``sync <ref>`` (``_cmd_sync``)
     - Analog.
     - Analog; **einheitliche** Nutzerterminologie **sync**.

Die genaue Code-Entflechtung ist **Implementierungsarbeit**; diese Tabelle dient der
**Roadmap** und sollte bei Meilensteinen gegen den Code verifiziert werden.

--------------------------------------------------------------------------------
6. Skripte und .syn: Zielformat und Migration
--------------------------------------------------------------------------------

**„Minimale Zeilen“** meint: nach Umbau sollen **wenige, stabile** Angaben pro Element
reichen — typischerweise **Positions-/Layout-Argumente** plus **Ressourcenreferenz**
über **generisches** ``resource_path=…`` (statt fester FMU-spezifischer Keyword-Ketten
im Controller).

**Illustration (keine finale Grammatik):**

* **Heute (Beispiel):**

  .. code-block:: text

      new FmuInstance bb 187.5 52.5 1 fmu_path=third_party/bouncing_ball/BouncingBall.fmu

* **Zielrichtung (mit Lib-Namensraum, siehe Abschnitt 3):**

  .. code-block:: text

      new fmulib.FmuInstance bb 187.5 52.5 1 resource_path=third_party/bouncing_ball/BouncingBall.fmu

Exakte Tokenreihenfolge, Pflicht-/Optional-Parameter und Aliasnamen werden mit CCP-
Parser und :doc:`controller_command_protocol` abgestimmt — **dieses Konzept** liefert
nur die **fachliche** Zielrichtung (Einfluss auf Abschnitt 5, 7 und Migrationsaufwand).

**Abwärtskompatibilität:** Bestehende ``.syn`` in Projektrepos werden **migriert**; keine
dauerhafte Kompatibilitätsschicht (Teamentscheid v0.2, unverändert).

--------------------------------------------------------------------------------
7. Validierung (Build / CI) und Schema-Format
--------------------------------------------------------------------------------

In **synarius-core** ist ein **Modul** für **maschinenlesbare** Validierung von
**Plugin-Manifesten** und **Lib-Descriptors** vorgesehen (Pflichtfelder, referenzielle
Konsistenz, **Versions-/Abhängigkeitsconstraints** aus Abschnitt 3).

**Schema-Format:** Die Wahl zwischen **XSD**, **JSON Schema**, **Python-Datenklassen**
mit expliziter Validierung oder **Kombinationen** ist **bewusst offen**, solange das
Kriterium **maschinenlesbar + CI-tauglich** erfüllt ist. Die **festgelegte** Variante
wird **nachgereicht**, wenn das Konzept ansonsten **abgeschlossen** ist (Projektplan:
detaillierter Validierungsplan **eigenständiger Arbeitsschritt**).

Bis zur Festlegung: Mindestanforderung — Validierung muss **Ladezeit** und **CI**
abdecken können (kein reines Prosa-Changelog als einzige „Constraint“-Quelle).

--------------------------------------------------------------------------------
8. Tests und Referenz-FMUs
--------------------------------------------------------------------------------

* **Weitere FMU-Beispiele** recherchieren; **Lizenz** vor Repo-Übernahme prüfen.
* **Tests pro Phase** sukzessive ausbauen; **Bestand an .syn** für CLI-Featureabdeckung.
* **``@main.simulation_steps``:** In der aktuellen Codebasis **implementiert** — für
  stimulierte Kurzläufe und Zeitspezifikation in Tests nutzbar (Teststrategie unverändert
  gültig).

--------------------------------------------------------------------------------
9. Umsetzungsrahmen und Phasenplan
--------------------------------------------------------------------------------

* **Kein Big-Bang:** Umsetzung in **kleinen, reviewbaren** Schritten; pro Schritt keine
  Verschlechterung von Simulation/Editor; bei Bedarf **Feature-Flags** oder kurzzeitig
  parallele Pfade.
* **Lieferung pro Phase:** kurzes Design-Abstract → Implementierung → Tests → Spec-/Changelog-Zeile.

**Vorschlag Phasen** (aus den inhaltlichen Abschnitten ableitbar; Feinjustierung im
Backlog):

.. list-table::
   :header-rows: 1
   :widths: 12 88

   * - Phase
     - Inhalt (Kurz)
   * - **1**
     - **Synarius-Library-Descriptor** für FMU (Abschnitt 3): Namensräume,
       maschinenlesbare Versionen/Dependencies; **Controller liest ``type_key`` und
       Metadaten aus Descriptor** statt Hardcoding / FMU-Sonderpfade wo möglich.
   * - **2**
     - **Dispatch** für ``new`` / ``inspect`` / ``sync`` über
       ``dict[type_key → ElementTypeHandler]`` und Registrierung (Abschnitt 4); erste
       Handler-Implementierungen; **ABC** erst nach Spec v0.3 einfrieren (siehe Abschnitt 4).
   * - **3**
     - **Entfernen** verbleibender FMU-Speziallogik im **SynariusController** (Abschnitt 1,
       5); Entfernung ``fmu bind`` / ``fmu reload``; Migration ``.syn``/Skripte.

Ohne diese **Gliederung** bleibt „mehrstufig“ ein Wunsch ohne **planbaren** Schnitt.

--------------------------------------------------------------------------------
10. Verhältnis zu :doc:`plugin_api` (v0.1)
--------------------------------------------------------------------------------

* **plugin_api v0.1** bleibt Referenz für Manifest, ``Plugins/``, Capabilities.
* **Dieses Dokument v0.2.1** ist die **aktuelle** FMU/Lib/Roadmap-Spezifikation;
  **v0.2** ist der unmittelbare Vorgänger (siehe Kopfzeile).
* Bei Widersprüchen bis zur Aktualisierung einzelner Unter-Specs: für **FMU/Lib/Dispatch**
  gilt **v0.2.1**; für **Ladeschema alter Plugins** zunächst **plugin_api v0.1**.

--------------------------------------------------------------------------------
Änderungen gegenüber v0.2 (Kurz)
--------------------------------------------------------------------------------

* Terminologie **Synarius-Library**; **SynariusController** statt MinimalController.
* Abschnitt 4: vorläufiger **Handler-/Dispatch-Rahmen** (ABC, ``dict``, Registrierung);
  vollständige Signaturen → **v0.3**.
* Versionierung: **maschinenlesbar**, **Ladezeit-Prüfung** Lib↔Plugin.
* **fmu bind** / **fmu reload**: Entfernung **in dieser Iteration**, ohne Deprecation-Fenster.
* **Lib ohne Plugin** / **Plugin ohne Lib** explizit.
* **Phasenplan** (1–3); **Zielformat .syn** skizziert; Validierungs-**Schema-Format** bewusst
  offen bis zur Festlegung; Ist/Soll **inspect/sync**.

--------------------------------------------------------------------------------
Siehe auch
--------------------------------------------------------------------------------

* :doc:`plugin_api` — Plugin API (minimal v0.1)
* :doc:`fmu_library_plugin_concept_v0_2` — Konzept v0.2 (Vorgänger)
* :doc:`library_catalog` — Bibliothekskatalog
* :doc:`controller_command_protocol` — CCP
