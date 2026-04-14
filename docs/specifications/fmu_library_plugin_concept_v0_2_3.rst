..
   Konzept: FMU & generischer Controller — Lib als Semantik, Plugin als Ausführung (v0.2.3).

================================================================================
FMU, Synarius-Library und Plugins: Architekturkonzept (v0.2.3)
================================================================================

:Status: **Superseded** — siehe :doc:`fmu_library_plugin_concept_v0_2_4` (v0.2.4).
:Version: 0.2.3 (eingefroren; nur noch historischer Vergleich)
:Vorgänger: :doc:`fmu_library_plugin_concept_v0_2_2` (v0.2.2)
:Sprache: Deutsch (technische Begriffe englisch wo etabliert, z. B. ``type_key``, ``sync``)

--------------------------------------------------------------------------------
Terminologie (v0.2.3)
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
2. Grenze Synarius-Library vs. Plugin (v0.2.3)
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
* **Parser-Abhängigkeit (Namensräume vs. Attributpfade):** Der CCP-Parser nutzt
  **Punkt-Notation** bereits für **Attributpfade** (z. B. ``diagram.subtitle``,
  ``fmu.path``). ``fmulib.FmuInstance`` als **ein** Typ-Token setzt voraus, dass
  **namensraum-qualifizierte** ``type_key``-Strings von **Pfad-Syntax** mit Punkten
  unterscheidbar sind — **nicht-triviale Grammatikerweiterung**. Bearbeitungsort:
  :doc:`controller_command_protocol` und Parser-Implementierung. **Ohne** Klärung der
  Tokenisierung lässt sich das Descriptor-Format für Namensräume **nicht** unabhängig
  vom **Oberflächen-Token-Format** der CLI festlegen — siehe **Phase 1**, Spalte
  **Voraussetzungen / Blocker**.
* **Optionale Overlay-Pfade** auf Projektebene.
* **Versionierung (maschinenlesbar):** Versionen von **Core**, **Lib** und **Plugin**
  sind in den jeweiligen Metadaten **maschinenlesbar** abzulegen. **Wechselseitige
  Abhängigkeiten** (Lib benötigt Plugin ≥ x.y; Plugin benötigt Lib ≥ a.b) sind in den
  **entsprechenden Descriptors/Manifesten** zu dokumentieren.
* **Ladezeit-Prüfung:** Beim Laden ist zu **prüfen**, ob **Plugin und Lib zusammenpassen**
  (Versions- und Abhängigkeitsconstraints). **Wer** die Prüfung technisch ausführt, ist
  mit der **Besitzfrage** der Handler-Tabelle gekoppelt (Laufzeitwirkung derselben
  Architekturentscheidung) — **festzulegen in v0.3**, siehe Mindestinhalt Abschnitt 4.
* **Drop-in-Registrierung** zusätzlicher Typen ohne Core-Fork bleibt Ziel.

--------------------------------------------------------------------------------
4. Plugin- und Lib-API: Handler, Dispatch, Registrierung (vorläufiger Rahmen)
--------------------------------------------------------------------------------

Dieser Abschnitt **schließt** die Lücke aus v0.2 (dort: vollständig „folgende Spec“).
**Vollständig eingefrorene** Methodensignaturen (alle Parameter- und Rückgabetypen) sind
Gegenstand von **Konzept v0.3** — **Reihenfolge zwingend:**

#. **Spec v0.3** mit vollständig ausformuliertem Abschnitt 4 (Signaturen, Fehlerbilder,
   @abstractmethod-Regeln, Vererbungsmodell für ``type_key``, Besitz- und
   Validierungszuständigkeit).
#. **Dann** Einfrieren der abstrakten Basisklasse ``ElementTypeHandler`` (ABC).
#. **Dann** Plugin-/Core-Implementierungen.

**Methodennamen (fest v0.2.2, unverändert in v0.2.3):** Die Handler-Methoden heißen **``new``**, **``inspect``**,
**``sync``** — **symmetrisch zu den CCP-Kommandos** (kein Mapping ``create`` ↔ ``new``):

