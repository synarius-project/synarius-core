..
   Synarius Plugin API specification (v0.3, English).

================================================================================
Synarius Plugin API (v0.3)
================================================================================

:Status: Specification + reference implementation in ``synarius_core.plugins``
:Version: 0.3
:See also: :doc:`plugin_concept_v0_3`, :doc:`plugin_concept_v0_3_technical`, :doc:`library_catalog`

This document defines the **Synarius Plugin API (v0.3)**: XML manifest and discovery, **capability**
registration, and the **Python contribution model** (``SynariusPlugin``, compile passes, element-type
handlers, optional simulation runtime).

Plugins extend **compilation** (transforms, code generation, backends) and **runtime** (simulation
execution). They **must not** redefine FMFL model semantics; semantics remain in FMFL and library
descriptors.

--------------------------------------------------------------------------------
1. Layout and discovery
--------------------------------------------------------------------------------

At application startup, Synarius scans a directory named ``Plugins/`` (exact name; host-defined
base path). Every **immediate subdirectory** is a **candidate plugin package**.

A candidate folder is a **valid plugin** if and only if:

1. It contains ``pluginDescription.xml`` at the folder root.
2. The XML declares a ``<Module>`` value and a file ``<Module>.py`` exists in that same folder (or
   an importable layout as specified by the host; the reference host assumes ``<Module>.py``
   alongside the XML).

The manifest plays the same role as ``libraryDescription.xml`` for FMF libraries, but for plugins:
**pluginDescription.xml**.

Optional extensions (not required by v0.3): nested Python packages, bundled resources, extra docs.

--------------------------------------------------------------------------------
2. pluginDescription.xml
--------------------------------------------------------------------------------

Root element: ``<PluginDescription>``.

Required child elements:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Element
     - Meaning
   * - ``<Name>``
     - Human-readable plugin name (stable logical id where the host maps it). Implementations
       should keep this aligned with the plugin class’s ``name`` field when they populate it.
   * - ``<Version>``
     - Plugin version string (opaque to the spec; semantic versioning recommended).
   * - ``<Module>``
     - Python module name **without** ``.py``: the file to load is ``<Module>.py`` in the plugin
       folder (flat layout in the reference host).
   * - ``<Class>``
     - Class name inside that module to import and instantiate.
   * - ``<Capabilities>``
     - Container for one or more ``<Capability>`` elements.

Each ``<Capability>`` is a non-empty string tag. Plugins are **registered by capability** at runtime
(see :ref:`synarius-plugin-capabilities`).

**Example — Python backend**

.. code-block:: xml

   <PluginDescription>
       <Name>PythonBackend</Name>
       <Version>0.1</Version>
       <Module>my_backend</Module>
       <Class>PythonBackendPlugin</Class>
       <Capabilities>
           <Capability>backend:python</Capability>
       </Capabilities>
   </PluginDescription>

**Example — FMU-oriented plugin**

.. code-block:: xml

   <PluginDescription>
       <Name>FMURuntime</Name>
       <Version>0.1</Version>
       <Module>fmu_runtime</Module>
       <Class>FMURuntimePlugin</Class>
       <Capabilities>
           <Capability>backend:fmu</Capability>
           <Capability>runtime:fmu</Capability>
       </Capabilities>
   </PluginDescription>

--------------------------------------------------------------------------------
3. Autodetection procedure
--------------------------------------------------------------------------------

On startup (or explicit reload, if the host supports it):

1. Enumerate immediate subdirectories of ``Plugins/``.
2. For each subdirectory, if ``pluginDescription.xml`` is missing, **skip** (not an error unless the
   host chooses to warn).
3. Parse ``pluginDescription.xml``; validate required fields. On parse or validation failure,
   **record a diagnostic** and skip that folder.
4. Resolve ``<Module>`` and ``<Class>``: load the Python module from the plugin directory (the host
   must ensure each plugin folder is on ``sys.path`` or equivalent **in isolation**, so two
   plugins can reuse simple module names without colliding — see
   :ref:`synarius-plugin-implementation-notes`).
5. Instantiate the class **without arguments** (parameterless constructor is required for portable
   plugins in v0.3).
6. Register the instance under each declared **capability** (and optionally under the plugin
   ``Name`` for debugging).

Duplicate capability registration (two plugins declaring the same capability) is **host policy**
(first wins, last wins, or fail-fast). v0.3 recommends **deterministic ordering** (e.g. folder name
sort) and **first wins** with a warning in diagnostics.

--------------------------------------------------------------------------------
4. Shared compile context
--------------------------------------------------------------------------------

