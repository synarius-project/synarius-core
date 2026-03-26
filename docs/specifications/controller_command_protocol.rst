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
   * - ``del``
     - Delete object(s)
     - ``del <ref...>``
     - Object(s) removed

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

Examples::

   set @objects/variables/Speed.stim_const_val 10.0
   set LogLevel 1

``select`` and ``del``
----------------------

- ``select <ref1> <ref2> ...`` replaces current selection in specified order.
- ``del <ref1> <ref2> ...`` deletes referenced objects and deterministically updates dependent structures (selection/connectors).

Script Execution
----------------

A script is UTF-8 plain text with one command per line.

- Execution order: top to bottom.
- Optional: reset ID counters at script start (configurable).
- Default failure behavior: stop on first error and surface it.
- Optional mode: continue-on-error with full failure log.

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
   * - ``del``
     - Mutation
     - Refs
     - Remove nodes/edges

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