.. code-block:: text

   CCP:     new     inspect     sync
   Handler: new     inspect     sync

``new`` ist **kein** Python-Schlüsselwort; die Namensgleichheit mit ``__new__`` ist in
der Praxis unproblematisch (etabliertes Muster, z. B. ``Model.new()``). Wer CCP liest
und den Handler nachschlägt, findet **``handler.new(…)``** ohne Dokumentationsbruch.

**Generischer Ressourcen-Slot (fest v0.2.2, unverändert in v0.2.3):** Das Keyword **``resource_path``** ist der
**generische** Ressourcen-Parameter für **alle** ``ElementTypeHandler``, die eine
datei- oder pfadbasierte Ressource binden — **nicht** nur illustrativ in ``.syn``.
Die Umbenennung von typspezifischem ``fmu_path`` zu ``resource_path`` ist damit eine
**semantische** Entscheidung: ein einheitlicher Slot; die **konkrete** Bedeutung (FMU,
andere Datei) folgt aus ``type_key`` und Descriptor.

**Struktur (v0.3): Übergabe von ``resource_path`` an ``new``:** Semantisch ist der Name
des Slots fest; **strukturell** offen ist, ob ``resource_path`` ein **explizit benannter
Parameter** der Methode ``new`` ist oder als Eintrag in einem generischen Keyword-/
Options-Mapping (z. B. ``kwargs``-artig) übergeben wird. Das ist **kein** „Kleinigkeit“-
Detail — es bestimmt die **Signatur** von ``ElementTypeHandler.new`` und muss im
**Mindestinhalt v0.3** stehen (siehe Liste unten).

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
* **Dispatch:** ``registry[type_key] → Handler-Instanz``; Aufruf von **``new``** /
  **``inspect``** / **``sync``** erfolgt **vom Controller** (CCP-Pfad), **nicht** von
  der Lib als Laufzeit-Orchestrator — die Lib **liefert Metadaten**, der Handler **führt**
  aus.
* **Argumente für ``new``:** Generische Übergabe (u. a. ``resource_path``); **konkrete**
  Zuordnung Namen → Semantik aus **Descriptor** / Lib-Metadaten (Mapping-Tabelle in v0.3).
* **Verschachtelte / spezialisierte type_keys** (z. B. FMU-Instanz als Spezialisierung
  einer generischen Elementary-Variante): entweder **ein** Handler pro konkretem Key
  oder **Vererbung** der Handler-Klasse — **v0.3** muss das **Vererbungsmodell** und die
  **Dispatch-Regeln** bei Hierarchien **eindeutig** festlegen (Mehrdeutigkeiten vermeiden).
* **Unbekannter ``type_key``:** Verhalten **Ladezeit** (Descriptor/Plugin registriert
  nichts Passendes) vs. **Ausführungszeit** (Tippfehler im Skript) — **getrennt**
  spezifizieren in v0.3 (Fehlercodes, Meldungen).

**Pflicht vs. optional auf API-Ebene:** ``inspect`` und ``sync`` sind **generische**
CCP-Kommandos; welche Methoden des ABC mit ``@abstractmethod`` **Pflicht** sind und
welche **Default-Implementierungen** (optional / No-Op / „nicht unterstützt“) erhalten,
ist **untrennbar** von der ABC-Definition — **festzulegen in v0.3** (gemeinsam mit den
Signaturen). Ohne diese Regel kann das ABC **nicht** sinnvoll eingefroren werden.

**Mindestinhalt von Konzept v0.3 (Anforderung):**

* Vollständige Signaturen von ``ElementTypeHandler`` für **``new``**, **``inspect``**,
  **``sync``** inkl. aller Parameter- und Rückgabetypen.
* Welche Methoden sind ``@abstractmethod`` (**Pflicht**), welche haben **Default-**
  Implementierungen (**optional** / explizites „nicht unterstützt“)?
* **Vererbungsmodell** für spezialisierte / hierarchische ``type_keys``: ein Handler pro
  Key vs. Vererbung — **Dispatch-Regeln** ohne Mehrdeutigkeit.
