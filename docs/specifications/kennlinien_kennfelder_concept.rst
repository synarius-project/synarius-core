..
   Synarius core — Kennlinien/Kennfelder implementation concept.

================================================================================
Kennlinien und Kennfelder — Implementierungskonzept
================================================================================

:Status: Entwurf (Implementierungskonzept)
:Version: 0.4
:Supersedes: Version 0.3
:Scope: synarius-core — Parameter-Subsystem, Standard-Bibliothek, Codegen

--------------------------------------------------------------------------------
Architekturelle Kernanweisung
--------------------------------------------------------------------------------

All Kennwert, Kennlinie, and Kennfeld evaluations operate exclusively on the
active dataset via a dynamic alias, ensuring consistent and deterministic
behavior across simulation and tooling.

Evaluation semantics are defined as language-independent lookup primitives.
Python implementations are reference implementations only and must not define
normative behavior.

Verwandte Spezifikation: :doc:`compiler_lowering_rules`

--------------------------------------------------------------------------------
1. Problemstellung und Ziel
--------------------------------------------------------------------------------

Das bestehende Synarius-Parametersystem unterstützt skalare Kalibrierparameter
(``MODEL.CAL_PARAM``, Kategorie ``VALUE``/``SCALAR``).
Regelungs- und Kalibrieranwendungen erfordern darüber hinaus:

* **Kennlinien** (1D-Lookup mit Interpolation),
* **Kennfelder** (2D-Lookup mit bilinearer Interpolation).

Das DuckDB-Repository-Schema unterstützt bereits mehrdimensionale Arrays
(``parameter_axes``, ``parameter_axis_meta``, ``parameter_values`` mit ``shape_json``)
und DCM-Import für diese Typen.

**Ziel dieses Konzepts:**

* Kennwert, Kennlinie und Kennfeld als **einzelne Modellblöcke** aus Nutzerperspektive.
* **Ausschließliche Bindung an das aktive Dataset** — kein alternatives Bindungsmodell.
* Dynamische Auflösung über den Alias ``@active_dataset`` in CCP und Laufzeit.
* Auswertungssemantik als **sprachunabhängige Lookup-Primitive**, normiert in
  :doc:`compiler_lowering_rules`.
* Codegen erzeugt Aufrufe gemeinsamer Hilfsfunktionen — kein Inline-Code.
* ``ParameterRuntime`` als zentrales Interface; das bestehende Parameter-Subsystem
  wird unverändert weitergenutzt.

--------------------------------------------------------------------------------
2. Dynamischer Dataset-Alias ``@active_dataset``
--------------------------------------------------------------------------------

2.1 Definition
~~~~~~~~~~~~~~

``@active_dataset`` ist ein **dynamischer Root-Alias** im CCP-Alias-System
(``SynariusController.alias_roots``).
Er wird bei jeder Auflösung neu evaluiert und zeigt auf das aktuell aktive Dataset.

.. code-block:: text

   @active_dataset  →  @main.parameters.data_sets.<active_dataset_name>

Die Auflösung hängt von ``ParameterRuntime.active_dataset_name`` ab und kann sich
während der Simulation ändern (wirksam ab dem nächsten Schritt, Abschnitt 6).

2.2 Auflösungsverhalten
~~~~~~~~~~~~~~~~~~~~~~~~~

* Auflösung erfolgt bei jeder CCP-Pfadauswertung und bei jeder
  ``parameter_ref``-Resolution im Simulations-Runtime.
* Ist kein aktives Dataset gesetzt, löst die Auflösung
  ``ParameterResolutionError`` aus (fail-fast).
* Der Alias ist **kein gespeicherter Zeiger** — er ist eine Funktion über
  ``ParameterRuntime.active_dataset()``.

2.3 CCP-Integration
~~~~~~~~~~~~~~~~~~~~

``@active_dataset`` wird wie alle anderen Root-Aliase in
``SynariusController.alias_roots`` gehalten.
Im Gegensatz zu statischen Aliase (``@main``, ``@objects``) wird der Eintrag
bei jeder Pfadauflösung dynamisch evaluiert, nicht einmalig bei ``init()``.

Beispiel-Interaktion im CLI:

