Controller Command Protocol
===========================

Scope
-----

This specification defines the text-based command interface used to communicate with the Synarius Core controller.
Commands are line-oriented and can run interactively (console) or in batch mode (script execution).

Command log and model fidelity
------------------------------

When command lines are logged, that log must be sufficient to reconstruct exactly the model the user built.
Therefore, the domain model must not be changed except by executing those string commands through the controller implementing this protocol—no persistent mutations that bypass the Controller Command Protocol.

General Concepts
----------------

- One command per line.
- Lines starting with ``#`` are comments and must be ignored.
- Tokens are whitespace-separated.
- Double-quoted strings may contain spaces.
- Typed values include numbers, booleans, and (optionally) collection literals.
- The controller maintains a current selection set for batch operations.
- Recommended root aliases: ``@latent``, ``@signals``, ``@objects``, ``@main``, ``@controller``.

Interactive hosts (for example ParaWiz console) **SHOULD** surface protocol-level failures—unknown commands, invalid arguments, unresolved references—as a **single human-readable message line** (the controller’s error text), without attaching a full implementation stack trace. Lower-level or unexpected errors may still be logged with diagnostics according to host policy.

Command vocabulary (design)
---------------------------

The protocol favors a **small set of universal verbs** (for example ``cd``, ``ls``, ``lsattr``, ``get``, ``set``, ``del``).
Domain-specific behavior should be exposed primarily through **attributes** on model objects, including **virtual**
attributes (see *Attribute Meta-Properties*): specialized semantics are implemented with getter/setter hooks so
hosts keep using the same ``get`` / ``set`` forms instead of multiplying ad-hoc command verbs. Separate top-level
commands are reserved when attribute access is a poor fit (for example ``swap_ds`` across two references) or for
coarse workflow entry points such as ``load`` and ``import``.

Attribute Meta-Properties
-------------------------

Each attribute may carry the following properties:

.. list-table::
   :header-rows: 1

   * - Property
     - Meaning
   * - ``virtual``
     - Value is computed via getter/setter callbacks and is not stored directly.
   * - ``exposed``
     - Attribute is user-visible in GUI/property views.
   * - ``writable``
     - Attribute is modifiable by user operations.

Hierarchical attribute paths (dict-valued attributes)
-----------------------------------------------------

Many attributes are scalars, but some attributes store mapping trees (notably ``pin``).

For those attributes the CCP **SHALL** support multi-segment paths:

* ``set <objectRef>.<attr.path> <value>``
* ``get <objectRef>.<attr.path>``

Where ``<objectRef>`` is the first dotted segment (as resolved by the controller’s path/reference rules),
and ``<attr.path>`` is the remainder joined with ``.``.

Path parsing uses the escaping rules documented in ``attribute_path_semantics.rst`` (``\\.``, ``\\\\``).

``lsattr`` lists flattened rows for dict-valued attributes, for example ``pin.in.direction``, ``pin.out.y``.

Top-Level Command Set
---------------------