Compile passes receive a single :class:`~synarius_core.plugins.element_types.CompileContext`:

.. code-block:: python

   from dataclasses import dataclass, field
   from typing import Any


   @dataclass
   class CompileContext:
       model: Any
       artifacts: dict[str, Any] = field(default_factory=dict)
       options: dict[str, Any] = field(default_factory=dict)
       diagnostics: list[str] = field(default_factory=list)

``run`` mutates ``ctx`` in place; avoid mixed “sometimes return a new ctx” patterns.

--------------------------------------------------------------------------------
5. CompilerPass
--------------------------------------------------------------------------------

For: loading FMFL, transforms, Python code generation, FMU code generation or binding.

.. code-block:: python

   from abc import ABC, abstractmethod

   from synarius_core.plugins.element_types import CompileContext


   class CompilerPass(ABC):
       name: str
       stage: str

       @abstractmethod
       def run(self, ctx: CompileContext) -> None:
           ...

* ``stage`` is an opaque string the host uses to **order** passes (e.g. ``parse``, ``lower``,
  ``codegen``).
* ``run`` mutates ``ctx`` or raises; error propagation is host-defined.

--------------------------------------------------------------------------------
6. ElementTypeHandler and contexts
--------------------------------------------------------------------------------

Handlers implement ``new`` / ``inspect`` / ``sync`` for one primary ``type_key``. Optional
**aliases** allow additional keys to resolve to the same handler:

.. code-block:: python

   from abc import ABC, abstractmethod
   from dataclasses import dataclass, field
   from typing import Any, ClassVar


   @dataclass
   class NewContext:
       controller: Any
       model: Any
       options: dict[str, Any] = field(default_factory=dict)
       diagnostics: list[str] = field(default_factory=list)


   @dataclass
   class InspectContext:
       controller: Any
       model: Any
       options: dict[str, Any] = field(default_factory=dict)
       diagnostics: list[str] = field(default_factory=list)


   @dataclass
   class InspectResult:
       type_key: str
       ref: str
       attributes: dict[str, Any] = field(default_factory=dict)
       pins: list[dict[str, Any]] = field(default_factory=list)
       raw: dict[str, Any] = field(default_factory=dict)


   @dataclass
   class SyncContext:
       controller: Any
       model: Any
       artifacts: dict[str, Any] = field(default_factory=dict)
       options: dict[str, Any] = field(default_factory=dict)
       diagnostics: list[str] = field(default_factory=list)


   class ElementTypeHandler(ABC):
       type_key: str
       handler_aliases: ClassVar[tuple[str, ...]] = ()

       @abstractmethod
       def new(
           self,
           ctx: NewContext,
           ref: str,
           args: list[Any],
           kwargs: dict[str, Any],
       ) -> Any:
           """Create a model object; caller attaches it to the model."""

       def inspect(self, ctx: InspectContext, ref: str) -> InspectResult:
           raise NotImplementedError(
               f"{type(self).__name__} does not implement inspect"
           )

       def sync(self, ctx: SyncContext, ref: str) -> None:
           """Default: no-op when there is no external resource."""

``kwargs`` may carry keywords such as ``resource_path`` (see :doc:`plugin_concept_v0_3_technical`).

**Pin descriptors** in :class:`InspectResult` are currently ``list[dict[str, Any]]`` (keys such as
``name``, ``direction``, ``kind``, ``metadata``). A dedicated typed schema is **[FUTURE WORK]**.

--------------------------------------------------------------------------------
7. SimulationRuntimePlugin
--------------------------------------------------------------------------------

For stepping execution (e.g. ``runtime:fmu``). The engine adapts the live simulation context to
the shape expected here.

.. code-block:: python

   from abc import ABC, abstractmethod
   from dataclasses import dataclass
   from typing import Any
   from uuid import UUID


   @dataclass
   class SimContext:
       artifacts: dict[str, Any]
       scalar_workspace: dict[Any, float]
       options: dict[str, Any]
       diagnostics: list[str]
       time_s: float = 0.0


   class SimulationRuntimePlugin(ABC):
       runtime_capability: str

       @abstractmethod
       def runtime_init(self, ctx: SimContext) -> None: ...

       @abstractmethod
       def runtime_step(self, ctx: SimContext, node_id: UUID) -> None: ...

       @abstractmethod
       def runtime_shutdown(self, ctx: SimContext) -> None: ...

       def runtime_reset(self, ctx: SimContext) -> None:
           self.runtime_shutdown(ctx)
           self.runtime_init(ctx)

