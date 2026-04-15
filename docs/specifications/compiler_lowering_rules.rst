..
   Synarius core — Compiler lowering rules for parameter-bound blocks.

================================================================================
Compiler Lowering Rules — Parameter-gebundene Blöcke
================================================================================

:Status: Entwurf
:Version: 0.2
:Supersedes: Version 0.1
:Scope: synarius-core — ``DataflowCompilePass``, Codegen-Backends,
        ``lookup_ops``-Referenzimplementierung

Verwandtes Konzept: :doc:`kennlinien_kennfelder_concept`

--------------------------------------------------------------------------------
Zweck
--------------------------------------------------------------------------------

Dieses Dokument definiert normativ:

1. Das **Mapping** von ``type_key``-Werten auf interne Lookup-Primitive.
2. Die **Semantik** jedes Lookup-Primitivs.
3. Die **Validierungsregeln** des ``DataflowCompilePass``.
4. Das **Fehlerverhalten** bei ungültigen Parametern oder Formen.

Lookup-Primitive sind **interne Kompilierungsartefakte** — keine Erweiterung
der FMFL-Sprache. Nutzer interagieren ausschließlich mit den Blocktypen.

Python-Implementierungen sind **Referenzimplementierungen** und definieren
keine normative Semantik.

--------------------------------------------------------------------------------
1. Lowering-Mapping
--------------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 22 20 58

   * - ``type_key``
     - Lookup-Primitiv
     - Signatur
   * - ``std.Kennwert``
     - ``param_scalar``
     - ``param_scalar(ref) → real``
   * - ``std.Kennlinie``
     - ``curve_lookup``
     - ``curve_lookup(ref, x) → real``
   * - ``std.Kennfeld``
     - ``map_lookup``
     - ``map_lookup(ref, x, y) → real``

``ref`` ist der über ``@active_dataset`` aufgelöste ``parameter_ref``-Wert.
Jeder andere ``type_key`` wird durch dieses Lowering nicht berührt.

--------------------------------------------------------------------------------
2. Auflösungsregeln für ``ref``
--------------------------------------------------------------------------------

Der ``DataflowCompilePass`` löst ``parameter_ref`` für jeden parameter-gebundenen
Knoten über ``@active_dataset`` auf:

1. Ersetze ``@active_dataset`` durch
   ``@main.parameters.data_sets.<active_dataset_name>``.
2. Traversiere den Modellbaum zum referenzierten ``MODEL.CAL_PARAM``-Knoten.
3. Ist kein aktives Dataset gesetzt → ``ParameterResolutionError``.
4. Ist der Knoten im aktiven Dataset nicht vorhanden → ``ParameterResolutionError``.
5. Lese Parameterdaten über ``ParameterRuntime.get_scalar / get_curve / get_map``
   als read-only Views.

Auflösung findet bei ``engine.init()`` statt.
Bei ``apply_pending_updates()`` nach Dataset-Wechsel werden die Schritte 1–5
für alle markierten Parameter erneut ausgeführt.

--------------------------------------------------------------------------------
3. Validierungsregeln
--------------------------------------------------------------------------------

3.1 Formvalidierung
~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Primitiv
     - Anforderungen
   * - ``param_scalar``
     - ``ndim == 0`` oder ``shape == (1,)``.
       Keine Achsen in ``parameter_axes``.
   * - ``curve_lookup``
     - ``ndim == 1``.
       Genau eine Achse (``axis_index == 0``) in ``parameter_axes``.
       ``len(axis_0) == shape[0]``.
   * - ``map_lookup``
     - ``ndim == 2``.
       Genau zwei Achsen (``axis_index`` in ``{0, 1}``) in ``parameter_axes``.
       ``len(axis_0) == shape[0]``, ``len(axis_1) == shape[1]``.

Verletzung → ``ParameterShapeError`` (fail-fast, CORE-ARCH-006).

3.2 Monotonie-Anforderung
~~~~~~~~~~~~~~~~~~~~~~~~~~

Alle Achsen müssen **streng monoton steigend** sein:

.. code-block:: text

   ∀ i ∈ [0, len(axis)-2] :  axis[i] < axis[i+1]

Verletzung → ``ParameterShapeError`` beim Kompilieren.

Beim DCM-Import wird fehlende Monotonie als Warnung protokolliert,
nicht als harter Fehler.

3.3 Mindestlänge
~~~~~~~~~~~~~~~~~

* ``curve_lookup``: ``len(axis_0) >= 2``.
* ``map_lookup``: ``len(axis_0) >= 2`` und ``len(axis_1) >= 2``.

Verletzung → ``ParameterShapeError``.

--------------------------------------------------------------------------------
4. Semantik der Lookup-Primitive
--------------------------------------------------------------------------------

4.1 ``param_scalar(ref)``
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   Eingabe:  ref   — aufgelöster Parameterverweis (Skalar)
   Ausgabe:  value := resolved_value(ref)

Keine Interpolation.