* Exakte Signatur der **Registrierung** (wie meldet ein Plugin Handler für ``type_key``?).
* **Besitz** der Handler-Tabelle: SynariusController vs. PluginRegistry vs. neue
  ``ElementTypeRegistry`` — **eine** autoritative Stelle.
* **Übergabeform von ``resource_path`` an ``new``:** benannter Parameter vs. Eintrag in
  einem generischen Keyword-/Options-Mapping (strukturelle Signatur; zusammen mit den
  übrigen Parametern von ``new`` festzulegen).
* **Wer prüft** Lib↔Plugin-**Versionsconstraints zur Ladezeit** (Laufzeitwirkung derselben
  Entscheidung wie die Besitzfrage) — **konkrete** Zuständigkeit, nicht nur Prosa.
* Unbekannter ``type_key``: Ladezeit vs. Ausführungszeit (siehe oben).

--------------------------------------------------------------------------------
5. CCP (generisch), Ist/Soll, Entfernung ``fmu bind`` / ``fmu reload``
--------------------------------------------------------------------------------

**Ziel:** ``inspect`` und ``sync`` sind **generische** Kommandos; die **konkrete**
Implementierung liegt in **Handlern** bzw. Libs und ist auf Methodenebene **optional**
(siehe Abschnitt 4, @abstractmethod-Regeln in v0.3).

**Entfernung von ``fmu bind`` und ``fmu reload`` (konsistent mit Abschnitt 9):** Die
Befehle werden **nicht** „sofort“ oder in einer frühen Iteration gestrichen, **solange**
noch kein Ersatz über generisches ``inspect``/``sync`` mit **Handler-Dispatch** existiert.
**Zeitpunkt:** **Phase 3** dieser Roadmap — **nach** Phase 2 (Dispatch und Handler für
``new``/``inspect``/``sync``). Vorher wäre die Entfernung **inkonsistent** (kein vollständiges
Backend für die generischen Kommandos). **Ohne** gesondertes Deprecation-Fenster
(Projekte migrieren Skripte und ``.syn``; siehe Abschnitt 6). Nutzerterminologie bleibt
**``sync``** (nicht „reload“/„bind“ als Primärbegriffe).

**Ist/Soll (qualitativ — Stand der Doku, nicht Ersatz für Code-Audit):**

.. list-table::
   :header-rows: 1
   :widths: 28 36 36

   * - Kommando / Mechanismus
     - Ist (Richtung)
     - Soll (v0.2.3)
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
über den generischen Slot **``resource_path``** (semantisch **Abschnitt 4**; die
**strukturelle** Übergabe an ``handler.new`` ist dort bzw. in v0.3 festgelegt); statt
FMU-spezifischer Keyword-Ketten allein im Controller.

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

**Phasen und Abhängigkeiten** (v0.2.3: explizite **Blocker** und **Lieferobjekte**; Feinjustierung im Backlog):

