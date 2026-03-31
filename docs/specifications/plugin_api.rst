..
   Synarius Plugin API — minimal specification (v0.1).

================================================================================
Plugin API (minimal v0.1)
================================================================================

:Status: Draft (specification + reference host implementation in ``synarius_core.plugins``)
:Version: 0.1

--------------------------------------------------------------------------------
Purpose
--------------------------------------------------------------------------------

This document defines the **minimal Synarius Plugin API (v0.1)**. Plugins are
discovered like FMF libraries: each plugin is a **folder** on disk, described by
**XML metadata**, with a **Python entry module** that exposes an entry **class**.

Plugins extend **compilation** (transforms, code generation, backends) and
**runtime** (simulation execution). They **must not** redefine FMFL model
semantics; semantics remain in FMFL. Plugins supply processing and execution
only.

--------------------------------------------------------------------------------
Layout and discovery root
--------------------------------------------------------------------------------

At application startup, Synarius scans a directory named ``Plugins/`` (exact
name; host-defined base path). Every **immediate subdirectory** is treated as
a **candidate plugin package**.

A candidate folder is a **valid plugin** if and only if:

1. It contains ``pluginDescription.xml`` at the folder root.
2. The XML declares a ``<Module>`` value (see below) and a file
   ``<Module>.py`` exists in that same folder (or an importable layout as
   specified by the host; v0.1 assumes ``<Module>.py`` alongside the XML).

The manifest plays the same role as ``libraryDescription.xml`` for FMF
libraries, but for plugins: **pluginDescription.xml**.

Optional later extensions (not required by v0.1): additional Python packages,
resources, bundled documentation.

--------------------------------------------------------------------------------
pluginDescription.xml
--------------------------------------------------------------------------------

Root element: ``<PluginDescription>``.

Required child elements:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Element
     - Meaning
   * - ``<Name>``
     - Human-readable plugin name (also used as a stable logical id where the
       host maps it).
   * - ``<Version>``
     - Plugin version string (opaque to the spec; semantic versioning
       recommended).
   * - ``<Module>``
     - Python module name **without** ``.py``: the file to load is
       ``<Module>.py`` in the plugin folder (v0.1 flat layout).
   * - ``<Class>``
     - Name of the class inside that module to import and instantiate.
   * - ``<Capabilities>``
     - Container for one or more ``<Capability>`` elements.

Each ``<Capability>`` is a non-empty string tag. Plugins are **registered by
capability** at runtime (see `Capabilities (v0.1)`_).

Example — Python backend:

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

Example — FMU-oriented plugin:

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
Autodetection procedure
--------------------------------------------------------------------------------

On startup (or explicit reload, if the host supports it):

1. Enumerate immediate subdirectories of ``Plugins/``.
2. For each subdirectory, if ``pluginDescription.xml`` is missing, **skip** (not
   an error unless the host chooses to warn).
3. Parse ``pluginDescription.xml``; validate required fields. On parse or
   validation failure, **record a diagnostic** and skip that folder.
4. Resolve ``<Module>`` and ``<Class>``: load the Python module from the plugin
   directory (host must ensure each plugin folder is on ``sys.path`` or
   equivalent **in isolation**, so that two plugins can both use logical module
   names without colliding — see `Implementation notes`_).
5. Instantiate the class (constructor signature is host-defined for v0.1; a
   parameterless constructor is recommended for portability).
6. Register the instance under each declared **capability** (and optionally
   under the plugin ``Name`` for debugging).

Duplicate capability registration (two plugins declaring the same capability)
is **host policy** (first wins, last wins, or fail-fast); v0.1 recommends
**deterministic ordering** (e.g. folder name sort) and **first wins** with a
warning in ``diagnostics``.

--------------------------------------------------------------------------------
Plugin roles (minimal Python contracts)
--------------------------------------------------------------------------------

v0.1 defines two **conceptual** roles. A single plugin class may implement one
or both sides if the host merges interfaces; the spec only requires **clear**
method names so hosts can dispatch.