.. code-block:: text

   > cd @active_dataset
   /parameters/data_sets/Dataset_A

   > get @active_dataset.Engine.TorqueMap.category
   CURVE

``@active_dataset`` ist für Debugging und Scripting nutzbar.
Die aufgelöste Form (``@main.parameters.data_sets.Dataset_A…``) kann zur
Diagnose ausgegeben werden.

2.4 Beispiel: Parameterpfad
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ein ``parameter_ref``-Attribut eines Kennfeld-Blocks:

.. code-block:: text

   @active_dataset.Engine.TorqueMap

Wird zur Laufzeit aufgelöst zu:

.. code-block:: text

   @main.parameters.data_sets.Dataset_A.Engine.TorqueMap

Nach einem Dataset-Wechsel auf ``Dataset_B`` löst derselbe ``parameter_ref``
im nächsten Schritt auf:

.. code-block:: text

   @main.parameters.data_sets.Dataset_B.Engine.TorqueMap

--------------------------------------------------------------------------------
3. Modellierungsebene — Neue Blocktypen in der Standard-Bibliothek
--------------------------------------------------------------------------------

3.1 Blockdefinitionen
~~~~~~~~~~~~~~~~~~~~~

.. list-table:: Neue Standard-Bibliotheksblöcke
   :header-rows: 1
   :widths: 14 16 14 18 38

   * - Block
     - Eingangspins
     - Ausgangspins
     - CAL_PARAM-Form
     - Lookup-Primitiv (normativ)
   * - ``std.Kennwert``
     - — (keine)
     - ``out`` (real)
     - Skalar
     - ``param_scalar(ref)``
   * - ``std.Kennlinie``
     - ``x`` (real)
     - ``out`` (real)
     - 1D + 1 Achse
     - ``curve_lookup(ref, x)``
   * - ``std.Kennfeld``
     - ``x``, ``y`` (real)
     - ``out`` (real)
     - 2D + 2 Achsen
     - ``map_lookup(ref, x, y)``

Die vollständige normative Semantik der Primitive ist in
:doc:`compiler_lowering_rules` spezifiziert.

3.2 Block-Attribute
~~~~~~~~~~~~~~~~~~~~

``parameter_ref`` (str, writable, exposed)
    Attributpfad auf den zugehörigen ``MODEL.CAL_PARAM``-Knoten.
    Verwendet ``@active_dataset`` als Root-Alias, z. B.:
    ``@active_dataset.Engine.TorqueMap``.

``type_key`` (str, nicht-writable)
    ``"std.Kennwert"``, ``"std.Kennlinie"`` bzw. ``"std.Kennfeld"``.

Das ist der vollständige Attributsatz. Es gibt keine weiteren konfigurierbaren
Parameter je Block.

3.3 Modell-Typ
~~~~~~~~~~~~~~

``MODEL.ELEMENTARY`` (``ElementaryInstance``) mit dem jeweiligen ``type_key``.
Kein neuer ``MODEL.*``-Typstring.

--------------------------------------------------------------------------------
4. Parameter-Bindungsmodell
--------------------------------------------------------------------------------

4.1 Ausschließliche Bindung an das aktive Dataset
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Alle Kennwert-, Kennlinie- und Kennfeld-Blöcke lesen **ausschließlich aus dem
aktiven Dataset**.
Es gibt keine alternative Bindung an ein festes Dataset und keine
per-Block-Konfiguration der Datensatzquelle.

Rationale:

* Entspricht dem realen Kalibrier-Workflow: ein Ingenieur wechselt das
  aktive Dataset, um einen anderen Parametersatz zu aktivieren — alle Blöcke
  folgen diesem Wechsel konsistent.
* Verhindert gemischte Parameterzustände (Block A aus Dataset X, Block B aus
  Dataset Y) während einer Simulation.
* Vereinfacht die Laufzeitsemantik: ein einziger Zustandswechsel (Dataset-Wechsel)
  wirkt auf alle Blöcke.
* Reduziert die UI-Komplexität: keine Pro-Block-Datensatzkonfiguration.

4.2 Auflösung von ``parameter_ref``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``ParameterRuntime.resolve_cal_param_for_block(block)`` löst ``parameter_ref``
auf wie folgt:

