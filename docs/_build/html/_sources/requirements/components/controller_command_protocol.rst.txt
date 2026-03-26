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

- ``virtual``: value is computed via getter/setter callbacks, not stored directly.
- ``exposed``: user-visible in GUI/property view.
- ``writable``: user-modifiable.

Top-Level Command Set
---------------------

- ``ls``: list children/entries in current context.
- ``lsattr``: list attributes in current context.
- ``cd <path>``: change active context.
- ``new <type> <args...> [kw=value ...]``: create object.
- ``select <ref...>``: replace current selection.
- ``set <target> <value>``: update attributes.
- ``del <ref...>``: delete objects.

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

- ``Variable``
- ``BasicOperator``
- ``Connector``
- ``DataViewer``
- ``SignalFile``
- ``FMUModule``
- ``Module``

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

Command categories:

- Inspection: ``ls``, ``lsattr``
- Navigation: ``cd``
- Construction: ``new``
- Interaction: ``select``
- Mutation: ``set``, ``del``

Construction outputs:

- Variable / operator / FMU / module -> node
- Connector -> edge
- DataViewer -> viewer node
- SignalFile -> external signal source binding

