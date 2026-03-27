Controller Command Protocol
===========================

Scope
-----

This specification defines the text-based command interface used to communicate with the Synarius Core controller.
Commands are line-oriented and can run interactively (console) or in batch mode (script execution).

General Concepts
----------------

- One command per line.
- Lines starting with ``#`` are comments and must be ignored.
- Tokens are whitespace-separated.
- Double-quoted strings may contain spaces.
- Typed values include numbers, booleans, and (optionally) collection literals.
- The controller maintains a current selection set for batch operations.
- Recommended root aliases: ``@latent``, ``@signals``, ``@objects``, ``@main``, ``@controller``.

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
     - ``select <ref...>``
     - Selection updated
   * - ``set``
     - Set attribute(s) on a target
     - ``set <target> <value>``
     - Attribute updated
   * - ``get``
     - Read attribute(s) from a target
     - ``get <target>``
     - Value output
   * - ``del``
     - Delete object(s)
     - ``del <ref...>``
     - Object(s) removed
   * - ``load``
     - Load a model from a command stack/script
     - ``load "<scriptPath>" [into=<path>] [idPolicy=remap|keep]``
     - Model elements created/updated

Object Referencing
------------------

``<ref>`` resolution precedence (recommended):

1. direct internal key
2. name
3. display name
4. numeric ID (optional)

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
     - ``new Variable <name> <x> <y> <size> [refName="<ref>"]``
   * - ``BasicOperator``
     - Create an operator node
     - ``new BasicOperator <opSymbol> <x> <y> [name="<name>"]``
   * - ``Connector``
     - Create a connection edge
     - ``new Connector <fromRef> <toRef> idxInPin=<int> [idxOutPin=<int>]``
   * - ``DataViewer``
     - Create a viewer/plot node
     - ``new DataViewer <x> <y> [options...]``
   * - ``SignalFile``
     - Register/load a signal file
     - ``new SignalFile "<path>" [name="<name>"] [fileType="<type>"]``
   * - ``FMUModule``
     - Create an FMU-backed node
     - ``new FMUModule "<fmuPath>" <x> <y> <size> [refName="<ref>"]``
   * - ``Module``
     - Create a submodule
     - ``new Module "<modelDescriptionPath>" <x> <y> <size> [refName="<ref>"]``

Pin semantics:

- ``idxInPin``: destination input pin index
- ``idxOutPin``: source output pin index

``set`` Forms
-------------

1. ``set <path>.<attr> <value>``
2. ``set <attr> <value>`` (applies to current context)
3. ``set @selection <attr> <value>`` (applies to each selected element)

Examples::

   set @objects/variables/Speed.stim_const_val 10.0
   set LogLevel 1
   set @selection gain 2.5

``set`` Detailed Semantics
--------------------------

Target Resolution
~~~~~~~~~~~~~~~~~

- In ``set <path>.<attr> <value>``, the object is resolved from ``<path>`` and ``<attr>`` is updated on that object.
- In ``set <attr> <value>``, the current context object is the target.
- In ``set @selection <attr> <value>``, the update is applied to all selected objects.

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

- In ``get <path>.<attr>``, the object is resolved from ``<path>`` and ``<attr>`` is read from that object.
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

``select`` and ``del``
----------------------

- ``select <ref1> <ref2> ...`` replaces current selection in specified order.
- ``del <ref1> <ref2> ...`` deletes referenced objects and deterministically updates dependent structures (selection/connectors).

``load`` Command
----------------

The ``load`` command applies a command stack to materialize a model (or submodel) according to this protocol.

Canonical form::

   load "<scriptPath>" [into=<path>] [idPolicy=remap|keep]

Semantics
~~~~~~~~~

- ``<scriptPath>`` points to a UTF-8 script containing one protocol command per line.
- ``into=<path>`` optionally selects the insertion root. If omitted, the active context is used.
- ``idPolicy=remap`` (default) remaps loaded IDs to fresh model-local IDs.
- ``idPolicy=keep`` keeps IDs from the loaded command stack and must fail on duplicates.
- Loading must be deterministic and follow top-to-bottom command order.
- Loading should be transactional at command-stack level: on failure, no partial model state should remain by default.

Error Behavior
~~~~~~~~~~~~~~

- Missing/unreadable script path causes command failure with a clear error.
- Protocol parsing errors in the loaded command stack cause command failure with line reference.
- Duplicate IDs under ``idPolicy=keep`` cause command failure.
- In transactional mode, failures must roll back all changes created by ``load``.

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
     - Refs
     - Remove nodes/edges
   * - ``load``
     - Reconstruction
     - Script path (+ optional target path)
     - Rebuild model/submodel from protocol command stack

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
   * - ``FMUModule``
     - Node
     - Yes
     - Yes (``.fmu``)
   * - ``Module``
     - Node
     - Yes
     - Yes (model description file)