.. list-table::
   :header-rows: 1

   * - Command
     - Purpose
     - Canonical syntax
     - Result
   * - *(empty line)*
     - No operation
     - *(blank line)*
     - No effect
   * - ``ls``
     - List children/entries in current context
     - ``ls``
     - Text output
   * - ``lsattr``
     - List attributes in current context
     - ``lsattr``
     - Text output
   * - ``cd``
     - Change active context/folder
     - ``cd <path>``
     - Active context updated
   * - ``new``
     - Create a new object/element
     - ``new <type> <args...> [kw=value ...]``
     - New object reference
   * - ``select``
     - Set current selection
     - ``select <ref...>``, ``select -p …``, ``select -m …``, or ``select`` (clear)
     - Selection updated
   * - ``set``
     - Set attribute(s) on a target
     - ``set …`` / ``set @selection …`` / ``set -p @selection …``
     - Attribute updated
   * - ``get``
     - Read attribute(s) from a target
     - ``get <target>``
     - Value output
   * - ``print``
     - Print optional type-specific information for a target object
     - ``print <ref>`` or ``print``
     - Human-readable informational output
   * - ``del``
     - Delete or move to trash (see semantics below)
     - ``del <ref...>`` or ``del @selected``
     - Object(s) moved to trash or permanently removed
   * - ``mv``
     - Reparent an object under another container
     - ``mv <ref> <destContainerPath>``
     - Object moved; variable registry updated when crossing the trash subtree
   * - ``cp``
     - Copy parameter payload between calibration-parameter nodes (parameters / DuckDB)
     - ``cp cal_param <sourceRef> <destRef>``
     - Destination CAL_PARAM updated from source; one-line status (for example ``ok <ref> -> <ref>``)
   * - ``undo``
     - Step backward in controller edit history
     - ``undo`` or ``undo <n>``
     - Prior state restored (see history rules)
   * - ``redo``
     - Step forward after ``undo``
     - ``redo`` or ``redo <n>``
     - Undone change reapplied
   * - ``load``
     - Load a model from a command stack/script
     - ``load "<scriptPath>" [into=<path>] [idPolicy=remap|keep]``
     - Model elements created/updated; undo/redo stacks cleared
   * - ``import``
     - Import calibration parameters from a file into a data set
     - ``import dcm <DataSetRef> "<filePath>"``
     - ``MODEL.CAL_PARAM`` nodes created; undo/redo stacks cleared
   * - ``write``
     - Export calibration parameters from the **active** parameter data set to a DCM file
     - ``write "<outputPath>"``
     - UTF-8 DCM written; does not clear undo/redo stacks

Object Referencing
------------------

``<ref>`` resolution precedence (recommended):

1. **Global stable reference:** a single token of the form ``<name>@<uuid>`` (no ``/``) resolves to the model object with that UUID anywhere in the tree (required so undo/redo can replay ``mv`` lines after objects moved under ``trash``).
2. direct internal key
3. name (under current path context)
4. display name
5. numeric ID (optional)

If resolution is ambiguous, the controller must raise an explicit error.

Paths and Targets
-----------------

- Relative path: ``./Child/SubChild``
- Alias-root path: ``@objects/variables/Speed``
- Attribute target: ``<path>.<attr>``

Examples::

   cd ./subsystemA
   set @objects/variables/Speed.signalMapped "VehicleSpeed"
   set ./VarA.Value 3.14

Selection-targeted attribute set:

- ``@selection set <attr> <value>``
- or shorthand via object paths and aliases.

``new`` Type Catalogue
----------------------

Minimum supported construction types:

.. list-table::
   :header-rows: 1

   * - Type
     - Intent
     - Canonical syntax
   * - ``Variable``
     - Create a variable node
     - ``new Variable <name> [<x> <y> <size>] [key=value …]``
   * - ``BasicOperator``
     - Create an operator node
     - ``new BasicOperator <opSymbol> [<x> <y> [<size>]] [name="<name>" …]``
   * - ``Connector``
     - Create a connection edge
     - ``new Connector <fromRef> <toRef> idxInPin=<int> [idxOutPin=<int>]``
   * - ``DataViewer``
     - Create a viewer/plot node
     - ``new DataViewer <x> <y> [options...]``
   * - ``SignalFile``
     - Register/load a signal file
     - ``new SignalFile "<path>" [name="<name>"] [fileType="<type>"]``
   * - ``FmuInstance``
     - Create an FMU-backed elementary (default library ``type_key``)
     - ``new FmuInstance <name> [<x> <y> [<size>]] fmu_path="…" [fmi_version=… fmu_type=… fmu_ports=… fmu_variables=… fmu_extra_meta=…]``
   * - ``Elementary`` (with ``fmu_path``)
     - FMU-backed block with explicit ``type_key``
     - ``new Elementary <name> [<x> <y> [<size>]] type_key=… fmu_path="…" [same FMU kwargs as ``FmuInstance``]``
   * - ``Module``
     - Create a submodule
     - ``new Module "<modelDescriptionPath>" <x> <y> <size> [refName="<ref>"]``

Pin semantics:

- ``idxInPin``: destination input pin index
- ``idxOutPin``: source output pin index

Placement (locatable diagram nodes)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For ``Variable`` and ``BasicOperator``, optional trailing numerics set ``position`` (``x``, ``y``) and, when given, square ``size``:

- ``new Variable <name>`` leaves ``(x, y) = (0, 0)`` and default size.
- ``new Variable <name> <x> <y> <size>`` sets placement (all three numbers required when used).
- ``new BasicOperator <opSymbol>`` leaves ``(x, y) = (0, 0)`` and default size.
- ``new BasicOperator <opSymbol> <x> <y>`` sets ``x`` and ``y``; default size remains.
- ``new BasicOperator <opSymbol> <x> <y> <size>`` sets placement and square size.

Scripts loaded into the model are the source of truth for layout: diagram hosts must place nodes from the instances' ``x`` / ``y`` (and related attributes), not from name-based or host-local position tables.

FMU blocks and attributes
~~~~~~~~~~~~~~~~~~~~~~~~~

There is no abbreviated form ``new FMU "<path>"``; use ``new FmuInstance`` or ``new Elementary`` with ``fmu_path=`` as above.

FMU-backed elementaries store a subtree under ``fmu.*`` (path, guid, ``variables``, ``extra_meta``, …) and diagram connectivity under ``pin.*``. The generic commands ``get``, ``set``, and ``lsattr`` support multi-segment paths on mapping-valued attributes (for example ``get <ref>.fmu.path``, ``set <ref>.fmu.model_identifier Mini``, ``lsattr <ref>`` lists flattened rows such as ``fmu.path`` and ``pin.u.direction``).

**List-valued ``fmu.variables``:** hierarchical ``get`` / ``set`` only traverses mappings, not list indices. Refresh the variable catalog from a ``.fmu`` file using ``fmu bind`` or ``fmu reload`` (below), or replace the entire list in one assignment using a safely parsed literal (same rules as ``fmu_variables=…`` on ``new``).

**No separate ``fmu set`` verb:** use ``set <ref>.fmu.<segment>…`` for scalar or nested map fields.

**Dedicated FMU commands** (optional helpers; not a substitute for ``get``/``set`` where those suffice):

- ``fmu inspect "<pathTo.fmu>"`` — parse FMI 2.0 ``modelDescription.xml`` inside the archive and print JSON (guid, model identifier, scalar variables, default experiment hints, …). FMI 3 is rejected until supported.
- ``fmu bind <ref> [from="<pathTo.fmu>"]`` — re-read an FMU and merge metadata into the elementary's ``fmu`` subtree and rebuild ``pin`` from input/output variables (library pin seed from ``type_key`` is preserved first, then FMU ports override). If ``from=`` is omitted, the file at the current ``fmu.path`` is used. With ``from=``, ``fmu.path`` is updated to that file's resolved path.
- ``fmu reload <ref> [path="<newPath>"]`` — optionally set ``fmu.path``, then run the same merge as ``fmu bind`` without changing the path when ``path=`` is omitted.

These commands are not recorded on the undo stack (same category as a complex external edit).