4.2 ``curve_lookup(ref, x)``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Eingabedaten: Achse ``a[0..n-1]`` (streng monoton steigend), Werte ``v[0..n-1]``.

**Extrapolation:**

.. code-block:: text

   x <= a[0]    →  out := v[0]
   x >= a[n-1]  →  out := v[n-1]

**Interpolation (linear):**

Sei ``i`` der größte Index mit ``a[i] <= x``:

.. code-block:: text

   t   := (x - a[i]) / (a[i+1] - a[i])
   out := v[i] + t * (v[i+1] - v[i])

``t`` liegt durch Konstruktion in ``[0, 1]``.

4.3 ``map_lookup(ref, x, y)``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Eingabedaten: Achsen ``a0[0..m-1]``, ``a1[0..n-1]``, Werte ``V[i,j]``
(Form ``(m, n)``, row-major).

**Clamp der Eingaben:**

.. code-block:: text

   x_c := clamp(x, a0[0], a0[m-1])
   y_c := clamp(y, a1[0], a1[n-1])

**Indexbestimmung:**

.. code-block:: text

   i := größter Index mit a0[i] <= x_c,  beschränkt auf [0, m-2]
   j := größter Index mit a1[j] <= y_c,  beschränkt auf [0, n-2]

**Bilineare Interpolation:**

.. code-block:: text

   tx := (x_c - a0[i]) / (a0[i+1] - a0[i])
   ty := (y_c - a1[j]) / (a1[j+1] - a1[j])

   out :=   V[i,   j  ] * (1-tx) * (1-ty)
          + V[i+1, j  ] *    tx  * (1-ty)
          + V[i,   j+1] * (1-tx) *    ty
          + V[i+1, j+1] *    tx  *    ty

``tx``, ``ty`` liegen durch Konstruktion in ``[0, 1]``.

4.4 Numerische Präzision
~~~~~~~~~~~~~~~~~~~~~~~~~

Die Definitionen gelten für reelle Arithmetik.
Implementierungen in IEEE-754 float64 sind konforme Referenzimplementierungen.
Gleitkomma-Rundungsabweichungen definieren keinen Semantikfehler.

--------------------------------------------------------------------------------
5. Fehlerverhalten
--------------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 42 28 30

   * - Fehlerfall
     - Zeitpunkt
     - Ausnahme
   * - ``@active_dataset`` nicht auflösbar (kein aktives Dataset)
     - ``engine.init()``
     - ``ParameterResolutionError``
   * - Parameter im aktiven Dataset nicht vorhanden
     - ``engine.init()``
     - ``ParameterResolutionError``
   * - Falscher ``ndim``
     - ``engine.init()``
     - ``ParameterShapeError``
   * - Achslänge passt nicht zu shape
     - ``engine.init()``
     - ``ParameterShapeError``
   * - Achse nicht monoton steigend
     - ``engine.init()``
     - ``ParameterShapeError``
   * - Achse kürzer als 2 Stützstellen
     - ``engine.init()``
     - ``ParameterShapeError``
   * - Parameter nach Dataset-Wechsel nicht gefunden
     - ``engine.step()`` UpdateParameters
     - Warnung; letzter Wert bleibt erhalten

Kein Fehlerfall ist silent.

--------------------------------------------------------------------------------
6. Codegen-Mapping
--------------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Primitiv
     - Hilfsfunktion (Python / C)
   * - ``param_scalar``
     - direkter ``param_handle.get_scalar()``-Aufruf
   * - ``curve_lookup``
     - ``syn_curve_lookup_linear_clamp``
   * - ``map_lookup``
     - ``syn_map_lookup_bilinear_clamp``

Hilfsfunktionen werden in ``synarius_core.dataflow_sim.lookup_ops`` (Python)
bereitgestellt.
Generierter Modellcode ruft ausschließlich diese Funktionen auf.

**Erweiterbarkeit:** Neue Interpolationsmodi (z. B. kubisch) erhalten eigene
Hilfsfunktionen (``syn_curve_lookup_cubic_clamp``).
Bestehende Funktionen werden nicht verändert.

--------------------------------------------------------------------------------
7. Beziehung zu anderen Spezifikationen
--------------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 42 58

   * - Spezifikation
     - Beziehung
   * - :doc:`kennlinien_kennfelder_concept`
     - Übergeordnetes Konzept; Abschnitt 5 verweist auf dieses Dokument.
   * - :doc:`parameters_data_model_dcm2_cdfx_v0_5`
     - Eigentumsregeln; read-only-View-Anforderung.
   * - :doc:`parameters_duckdb_sot_provisional`
     - DuckDB als einzige Wahrheitsquelle; guarded-setter-Pfad.
   * - :doc:`core_type_system`
     - ``MODEL.ELEMENTARY`` bleibt der Modelltyp.
   * - :doc:`controller_command_protocol`
     - CCP-Verben ``new``, ``set``, ``get`` decken alle Operationen ab;
       ``@active_dataset`` ist transparenter Alias in allen Pfadoperationen.