1. Ersetze ``@active_dataset`` durch den aktuellen Pfad des aktiven Datasets.
2. Traversiere den Modellbaum zum referenzierten ``MODEL.CAL_PARAM``-Knoten.
3. Gibt den Knoten zurück; ist er nicht gefunden, ``ParameterResolutionError``.

4.3 Fehlende Parameter
~~~~~~~~~~~~~~~~~~~~~~~

* Zur Kompilierzeit / ``engine.init()``: ``ParameterResolutionError`` (fail-fast).
* Nach einem Dataset-Wechsel während laufender Simulation, falls der
  Parameter im neuen Dataset nicht vorhanden ist: letzter bekannter Wert
  bleibt erhalten; Warnung wird protokolliert.

4.4 Form-Validierung und Monotonie
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Der ``DataflowCompilePass`` prüft beim Kompilieren:

* ``std.Kennwert``: ``ndim == 0`` oder ``shape == (1,)``.
* ``std.Kennlinie``: ``ndim == 1``, genau eine Achse.
* ``std.Kennfeld``: ``ndim == 2``, genau zwei Achsen.
* Alle Achsen: streng monoton steigend.

Verletzungen → ``ParameterShapeError`` (fail-fast).

Beim DCM-Import wird fehlende Monotonie als Warnung protokolliert,
nicht als Fehler — der Fehler tritt verbindlich beim Kompilieren auf.

--------------------------------------------------------------------------------
5. Lookup-Primitive — Semantik (Zusammenfassung)
--------------------------------------------------------------------------------

5.1 Abgrenzung und Minimalset
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Lookup-Primitive sind **interne Kompilierungsartefakte**.
Sie sind keine Erweiterung der FMFL-Sprache.

Das folgende minimale Set definiert das normative Lookup-Verhalten für v0.1:

* ``param_scalar`` — skalarer Direktzugriff.
* ``curve_lookup`` — lineare Interpolation, konstante Extrapolation.
* ``map_lookup`` — bilineare Interpolation, konstante Extrapolation.

Es gibt keine weiteren Interpolationsmodi in v0.1.

5.2 Primitive (Kurzreferenz)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**``param_scalar(ref)``**
    Gibt den skalaren Parameterwert zurück. Keine Interpolation.

**``curve_lookup(ref, x)``**
    1D-Lookup: lineare Interpolation zwischen Stützstellen,
    konstante Extrapolation (Clamp) an beiden Rändern.
    Achse muss streng monoton steigend sein.

**``map_lookup(ref, x, y)``**
    2D-Lookup: bilineare Interpolation, konstante Extrapolation
    in beiden Dimensionen.
    Beide Achsen müssen streng monoton steigend sein.

Die vollständige normative Semantik — inklusive formaler Definitionen —
ist in :doc:`compiler_lowering_rules` spezifiziert.

5.3 Python als Referenzimplementierung
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Python-Implementierungen dieser Primitive sind **Referenzimplementierungen**.
Sie müssen die Semantik aus :doc:`compiler_lowering_rules` korrekt abbilden.
Abweichungen einer Implementierung von der Spezifikation sind Bugs in der
Implementierung, nicht in der Spezifikation.

--------------------------------------------------------------------------------
6. Simulationssemantik — UpdateParameters-Phase
--------------------------------------------------------------------------------

6.1 Schleifenmodell
~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   engine.init(param_runtime=<optional>):
       1. Kompiliere Dataflow
          → erkenne und validiere Kennwert/Kennlinie/Kennfeld-Knoten
          → prüfe parameter_ref-Auflösbarkeit (via @active_dataset)
          → senke Knoten auf Lookup-Primitive ab
       2. Initialisiere Plugins (FmuRuntime, weitere)
       3. Falls param_runtime gegeben:
          UpdateParameters → lade CAL_PARAM-Daten in param_cache
       4. Snapshot des initialen Workspaces

   engine.step():
       1. UpdateParameters — apply_pending_updates(param_cache)
          → löse @active_dataset neu auf
       2. Werte Modell aus (run_equations mit Lookup-Primitiven)
       3. FMU step (falls Plugin aktiv)
       4. Workspace → Variablen schreiben

   engine.reset():
       1. Workspace-Snapshot wiederherstellen
       2. request_full_parameter_update() → beim nächsten step() wirksam