.. list-table::
   :header-rows: 1
   :widths: 10 58 32

   * - Phase
     - Inhalt (Kurz)
     - Voraussetzungen / Blocker
   * - **1**
     - **Synarius-Library-Descriptor** für FMU (Abschnitt 3): Namensräume,
       maschinenlesbare Versionen/Dependencies. **Lieferobjekt (messbar, reviewbar):**
       (a) ein **ladbarer** FMU-Lib-Descriptor mit den vereinbarten Pflichtfeldern;
       (b) **mindestens eine** konkrete Änderung im **SynariusController** (oder unmittelbar
       davor geschalteter Lade-Schicht), sodass ein zuvor **im Code hardcodierter** Wert
       (z. B. ein Default-``type_key`` oder eine gleichwertige Konstante für FMU-Elemente)
       aus dem Descriptor **gelesen** wird. Weitere Nutzung von Descriptor-Metadaten ist
       **willkommen**, sofern ohne v0.3/ABC machbar — das **Minimum** ist (a)+(b).
     - **Kein** fertiges ABC und **keine** vollständige Spec v0.3 für Handler-Signaturen
       nötig — Phase 1 **kann** parallel zur Ausarbeitung v0.3 starten. **Zusätzliche
       Voraussetzung:** **Klärung** mit :doc:`controller_command_protocol` / Parser —
       **Tokenisierung** qualifizierter ``type_key``-Strings (ein Token ``fmulib.FmuInstance``)
       vs. **Attributpfade** mit Punkt-Notation; ohne diese Klärung fehlt der Lib-Descriptor
       für Namensräume ein **gemeinsames Fundament** mit der CCP-Oberfläche.
   * - **2**
     - **Dispatch** für ``new`` / ``inspect`` / ``sync`` über
       ``dict[type_key → ElementTypeHandler]`` und Registrierung (Abschnitt 4); erste
       Handler-Implementierungen; **ABC** erst nach Spec v0.3 einfrieren (siehe Abschnitt 4).
     - **Blockiert**, bis **Konzept v0.3** die in Abschnitt 4 genannten Punkte (Signaturen,
       @abstractmethod, Vererbungsmodell, Besitz, **wer prüft** Lib↔Plugin) **lieferbar**
       sind — ohne v0.3 kein stabiles Einfrieren des ABC.
   * - **3**
     - **Entfernen** verbleibender FMU-Speziallogik im **SynariusController** (Abschnitt 1,
       5); **Entfernung** ``fmu bind`` / ``fmu reload``; Migration ``.syn``/Skripte.
     - **Nach** abgeschlossener Phase 2: generische Kommandos **dispatchen** bereits auf
       Handler; Entfernung der Legacy-Befehle ist dann **sinnvoll** (Ersatz-Backend
       vorhanden).

Ohne diese **Gliederung** bleibt „mehrstufig“ ein Wunsch ohne **planbaren** Schnitt.

--------------------------------------------------------------------------------
10. Verhältnis zu :doc:`plugin_api` (v0.1)
--------------------------------------------------------------------------------

* **plugin_api v0.1** bleibt Referenz für Manifest, ``Plugins/``, Capabilities.
* **Dieses Dokument v0.2.3** ist die **aktuelle** FMU/Lib/Roadmap-Spezifikation;
  **v0.2.2**, **v0.2.1** und **v0.2** sind Vorgänger (siehe Kopfzeile).
* Bei Widersprüchen bis zur Aktualisierung einzelner Unter-Specs: für **FMU/Lib/Dispatch**
  gilt **v0.2.3**; für **Ladeschema alter Plugins** zunächst **plugin_api v0.1**.

--------------------------------------------------------------------------------
Änderungen gegenüber v0.2.2 (Kurz)
--------------------------------------------------------------------------------

* **``resource_path``:** Mindestinhalt v0.3 um **Übergabeform** an ``new`` (benannter Parameter
  vs. generisches Mapping) ergänzt; Abschnitt 4 erläutert Vorgriff auf die Signatur.
* **Punkt-Notation / Namensräume:** Parser-Konflikt Attributpfad vs. qualifizierter ``type_key``
  explizit; **Phase 1** mit Blocker „Klärung Tokenisierung“ und :doc:`controller_command_protocol`.
* **Phase 1 Lieferobjekt:** messbare Kriterien (ladbarer Descriptor + mindestens ein Hardcode
  durch Descriptor-Wert ersetzt); „wo möglich“ ersetzt.
* **„authoritative“** → **„autoritative“** (deutsche Doku).

--------------------------------------------------------------------------------
Siehe auch
--------------------------------------------------------------------------------

* :doc:`plugin_api` — Plugin API (minimal v0.1)
* :doc:`fmu_library_plugin_concept_v0_2` — Konzept v0.2
* :doc:`fmu_library_plugin_concept_v0_2_1` — Konzept v0.2.1
* :doc:`fmu_library_plugin_concept_v0_2_2` — Konzept v0.2.2 (Vorgänger)
* :doc:`library_catalog` — Bibliothekskatalog
* :doc:`controller_command_protocol` — CCP
