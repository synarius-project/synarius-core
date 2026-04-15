..
   Synarius plugin architecture — technical concept (v0.3, English).

================================================================================
Synarius libraries, plugins, and core — technical architecture (v0.3)
================================================================================

:Status: Architecture specification (normative rules + provisional details)
:Version: 0.3
:See also: :doc:`plugin_concept_v0_3_plugin_api`, :doc:`library_catalog`, :doc:`controller_command_protocol`, :doc:`attribute_path_semantics`

--------------------------------------------------------------------------------
1. Purpose and scope
--------------------------------------------------------------------------------

This document defines the **target architecture** for FMU-backed and similar workflows under
Synarius: how **Synarius libraries** (descriptors, ``type_key``), **plugins** (execution and
tooling), **handlers** (per-type ``new`` / ``inspect`` / ``sync``), and **Synarius Core**
(:class:`~synarius_core.controller.synarius_controller.SynariusController`, CCP) work together.

**In scope**

* Normative separation of concerns (library vs. plugin vs. core).
* Registry ownership, dispatch symmetry, and CCP navigation patterns.
* Relationship between ``type_key`` strings and navigable CCP trees.

**Out of scope**

* Exact XML schemas for every descriptor field (see library and plugin manifests).
* Parser grammar for CCP (see :doc:`controller_command_protocol`).

**Conformance tags**

* **[NORMATIVE]** — Architectural rule; deviation only deliberately and with documentation.
* **[PROVISIONAL]** — Intended direction; details may evolve with implementation.
* **[OPEN QUESTION]** — Decision pending; named here only.
* **[FUTURE WORK]** — Deferred to a later specification or implementation milestone.

--------------------------------------------------------------------------------
2. Terminology
--------------------------------------------------------------------------------

**Synarius Core**

The runtime and control kernel (including ``SynariusController`` and generic model IR). The
**Controller Command Protocol (CCP)** is the controller’s textual command surface.

**Synarius library (“Lib”)**

The descriptive layer: ``type_key``, namespaces, metadata about types and permitted operations.
Elements are declared in FMF library manifests (see :doc:`library_catalog`).

**Plugin**

An installable extension following :doc:`plugin_concept_v0_3_plugin_api`: a folder with
``pluginDescription.xml``, declared **capabilities**, and a Python **contribution provider**
subclass of ``SynariusPlugin``.

**Handler**

An ``ElementTypeHandler`` instance responsible for ``new``, ``inspect``, and ``sync`` for one
``type_key`` (and optional aliases). Signatures and context types are defined in
:doc:`plugin_concept_v0_3_plugin_api`.

**Library catalog**

Loads FMF library descriptors from disk and exposes the ``@libraries`` tree (:doc:`library_catalog`).

**Informal plugin categories** (readability only; **[PROVISIONAL]**)

Plugins remain defined by **capabilities** and the manifest. Categories below do **not** add new
manifest types:

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Category
     - Typical capability tags
   * - Backend / codegen
     - ``backend:*`` — translation, code generation.
   * - Runtime
     - ``runtime:*`` — execution (e.g. FMU stepping).
   * - Tool / IDE
     - Studio and editor integration (often outside the simulation kernel).
   * - Library delivery
     - Shipping library descriptors; versioned alongside plugins, **not** identical to a runtime
       plugin package.

--------------------------------------------------------------------------------
3. Architecture principles [NORMATIVE]
--------------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 32 68

   * - Principle
     - Statement
   * - **Synarius library as semantic source**
     - Model semantics (types, pins, allowed operations) live in the library and its
       descriptors / FMFL.
   * - **Plugin as execution layer**
     - Runtime behavior (e.g. FMU binding) lives in plugins and handlers, not in ad hoc FMU-only
       branches of the core.
   * - **Synarius Core stays generic**
     - The controller performs generic operations and dispatches by registry; the **target** design
       avoids hard-coded FMU bind/reload logic in the core.
   * - **Separation of responsibilities**
     - Semantics (Lib) · execution (plugin/handler) · orchestration (Synarius Core).
   * - **Plugins extend behavior, not semantics**
     - New meaning in the model is expressed through the library (descriptor / FMFL), not hidden
       plugin logic inside the core.
   * - **Library and plugin are decoupled**
     - Machine-readable metadata and version compatibility checks **[PROVISIONAL]** attach to the
       load pipeline and validation.

--------------------------------------------------------------------------------
4. Interaction: library, plugin, and core
--------------------------------------------------------------------------------

**4.1 Roles [NORMATIVE] / [PROVISIONAL]**

* [NORMATIVE] An element type is **semantically** described by the Synarius library (descriptor,
  ``type_key``, namespace).
* [NORMATIVE] **Execution** (e.g. FMU stepping) lives outside the core, in plugins; the core
  orchestrates generic steps.
* [PROVISIONAL] For each ``type_key`` there is a **handler** (``ElementTypeHandler``). The plugin
  class returns handler instances from ``SynariusPlugin.element_type_handlers()`` (see
  :doc:`plugin_concept_v0_3_plugin_api`).

**4.2 Dispatch [NORMATIVE] / [PROVISIONAL]**

* [PROVISIONAL] CCP operations ``new``, ``inspect``, and ``sync`` are routed to the handler
  registered for the ``type_key``.