Mapping nodes to runtime instances **[PROVISIONAL]** is host-defined.

--------------------------------------------------------------------------------
8. SynariusPlugin — contribution provider
--------------------------------------------------------------------------------

The host instantiates this class **without arguments** and queries contributions:

.. code-block:: python

   from abc import ABC

   from synarius_core.plugins.element_types import (
       CompilerPass,
       ElementTypeHandler,
       SimulationRuntimePlugin,
   )


   class SynariusPlugin(ABC):
       name: str = ""

       def compile_passes(self) -> list[CompilerPass]:
           return []

       def element_type_handlers(self) -> list[ElementTypeHandler]:
           return []

       def simulation_runtime(self) -> SimulationRuntimePlugin | None:
           return None

Lifecycle (conceptual):

#. Read ``pluginDescription.xml``.
#. Import the class named ``<Class>`` from module ``<Module>`` and instantiate it.
#. Call ``compile_passes()``, ``element_type_handlers()``, and ``simulation_runtime()``; register
   each handler under its ``type_key`` (and aliases) in ``ElementTypeRegistry``.

End users do **not** call a separate ``register_handlers`` API; the registry consumes the lists
returned above (an implementation may still factor a private helper).

.. _synarius-plugin-capabilities:

--------------------------------------------------------------------------------
9. Capabilities
--------------------------------------------------------------------------------

Registration is **capability-based**. Reserved strings (names are stable; semantics are
host-defined within these buckets):

* ``backend:python`` — Python-oriented backend / codegen.
* ``backend:fmu`` — FMU-oriented backend / binding.
* ``runtime:emulation`` — Emulation-style runtime.
* ``runtime:fmu`` — FMU execution runtime.

Optional additional tags (when hosts are ready):

* ``frontend:fmfl``
* ``transform:basic``
* ``compile:post-dataflow`` — passes that run after the core dataflow compile step (hosts may still
  use ``stage`` on ``CompilerPass`` objects; see ``PluginRegistry.iter_compile_passes``).

Unknown capabilities should be **ignored** or logged without breaking other plugins.

--------------------------------------------------------------------------------
10. Contributions vs. capabilities
--------------------------------------------------------------------------------

* **Capabilities** (XML): advertise what the plugin offers; used for lookup and filtering.
* **Contributions** (Python): concrete extension points the core invokes — ``CompilerPass``,
  ``ElementTypeHandler``, ``SimulationRuntimePlugin``.

Example mapping (illustrative):

* ``runtime:fmu`` → ``SimulationRuntimePlugin``
* ``backend:python`` → ``CompilerPass`` (e.g. ``stage="codegen"``)

--------------------------------------------------------------------------------
11. Diagnostics [PROVISIONAL]
--------------------------------------------------------------------------------

Contexts carry ``diagnostics: list[str]`` today. Structured objects (severity, location) are
**[FUTURE WORK]**.

--------------------------------------------------------------------------------
12. Design rules [NORMATIVE]
--------------------------------------------------------------------------------

1. **No FMFL semantics in plugins.** Plugins must not introduce new core model element types or
   change the meaning of FMFL constructs; they operate on artifacts, generated code, or runtime
   state as defined by the host.
2. **XML for metadata, Python for behavior.** Identity and capability declaration live in
   ``pluginDescription.xml``.
3. **Folder = one plugin.** One subdirectory under ``Plugins/`` equals one plugin root; no nested
   plugin roots in v0.3.
4. **Fail-soft per folder.** A broken plugin must not prevent loading of other plugins (unless the
   host runs in strict mode).

.. _synarius-plugin-implementation-notes:

--------------------------------------------------------------------------------
13. Implementation notes
--------------------------------------------------------------------------------

* **Module path isolation:** Because ``<Module>`` is often a short name, hosts should import each
  plugin from its **directory** as a package root (dynamic import with a unique qualified name per
  folder) to avoid ``sys.path`` clashes.
* **Security:** Loading arbitrary ``*.py`` from disk is appropriate for **trusted local**
  installations only; signing and distribution are out of scope for v0.3.

--------------------------------------------------------------------------------
14. Relation to FMF libraries
--------------------------------------------------------------------------------

FMF libraries use ``libraryDescription.xml`` under ``Lib/`` (see :doc:`library_catalog`). Plugins
use ``pluginDescription.xml`` under ``Plugins/``. The mechanisms are **orthogonal**: libraries
describe reusable FMF elements; plugins describe **executable extensions** to the Synarius toolchain
and runtime. Architectural boundaries are summarized in :doc:`plugin_concept_v0_3_technical`.