6.2 Dataset-Wechsel
~~~~~~~~~~~~~~~~~~~~

* Ein Dataset-Wechsel (``set @main.parameters.active_dataset_name <name>``)
  ruft ``request_full_parameter_update()`` auf.
* Die Änderung wird als ausstehender Update in die Pending-Queue eingestellt.
* Sie wird **ausschließlich** am Beginn des nächsten Schritts wirksam
  (Phase 1 von ``engine.step()``).
* Kein Dataset-Wechsel wirkt mitten in einem Berechnungsschritt.

6.3 Optionale Engine-Kopplung
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``SimpleRunEngine`` erhält ``ParameterRuntime`` als optionales Argument:

.. code-block:: python

   class SimpleRunEngine:
       def __init__(
           self,
           model: Model,
           param_runtime: ParameterRuntime | None = None,
           **kwargs
       ): ...

Ist ``param_runtime=None`` und enthält das Modell Kennwert/Kennlinie/Kennfeld-Blöcke,
löst ``init()`` ``ParameterResolutionError`` aus (fail-fast).
Modelle ohne solche Blöcke sind nicht betroffen.

6.4 Abgrenzung zu Stimuli
~~~~~~~~~~~~~~~~~~~~~~~~~~

Stimuli und Parameter-Updates sind orthogonal:

* Parameter-Updates ändern Lookup-Tabellen **vor** der Gleichungsauswertung.
* Stimuli überlagern ``Variable``-Ausgaben **innerhalb** eines Schritts.

--------------------------------------------------------------------------------
7. GUI-Integration
--------------------------------------------------------------------------------

7.1 Parametereditor-Aufruf aus Blöcken
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``open_parameter_editor`` (bool, virtual, writable, exposed)
    Analog zu ``DataViewer.open_widget``.
    Schreiben von ``True`` öffnet den Parametereditor für den referenzierten
    ``CAL_PARAM``-Knoten.

Auflösung: ``parameter_ref → @active_dataset → CAL_PARAM → Widget``.

7.2 Widget-Auswahl nach Parameterform
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 30 50

   * - Blocktyp
     - Widget
     - Bemerkung
   * - ``std.Kennwert``
     - Skalarer Wert-Editor (bestehend)
     - Eingabefeld für einen float-Wert.
   * - ``std.Kennlinie``
     - 1D-Modus des ``CalibrationMapWidget``
     - Liniengraph + editierbare Wertetabelle.
       Neuer Modus im bestehenden Widget (synarius-apps).
   * - ``std.Kennfeld``
     - ``CalibrationMapWidget`` (bestehend)
     - Vollständig vorhanden.

7.3 Änderungspropagation
~~~~~~~~~~~~~~~~~~~~~~~~~

GUI-Edits schreiben über den guarded-setter-Pfad von ``ParameterRuntime``
(konsistent mit ``parameters_duckdb_sot_provisional.rst``).
Der Widget-Commit-Handler ruft ``request_parameter_update(parameter_ref)`` auf.

--------------------------------------------------------------------------------
8. Standard-Initialisierung neuer CAL_PARAM-Knoten
--------------------------------------------------------------------------------

Wird ein Block ohne expliziten ``parameter_ref`` erzeugt, erstellt der
Element-Type-Handler über
``ParameterRuntime.register_cal_param_node_from_import()``
einen Minimal-Parameter im aktiven Dataset:

.. list-table::
   :header-rows: 1
   :widths: 20 25 55

   * - Blocktyp
     - Form
     - Initialdaten
   * - ``std.Kennwert``
     - Skalar
     - ``values = [0.0]``
   * - ``std.Kennlinie``
     - 1D, 2 Stützstellen
     - ``axis_0 = [0.0, 1.0]``, ``values = [0.0, 1.0]``
   * - ``std.Kennfeld``
     - 2D, 2×2
     - ``axis_0 = [0.0, 1.0]``, ``axis_1 = [0.0, 1.0]``,
       ``values = [[0.0, 0.0], [0.0, 0.0]]``