* [NORMATIVE] **Ownership** of registration and dispatch: **Section 5** (``ElementTypeRegistry``).

**4.3 Symmetry: CCP and handler [PROVISIONAL]**

.. code-block:: text

   CCP:     new     inspect     sync
   Handler: new     inspect     sync

**4.4 Edge cases [NORMATIVE]**

* **Lib-only:** declarative / FMFL types without a runtime backend are allowed.
* **Plugin without matching FMU library:** other domains remain valid as long as capabilities and
  the registry allow them.

--------------------------------------------------------------------------------
5. Registries, ownership, and CCP navigation
--------------------------------------------------------------------------------

**5.1 Ownership [NORMATIVE]**

``SynariusController`` holds **PluginRegistry** and **ElementTypeRegistry** as subsystems.

* **PluginRegistry** loads plugins per :doc:`plugin_concept_v0_3_plugin_api`, instantiates the
  declared plugin class **without constructor arguments**, and collects **contributions**:

  * ``element_type_handlers()`` — each ``ElementTypeHandler`` is registered under its ``type_key``
    (and any ``handler_aliases``) in **ElementTypeRegistry**;
  * optionally ``compile_passes()`` and ``simulation_runtime()`` for other subsystems.

* **ElementTypeRegistry** is the **authoritative** ``type_key → handler`` map for dispatching
  ``new``, ``inspect``, and ``sync``.

**5.2 CCP transparency [NORMATIVE]**

Both registries are exposed under **alias roots** in the CCP address space, analogous to
``@libraries`` → library catalog:

* ``@plugins`` → ``PluginRegistry``
* ``@types`` → ``ElementTypeRegistry``

Existing commands ``ls``, ``lsattr``, ``cd``, and ``get`` apply to these subtrees **without new
verbs**. Plugin objects expose attributes such as ``version``, ``state``, and ``capabilities``;
handler objects expose ``type_key`` and related metadata.

**5.3 Navigation paths vs. ``type_key`` [NORMATIVE]**

The dot in ``type_key`` (e.g. ``fmulib.FmuInstance``) maps to a **tree** under ``@types``: a
container segment ``fmulib`` and a leaf ``FmuInstance``, i.e. ``@types/fmulib/FmuInstance``. A
**flat** path segment that still contains a dot (e.g. ``@types/fmulib.FmuInstance``) is **invalid**,
because it collides with attribute-path syntax in CCP. The same hierarchy applies under
``@libraries`` for catalog paths (e.g. ``@libraries/fmulib/FmuInstance``).

The **type token** in the ``new`` command (``new fmulib.FmuInstance …``) is a single
**space-delimited** token and is **not** subject to CCP navigation path rules.

**5.4 ``new``: type token vs. attribute path [NORMATIVE]**

The first argument to ``new`` — the type designator — is **not** split by the
``<objectRef>.<attr.path>`` logic used by ``get`` and ``set``. The string ``fmulib.FmuInstance`` is
looked up as a whole against ``ElementTypeRegistry``. Normative one-line clarifications also belong
in :doc:`controller_command_protocol` and :doc:`attribute_path_semantics`; this document states the
architectural requirement.

**5.5 Handler lifecycle [PROVISIONAL] / [FUTURE WORK]**

Handlers are typically created when the plugin is loaded (from ``element_type_handlers()``) and
registered until ``PluginRegistry.reload()``. Finer-grained unload **[FUTURE WORK]** must avoid
dangling handler references.

**5.6 Plugin ``state`` [PROVISIONAL]**

``state`` on plugin nodes (e.g. ``loaded``, ``failed``) is read-only in early iterations; mutable
unload **[PROVISIONAL]** is not specified here.

--------------------------------------------------------------------------------
6. ``resource_path`` [PROVISIONAL] / [NORMATIVE] / [OPEN QUESTION]
--------------------------------------------------------------------------------

* [PROVISIONAL] ``resource_path`` denotes a **generic resource reference** for types that bind an
  external asset (paths, URIs, or catalog entries, depending on type and descriptor).
* [NORMATIVE] The slot is **not** a bag for arbitrary opaque data; additional structure stays in the
  descriptor and ``type_key``.
* [PROVISIONAL] Handlers receive CCP arguments as ``args`` and ``kwargs``; ``resource_path`` can be
  passed as a keyword. Final normative grammar **[FUTURE WORK]** in CCP and handler docs.

--------------------------------------------------------------------------------
7. Validation [PROVISIONAL]
--------------------------------------------------------------------------------

* [PROVISIONAL] Machine-readable checks for library descriptors and plugin manifests, suitable for
  CI.
* [OPEN QUESTION] Schema technology (XSD, JSON Schema, Python validators, …).

--------------------------------------------------------------------------------
8. Related specifications
--------------------------------------------------------------------------------

* :doc:`plugin_concept_v0_3` — Documentation hub (v0.3).
* :doc:`plugin_concept_v0_3_plugin_api` — Manifest, discovery, capabilities, Python ABCs.
* :doc:`library_catalog` — FMF library catalog.
* :doc:`controller_command_protocol` — CCP.
* :doc:`attribute_path_semantics` — Attribute path rules.