Compiler pass
~~~~~~~~~~~~~

For: loading FMFL, transforms, Python code generation, FMU code generation or
binding.

Contract (informative):

.. code-block:: python

   class CompilerPass:
       name: str
       stage: str

       def run(self, ctx):
           return ctx

* ``stage`` is an opaque string used by the host to **order** passes within a
  pipeline (e.g. ``parse``, ``lower``, ``codegen``).
* ``run`` must return ``ctx`` (possibly mutated) or raise; hosts define error
  propagation.

Runtime plugin
~~~~~~~~~~~~~~

For: emulation, FMU execution via a Python library, or similar stepping
execution.

Contract (informative):

.. code-block:: python

   class RuntimePlugin:
       name: str

       def init(self, ctx):
           pass

       def step(self, ctx):
           pass

Hosts may call ``init`` once before a run loop and ``step`` once per logical
step (or define a different schedule; document any deviation in host docs).

--------------------------------------------------------------------------------
Shared context
--------------------------------------------------------------------------------

A single **context** object is passed through compiler and runtime hooks. v0.1
requires the following **logical** attributes (concrete type is host-defined):

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Attribute
     - Role
   * - ``model``
     - Current model or IR the pipeline operates on (read/ write per stage
       policy).
   * - ``artifacts``
     - Build outputs (paths, blobs, intermediate trees).
   * - ``options``
     - Key/value options from the user or host.
   * - ``diagnostics``
     - Structured messages (errors, warnings) append-only for a run.

--------------------------------------------------------------------------------
Capabilities (v0.1)
--------------------------------------------------------------------------------

Registration is **capability-based**. For the current scope, the following
capability strings are **reserved** (meaning is host-defined but names are
stable):

* ``backend:python`` — Python-oriented backend / codegen.
* ``backend:fmu`` — FMU-oriented backend / binding.
* ``runtime:emulation`` — Emulation-style runtime.
* ``runtime:fmu`` — FMU execution runtime.

Optional additional tags (may be used when hosts are ready):

* ``frontend:fmfl``
* ``transform:basic``
* ``compile:post-dataflow`` — informative tag for passes that run after the core dataflow compile step (host may still use ``stage`` on pass objects; see ``PluginRegistry.iter_compile_passes``).

Unknown capabilities should be **ignored** or logged without breaking load of
other plugins.

--------------------------------------------------------------------------------
Design rules (normative)
--------------------------------------------------------------------------------

1. **No FMFL semantics in plugins.** Plugins must not introduce new core model
   element types or change the meaning of FMFL constructs; they operate on
   artifacts, generated code, or runtime state as defined by the host.
2. **XML for metadata, Python for behavior.** All machine-readable plugin
   identity and capability declaration lives in ``pluginDescription.xml``.
3. **Folder = one plugin.** One subdirectory under ``Plugins/`` equals one
   plugin root; no nested plugin roots in v0.1.
4. **Fail-soft per folder.** A broken plugin must not prevent loading of other
   plugins (unless the host explicitly runs in strict mode).

--------------------------------------------------------------------------------
Implementation notes
--------------------------------------------------------------------------------

* **Module path isolation:** Because ``<Module>`` is often ``my_backend`` or
  ``plugin``, hosts should import each plugin from its **directory** as a
  package root (e.g. dynamic import with a unique qualified name per folder) to
  avoid ``sys.path`` clashes between plugins.
* **Security:** Loading arbitrary ``*.py`` from disk is appropriate for
  **trusted local** installations only; distribution and signing are out of
  scope for v0.1.

--------------------------------------------------------------------------------
Relation to FMF libraries
--------------------------------------------------------------------------------

FMF libraries use ``libraryDescription.xml`` and a parallel folder layout under
``Lib/`` (see :doc:`library_catalog`). Plugins use ``pluginDescription.xml`` and
``Plugins/``. The two mechanisms are **orthogonal**: libraries describe reusable
FMF elements; plugins describe **executable extensions** to the Synarius tool
chain and runtime.