Der auto-generierte ``parameter_ref`` lautet ``@active_dataset.<block_name>``.

Diese Logik liegt ausschließlich im Element-Type-Handler, nicht im Controller.

--------------------------------------------------------------------------------
9. Erforderliche Änderungen in synarius-core
--------------------------------------------------------------------------------

9.1 Modell-Kern
~~~~~~~~~~~~~~~~

Keine Änderungen. ``parameter_ref`` ist ein gewöhnlicher ``AttributeDict``-Eintrag.

9.2 ``SynariusController`` — dynamischer Alias ``@active_dataset``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``alias_roots`` erhält einen dynamisch evaluierten Eintrag:

.. code-block:: python

   # In SynariusController.__init__ / refresh_element_type_handlers:
   self.alias_roots["@active_dataset"] = DynamicAlias(
       resolver=lambda: self.model.parameter_runtime().active_dataset()
   )

``DynamicAlias`` ist ein minimales Wrapper-Objekt (oder ein Callable-Eintrag),
das von ``_resolve_path()`` beim ersten Traversierungsschritt evaluiert wird,
anstatt wie statische Aliase direkt als Objekt verwendet zu werden.

Ist kein aktives Dataset gesetzt, gibt der Resolver ``None`` zurück;
``_resolve_path()`` löst dann ``CommandError("@active_dataset: no active dataset")``
aus.

9.3 ``ParameterRuntime`` — neue API
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   def resolve_cal_param_for_block(
       self, block: ElementaryInstance
   ) -> BaseObject | None: ...

   def get_scalar(
       self, parameter_ref: str, dataset_id: UUID | None = None
   ) -> float: ...

   def get_curve(
       self, parameter_ref: str, dataset_id: UUID | None = None
   ) -> tuple[np.ndarray, np.ndarray]: ...
   # Rückgabe: (axis_0, values) als read-only Views

   def get_map(
       self, parameter_ref: str, dataset_id: UUID | None = None
   ) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...
   # Rückgabe: (axis_0, axis_1, values) als read-only Views

   def request_parameter_update(self, parameter_ref: str) -> None: ...
   def request_full_parameter_update(self) -> None: ...

   def apply_pending_updates(self, param_cache: dict) -> None: ...

Alle Array-Rückgaben sind read-only Views (``arr.flags.writeable = False``).

9.4 ``DataflowCompilePass`` — Erweiterung
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Erkennt Knoten mit ``type_key`` in
  ``{"std.Kennwert", "std.Kennlinie", "std.Kennfeld"}``.
* Löst ``parameter_ref`` über ``@active_dataset`` auf und validiert Form
  und Monotonie.
* Ergänzt ``CompiledDataflow`` um ``param_bound_node_ids: frozenset[UUID]``.
* Senkt Knoten auf Lookup-Primitive gemäß :doc:`compiler_lowering_rules` ab.

9.5 ``SimpleRunEngine`` — Änderungen
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``param_runtime: ParameterRuntime | None = None`` als optionales Argument.
* Internes ``param_cache: dict`` für aufgelöste Parameterdaten.
* ``step()`` ruft ``apply_pending_updates(param_cache)`` am Anfang auf.
* ``run_equations(workspace, param_cache)`` erhält ``param_cache`` als Argument.

9.6 Neues Modul: ``synarius_core.dataflow_sim.lookup_ops``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Python-Referenzimplementierungen gemäß :doc:`compiler_lowering_rules`:

.. code-block:: python

   def syn_curve_lookup_linear_clamp(
       axis: np.ndarray, values: np.ndarray, x: float
   ) -> float: ...

   def syn_map_lookup_bilinear_clamp(
       axis_0: np.ndarray, axis_1: np.ndarray,
       values: np.ndarray, x: float, y: float
   ) -> float: ...

9.7 Codegen-Backends — Erweiterung
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``python_step_emit.py`` und ``codegen_kernel.py`` emittieren für
Lookup-Primitiv-Knoten Aufrufe der Hilfsfunktionen aus ``lookup_ops``
mit ``param_cache`` als Handle.
Kein Inline-Interpolationscode im generierten Modellcode.