Parameter data sets (``MODEL.PARAMETER_DATA_SET``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each registered parameter data set exposes a virtual integer attribute ``num_params``:

* ``get <dataSetRef>.num_params`` — number of calibration parameters stored in the DuckDB repository for that set.
* ``set <dataSetRef>.num_params 0`` — removes all ``MODEL.CAL_PARAM`` descendants under the set and deletes the
  corresponding parameter rows from the repository; the data set **node** and the ``data_sets`` row **remain**.
  Writes with any value other than ``0`` are rejected (only ``0`` means “clear all parameters in this set”).

With ``cd`` into the data set node, the usual shorthand applies: ``get num_params`` and ``set num_params 0``.

``set`` Forms
-------------

1. ``set <path>.<attr> <value>``
2. ``set <attr> <value>`` (applies to current context)
3. ``set @selection <attr> <value>`` (applies to each selected element)
4. ``set -p @selection <attr> <delta>`` (add ``<delta>`` to the current value of ``<attr>`` on each selected object; option ``-p`` immediately after ``set``)
5. ``set -p @selection position <dx> <dy>`` (add ``dx``/``dy`` to ``x``/``y`` on each selected locatable object)

Examples::

   set @objects/variables/Speed.stim_const_val 10.0
   set LogLevel 1
   set @selection gain 2.5
   set -p @selection x 0.5
   set -p @selection position 12 -3

``set`` Detailed Semantics
--------------------------

Target Resolution
~~~~~~~~~~~~~~~~~

- In ``set <objectRef>.<attr> <value>``, the object before the first ``.`` is resolved with the same rules as a standalone reference (global stable ``name@<uuid>``, alias path from ``@…``, or path relative to ``current``), then ``<attr>`` is updated on that object.
- In ``set <attr> <value>``, the current context object is the target.
- In ``set @selection <attr> <value>``, the update is applied to all selected objects.
- In ``set -p @selection <attr> <delta>``, the parsed ``<delta>`` must be numeric; it is **added** to the current attribute value on each selected object that exposes a numeric ``<attr>``. Objects that do not support the attribute or a numeric read are **skipped** (they do not count toward the returned update count).
- In ``set -p @selection position <dx> <dy>``, ``dx`` and ``dy`` are added to the model position of each selected ``LocatableInstance`` (same skip semantics). This form is intended for hosts (e.g. Studio) to apply one shared translation to a multi-selection.
- ``set @selection -p …`` is **not** valid; use ``set -p @selection …`` only.
- The return value for ``-p`` forms is the number of objects successfully updated (as a decimal string), not necessarily ``len(selection)``.

Value Parsing
~~~~~~~~~~~~~

- Scalar values support at least: string, integer, float, boolean.
- Strings may be quoted and may contain spaces.
- If collection literals are supported, they must be parsed safely (no ``eval``).

Validation Rules
~~~~~~~~~~~~~~~~

- The target object must exist and be uniquely resolved.
- The attribute must exist or be creatable according to the object type policy.
- Attribute write access must be validated (for example via writable/virtual rules).
- For virtual attributes, setter callbacks are used where defined.

Error Behavior
~~~~~~~~~~~~~~

- If the target cannot be resolved, the command fails with a clear error.
- If the attribute is not writable or value conversion fails, the command fails with a clear error.
- In script execution, default behavior is fail-fast (stop on first error).

``get`` Forms
-------------

1. ``get <path>.<attr>``
2. ``get <attr>`` (reads from current context)
3. ``get @selection <attr>`` (reads from each selected element)

Examples::

   get @objects/variables/Speed.value
   get LogLevel
   get @selection Name

``get`` Detailed Semantics
--------------------------

Target Resolution
~~~~~~~~~~~~~~~~~

- In ``get <objectRef>.<attr>``, the object before the first ``.`` is resolved like a standalone reference (global ``name@<uuid>``, ``@…`` path, or relative path), then ``<attr>`` is read from that object.
- In ``get <attr>``, the current context object is used as the target.
- In ``get @selection <attr>``, values are read from each selected object.

Read Semantics
~~~~~~~~~~~~~~

- For regular attributes, the stored value is returned.
- For virtual attributes, getter callbacks are used.
- Multi-target reads (selection) return deterministic output ordering based on selection order.

Output Semantics
~~~~~~~~~~~~~~~~

- Single-target reads return one value line.
- Multi-target reads return one line per resolved object in deterministic order.
- Missing values should be represented explicitly (for example ``<none>``), not silently skipped.

Error Behavior
~~~~~~~~~~~~~~

- If the target cannot be resolved, the command fails with a clear error.
- If the attribute is unknown or not readable, the command fails with a clear error.
- In script execution, default behavior is fail-fast (stop on first error).

``print`` Forms
---------------

1. ``print <ref>``
2. ``print`` (applies to current context)

Examples::

   print @objects/variables/Speed
   print Kp

``print`` Detailed Semantics
----------------------------

Purpose
~~~~~~~

``print`` is a general CCP command for optional, type-specific informational output intended for CLI users.
It complements ``get`` by providing compact, human-friendly summaries rather than raw attribute reads.

Target Resolution
~~~~~~~~~~~~~~~~~

- In ``print <ref>``, the object is resolved from ``<ref>`` using normal CCP path/reference rules.
- In ``print`` without argument, the current context object is used.

Output Semantics
~~~~~~~~~~~~~~~~

- Output is plain text (may span multiple lines).
- The minimal controller provides type-specific summaries for the following targets (non-exhaustive; other hosts may extend):

  * **Model root** (``ComplexInstance`` equal to the model root): name, child count, model type if set.
  * **Kenngrößen** (``MODEL.CAL_PARAM``): name, category (``VALUE``, ``CURVE``, ``MAP``, …), parameter and dataset IDs, dataset name, optional display name, comment, unit, conversion, source, numeric format and value semantics; for text parameters, the text value; otherwise a value summary (shape, min/max/mean for numeric arrays) and per-axis support point ranges where axes exist.
  * **Parameter dataset** (``MODEL.PARAMETER_DATA_SET``): name, id, optional source path/format/hash, direct child count in the model tree.
  * **Parameter data container** (``MODEL.PARAMETER_DATA_CONTAINER``): name, id, container type, child count.
  * **Parameter datasets folder** (``MODEL.PARAMETER_DATA_SETS``): entry count.
  * **Model parameters area** (``MODEL.PARAMETERS``): active dataset name if set, direct child count.
  * **Variable**, **BasicOperator**, **Connector**, **DataViewer**, **ElementaryInstance** (including ``fmu.path`` when present), generic **ComplexInstance**, **VariableMappingEntry**.
- When no specialized formatter exists, implementations may return a minimal generic object summary (for example Python type and name).

Error Behavior
~~~~~~~~~~~~~~

- ``print`` with more than one argument is invalid.
- If the target cannot be resolved, the command fails with a clear error.
- For a ``MODEL.CAL_PARAM`` node without repository data, the command fails with a clear error.
- If printing is unsupported for a resolved target, behavior must be consistent and explicit (clear error or documented generic fallback).

``select`` and ``del``
----------------------

- ``select <ref1> <ref2> ...`` replaces current selection in specified order.
- ``select -p <ref1> <ref2> ...`` appends resolved objects to the existing selection (stable order, no duplicates).
- ``select -m <ref1> <ref2> ...`` removes each resolved object from the current selection if present (order of remaining entries preserved; each reference must resolve).
- ``select`` with no arguments clears the selection.
- The model contains a dedicated ``trash`` folder under the root. Objects **not** already under that subtree are **moved into trash** (soft delete) when ``del`` runs; objects **already** in the trash subtree are **permanently** removed from the model.
- ``del`` must not combine, in one command, objects that are in the trash subtree with objects that are not; implementations must fail with a clear error.
- ``del <ref1> <ref2> ...`` updates dependent structures (selection/connectors) deterministically.
- ``del @selected`` applies to every object in the current controller selection. Deletion order is deterministic: all selected ``Connector`` instances first (by ``hash_name``), then ``BasicOperator``, then ``Variable``, then any other selected types. This matches the order hosts should use so edges are removed before nodes they attach to.
- ``del @selected`` must appear alone (no further references on the same line). An empty selection yields ``0`` removals.
- After any ``del`` command, the selection is pruned: objects removed from the model or only present under trash are dropped from the selection.

Note: ``@selection`` is reserved for ``set`` / ``get`` batch targets; ``@selected`` is reserved for ``del`` only.

``mv`` Command
--------------

- ``mv <ref> <destContainerPath>`` reparents the object identified by ``<ref>`` so it becomes a direct child of the container resolved by ``<destContainerPath>`` (must be a ``ComplexInstance``).
- Moving across the boundary of the trash subtree updates the variable name registry (variables in trash do not count toward live registry entries).
- The root model object and the canonical ``trash`` folder itself must not be moved.

``cp`` Command
--------------

Copy numeric or text calibration-parameter **payload** (values, axes, and associated metadata in the parameters repository) from one ``MODEL.CAL_PARAM`` node to another. Both references must resolve to attached ``ComplexInstance`` nodes with that model type. The **destination** keeps its own ``parameter_id`` and ``data_set_id``; only the stored payload is replaced to match the source.

Canonical form::

   cp cal_param <sourceRef> <destRef>

Semantics
~~~~~~~~~

- ``cal_param`` is the only supported subcommand in minimal implementations; other subcommands should be rejected with a clear usage error.
- **Numeric** parameters: destination row is updated via the same repository path as a full cal-param write (values, axis arrays, axis names/units, category and scalar metadata fields written by that path). The destination keeps its existing ``source_identifier`` (and, for text parameters, ``conversion_ref``) so the target does not inherit the source’s provenance keys.
- **Text** parameters (ASCII category): destination ``parameters_all`` fields are updated from the source for content-bearing columns; ``conversion_ref`` and ``source_identifier`` on the destination row are left unchanged. Source and destination must both be text parameters (mixed text/numeric copy fails).
- **Undo:** ``cp`` is **not** required to participate in the linear undo/redo stack (implementations may treat it as a direct repository mutation without an inverse command).

Error Behavior
~~~~~~~~~~~~~~

- Wrong arity, unknown subcommand, or non-``CAL_PARAM`` targets must fail with a clear error.
- Repository validation errors (for example text onto numeric) propagate as command failures.

``undo`` and ``redo``
---------------------

- Controllers may maintain a bounded linear undo history of user-visible mutations (for example ``set``, ``new``, ``select``, ``mv``, soft ``del``). The ``cp`` command is not required to be undoable.
- ``undo`` reapplies the inverse of the last recorded step; ``undo <n>`` applies ``n`` inverses in order (``n`` is a positive decimal integer). ``redo`` / ``redo <n>`` mirror this for steps that were undone.
- Issuing a new undoable command after ``undo`` clears the redo stack (standard editor semantics).
- ``load`` is **not** recorded in undo history; a successful ``load`` clears both undo and redo stacks.
- History depth may be capped (for example default 100 steps); oldest entries are discarded when the cap is exceeded.

``load`` Command
----------------

The ``load`` command applies a command stack to materialize a model (or submodel) according to this protocol.

Canonical form::

   load "<scriptPath>" [into=<path>] [idPolicy=remap|keep]

Formal Parameters
~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Default
     - Meaning
   * - ``scriptPath``
     - string (path)
     - *(required)*
     - Path to the command-stack script file
   * - ``into``
     - path
     - current context
     - Target root where loaded objects are materialized
   * - ``idPolicy``
     - enum: ``remap`` | ``keep``
     - ``remap``
     - ID handling strategy for loaded objects

Semantics
~~~~~~~~~

- ``<scriptPath>`` points to a UTF-8 script containing one protocol command per line.
- ``into=<path>`` optionally selects the insertion root. If omitted, the active context is used.
- ``idPolicy=remap`` (default) remaps loaded IDs to fresh model-local IDs.
- ``idPolicy=keep`` keeps IDs from the loaded command stack and must fail on duplicates.
- Loading must be deterministic and follow top-to-bottom command order.
- Loading should be transactional at command-stack level: on failure, no partial model state should remain by default.

Execution Phases
~~~~~~~~~~~~~~~~

1. Parse and validate parameters.
2. Resolve target root (``into`` or current context).
3. Read and parse command-stack script.
4. Execute commands in order against an isolated transactional context.
5. Commit model changes atomically if all commands succeed.
6. On failure, roll back all changes produced by the ``load`` command.

Return Semantics
~~~~~~~~~~~~~~~~

- On success, ``load`` returns a deterministic summary containing at least:
  - number of executed commands,
  - number of created/updated/deleted objects,
  - applied ID policy.
- On failure, ``load`` returns a structured error with:
  - failing command line number,
  - failing command text (or normalized form),
  - error category and message.

Error Behavior
~~~~~~~~~~~~~~

- Missing/unreadable script path causes command failure with a clear error.
- Protocol parsing errors in the loaded command stack cause command failure with line reference.
- Duplicate IDs under ``idPolicy=keep`` cause command failure.
- In transactional mode, failures must roll back all changes created by ``load``.

``import`` and ``write`` (DCM)
----------------------------

**Import** — canonical form::

   import dcm <DataSetRef> "<filePath>"

- Resolves ``<DataSetRef>`` to a ``MODEL.PARAMETER_DATA_SET`` node, reads a UTF-8 DCM file, and creates ``MODEL.CAL_PARAM`` children plus repository rows for each supported block (see the parameters / DCM specifications for the supported subset).
- Relative ``<filePath>`` resolution follows the same rules as other file-opening commands (for example relative to the directory of the script last opened with ``load`` when the path is not absolute).
- On success, returns the number of imported parameters as a decimal string.
- A successful ``import`` clears the undo and redo stacks (same class as ``load``).

**Write** — canonical form::

   write "<outputPath>"

- Exports **all** parameters stored in DuckDB for the **active** ``MODEL.PARAMETER_DATA_SET`` (see the parameters runtime ``active_dataset`` / ``active_dataset_name``). The file uses ``KONSERVIERUNG_FORMAT 2.0`` and the same numeric subset as the DCM importer (for example ``FESTWERT``, ``FESTWERTEBLOCK``, ``KENNLINIE``, ``KENNFELD``, ``STUETZSTELLENVERTEILUNG``).
- Text parameters (for example ASCII category) are **not** emitted as DCM blocks; they appear as comment lines in the output so the file remains parseable.
- Parent directories for ``<outputPath>`` are created when missing.
- Relative ``<outputPath>`` is resolved like ``import`` (including relative to the directory of the script last opened with ``load`` when not absolute).
- On success, returns the number of exported numeric blocks as a decimal string, optionally followed by a short note if text parameters were omitted.
- ``write`` does **not** clear undo/redo stacks.

Script Execution
----------------

A script is UTF-8 plain text with one command per line.

- Execution order: top to bottom.
- Optional: reset ID counters at script start (configurable).
- Default failure behavior: stop on first error and surface it.
- Optional mode: continue-on-error with full failure log.
- ``load`` reuses the same line-oriented protocol semantics and may be used as a higher-level entry point for model reconstruction.

Safety Requirements
-------------------

- No ``eval`` in production mode.
- Use safe parsing for typed values.
- If collection literals are supported, parsing must be explicit, safe, and deterministic.

Integrated Summary
------------------

A) Command Summary
~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Command
     - Category
     - Targeting
     - Typical usage
   * - ``ls``, ``lsattr``
     - Inspection
     - Current context
     - Debugging and exploration
   * - ``cd``
     - Navigation
     - Path
     - Change active folder/subgraph
   * - ``new``
     - Construction
     - Type registry
     - Build graph/nodes/viewers
   * - ``select``
     - Interaction
     - Refs
     - Prepare batch operations
   * - ``set``
     - Mutation
     - Path / selection / context
     - Configure objects and runtime
   * - ``get``
     - Inspection
     - Path / selection / context
     - Read object state and runtime values
   * - ``del``
     - Mutation
     - Refs or ``@selected``
     - Soft-delete to trash or hard-delete from trash
   * - ``mv``
     - Mutation
     - Object ref + container path
     - Reparent nodes (including restore from trash)
   * - ``cp``
     - Mutation (parameters)
     - Two CAL_PARAM refs
     - Copy calibration payload between datasets / parameters
   * - ``undo`` / ``redo``
     - History
     - Optional step count
     - Reverse or reapply recent edits
   * - ``load``
     - Reconstruction
     - Script path (+ optional target path)
     - Rebuild model/submodel from protocol command stack
   * - ``import`` / ``write``
     - Parameters (DCM)
     - Data set ref + path / active data set + path
     - Bulk ingest or export of calibration parameters

B) Construction Type Summary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Type
     - Produces
     - Connectable
     - External resource
   * - ``Variable``
     - Node
     - Yes
     - No
   * - ``BasicOperator``
     - Node
     - Yes
     - No
   * - ``Connector``
     - Edge
     - N/A
     - No
   * - ``DataViewer``
     - Viewer node
     - Reads variables
     - No
   * - ``SignalFile``
     - Signal source
     - Maps to variables
     - Yes (file)
   * - ``FmuInstance`` / ``Elementary`` (FMU)
     - Node
     - Yes
     - Yes (``.fmu``)
   * - ``Module``
     - Node
     - Yes
     - Yes (model description file)