9.8 Controller (CCP)
~~~~~~~~~~~~~~~~~~~~~

Keine neuen CCP-Befehle.
``@active_dataset`` ist als dynamischer Alias transparent in alle bestehenden
Pfadoperationen (``cd``, ``ls``, ``get``, ``set``, ``lsattr``) integriert.

--------------------------------------------------------------------------------
10. Standard-Bibliothek — Ergänzungen
--------------------------------------------------------------------------------

10.1 Neue Komponenten
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   standard_library/components/
   ├─ Kennwert/
   │   ├─ elementDescription.xml
   │   └─ icons/
   ├─ Kennlinie/
   │   ├─ elementDescription.xml
   │   └─ icons/
   └─ Kennfeld/
       ├─ elementDescription.xml
       └─ icons/

10.2 elementDescription.xml — Kennlinie (Beispiel)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: xml

   <ElementDescription>
     <Ports>
       <Port kind="in"  name="x"   type="real"/>
       <Port kind="out" name="out" type="real"/>
     </Ports>
     <Parameters>
       <Parameter name="parameter_ref" type="string" default=""/>
     </Parameters>
     <!--
       Kein <Behavior>-FMFL.
       Semantik: curve_lookup() — linear, clamp.
       Spezifikation: compiler_lowering_rules.rst
     -->
   </ElementDescription>

10.3 Element-Type-Handler
~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``new``: Block anlegen + Auto-Initialisierung des CAL_PARAM im aktiven Dataset.
* ``inspect``: Parameterform, Achseninfo, aktives Dataset.
* ``sync``: Neuladen über ``request_parameter_update(parameter_ref)``.

--------------------------------------------------------------------------------
11. Migrationsstrategie
--------------------------------------------------------------------------------

11.1 Kompatibilität
~~~~~~~~~~~~~~~~~~~~

* Bestehende ``.syn``-Modelle bleiben unverändert gültig.
* ``SimpleRunEngine`` ist durch optionales ``param_runtime``-Argument
  rückwärtskompatibel.
* ``run_equations()``-Signaturerweiterung um ``param_cache``:
  bestehender Code übergibt leeres Dict.

11.2 Inkrementelle Einführung
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. ``compiler_lowering_rules.rst`` finalisieren.
2. ``@active_dataset``-Alias im Controller implementieren.
3. ``lookup_ops``-Modul anlegen und unit-testen.
4. ``ParameterRuntime``-API erweitern (Pending-Queue, Zugriffsmethoden).
5. ``DataflowCompilePass`` erweitern (Erkennung, Validierung, Lowering).
6. ``SimpleRunEngine`` erweitern (``param_runtime``, ``param_cache``).
7. ``std.Kennwert`` + Codegen: einfachster Fall verifizieren.
8. ``std.Kennlinie`` + ``syn_curve_lookup_linear_clamp``.
9. ``std.Kennfeld`` + ``syn_map_lookup_bilinear_clamp``.
10. GUI: ``open_parameter_editor``, 1D-Widget-Modus.

11.3 Ausblick
~~~~~~~~~~~~~~

* **n-dimensionale Parameter:** Mit derselben Architektur erweiterbar.
* **Weitere Interpolationsmodi:** Neue Hilfsfunktionsvarianten; bestehende
  Funktionen bleiben unverändert.
* **Statische Einbettung (C-Export):** Eigener Spezifikationsabschnitt;
  schließt Laufzeit-Updates aus.

--------------------------------------------------------------------------------
12. Offene Punkte
--------------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Punkt
     - Status
   * - ``DynamicAlias``-Implementierung im Controller
     - ``_resolve_path()`` muss Callable-Aliase von Objekt-Aliasen unterscheiden.
       Minimale Änderung (ein ``callable()``-Check in der Alias-Auflösung).
   * - ``compiler_lowering_rules.rst`` finalisieren
     - Muss vor Implementierungsbeginn des ``DataflowCompilePass`` abgenommen werden.
   * - 1D-Widget-Modus in ``CalibrationMapWidget``
     - Scope synarius-apps.
   * - Statische Einbettung (C-Export)
     - Nicht in v0.1; eigene Spezifikation mit Dataset-Snapshot-Semantik.
