..
   FMF v0.1 — Functional Model Format (normative packaging and element XML).

================================================================================
FMF v0.1 specification
================================================================================

:Status: Draft v0.1

This document specifies the *Functional Model Format* (FMF): library discovery, folder layout, and ``elementDescription.xml``. For scope and principles, see :doc:`index`. For behavior IR, see :doc:`fmfl_v0_1`. For one-page normative summaries, see :doc:`normative_summaries_v0_1`.

--------------------------------------------------------------------------------
C. FMF v0.1 specification
--------------------------------------------------------------------------------

C.1 Library concept
~~~~~~~~~~~~~~~~~~~

A **library** is a filesystem directory that contains a file named ``libraryDescription.xml`` at its root. No other file is required to *mark* the directory; processors **SHALL** treat the presence of ``libraryDescription.xml`` as the library root.

**Purpose of ``libraryDescription.xml``**

* Declare library identity, versioning, and human-readable description.
* Enumerate or point to contained elements (v0.1: **SHALL** list each element via an ``<Element>`` entry with a relative path to ``elementDescription.xml``).
* Carry optional metadata and **future-facing** hooks (capabilities, execution profile hints, runtime contributions) as optional XML sections for forward compatibility.

**Required fields (normative)**

Inside ``libraryDescription.xml``, the root element **SHALL** be ``<LibraryDescription>`` with attributes:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Attribute / child
     - Meaning
   * - ``fmfVersion``
     - **Required.** Format version; v0.1 uses literal ``0.1``.
   * - ``name``
     - **Required.** Short library name (token, no spaces).
   * - ``version``
     - **Required.** Semantic version string of the library (e.g. ``1.0.0``).
   * - ``elements``
     - **Required.** Container for one or more ``<Element>`` children.

Each ``<Element>`` **SHALL** provide:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Attribute
     - Meaning
   * - ``id``
     - Unique element identifier within the library (token).
   * - ``path``
     - Relative path from library root to ``elementDescription.xml``.

**Optional fields (normative names, informative use in v0.1)**

* ``<Description>`` — human-readable text.
* ``<Vendor>`` — string.
* ``<Metadata>`` — key/value pairs for tooling (implementation-defined interpretation).
* ``<Capabilities>`` — optional list of capability tokens (e.g. ``pure_function``, ``side_effect_free``) for future policy.
* ``<ExecutionProfiles>`` — optional hints such as ``hosted_python``, ``emulation``, ``live`` (see :ref:`fmf-fmfl-runtime-concept` in :doc:`index`).
* ``<RuntimeContributions>`` — optional declarative hooks (e.g. initializer module id) reserved for future runtime loaders.

C.1.1 Library and element references (normative for Synarius hosts)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hosts that bind model elements to FMF library definitions (for example a **New** / insert-element operator, palette entries, or code generation) **SHALL** use the following reference convention.

**Qualified form**

* A reference **SHALL** be either ``<LibName>.<ElementId>`` (exactly one unescaped ``.`` separating two tokens) or, under the rules below, an **unqualified** ``<ElementId>``.
* ``<LibName>`` **SHALL** equal the ``name`` attribute of the root ``<LibraryDescription>`` for that library (same token rules as ``name``: short identifier, no spaces).
* ``<ElementId>`` **SHALL** equal the element’s ``id`` (as in ``<Element id="…"/>`` and in ``elementDescription.xml``).

**Standard library name**

* The Synarius-bundled standard library (elementary real arithmetic and related elements, see :doc:`fmfl_v0_1`, section E) **SHALL** use ``name="std"`` in ``libraryDescription.xml``.
* Other libraries **SHALL NOT** use ``std`` as their ``name`` (reserved).

**Unqualified references**

* Only for the library whose ``name`` is ``std``, hosts **MAY** accept a reference consisting of ``<ElementId>`` alone, which **SHALL** be interpreted as ``std.<ElementId>``.
* For every other library, references **SHALL** use the qualified form ``<LibName>.<ElementId>``.

**Ambiguity**

* If an unqualified ``<ElementId>`` could denote more than one loaded element, hosts **SHALL** reject the reference or require qualification; they **SHALL NOT** silently pick a non-``std`` library.

**Element identifiers**

* Element ``id`` values **SHOULD NOT** contain ``.``, so that ``<LibName>.<ElementId>`` remains unambiguous without escape rules.

**Repository layout (informative):** Synarius Core ships this library under ``Lib/std/`` (sibling to other optional trees under ``Lib/``). The on-disk folder name **MAY** differ from ``name``; processors **SHALL** use the manifest ``name`` as ``<LibName>``.

C.2 Folder structure (normative minimal layout)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is the **default** layout processors **SHALL** support for v0.1:

.. code-block:: text

   <LibraryRoot>/
     libraryDescription.xml
     components/
       <ElementId>/
         elementDescription.xml
         behavior/
           <name>.fmfl
         resources/
           icons/
             <stem>_16.svg
             <stem>_32.svg
             <stem>_64.svg

**Rationale:** Per-element directories mirror FMI-style encapsulation and keep behavior paths stable when icons or extra resources are added.

C.3 FMF element (component) v0.1
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

An **element** is described by ``elementDescription.xml`` in ``components/<ElementId>/``.

It **SHALL** specify:

.. list-table::
   :header-rows: 1
   :widths: 18 82

   * - Concept
     - Rule
   * - Identity
     - ``id`` attribute **SHALL** match the parent folder name ``<ElementId>`` and **SHALL** be unique within the library.
   * - Display name
     - ``name`` attribute (human-readable).
   * - Ports
     - At least one ``<Port>`` with ``kind="in"`` or ``kind="out"``, ``name`` token, optional ``type`` (v0.1 default: ``real`` if omitted).
   * - Parameters
     - Optional ``<Parameters>`` with ``<Parameter>`` entries (name, default).
   * - Behavior reference
     - ``<Behavior>`` contains one or more ``<FMFL>`` children (see C.3.2).
   * - Graphics
     - Optional ``<Graphics>`` with paths relative to the element folder (see C.3.1).

C.3.1 SVG icons and nominal resolutions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When SVG icons are shipped for an element, libraries **SHOULD** provide **three** assets, each authored or simplified for a distinct nominal **pixel grid**:

.. list-table::
   :header-rows: 1
   :widths: 15 85

   * - Nominal size
     - Intent
   * - **16×16**
     - **Preferred authoring master** and default choice when a host loads only one asset (see below). Suited to dense palettes and tree rows; Synarius Studio scales this nominal grid to ~**19×19** logical pixels in compact UI so glyphs align visually with on-diagram BasicOperator icons.
   * - **32×32**
     - Optional larger browser / inspector preview when multiple assets are bundled.
   * - **64×64**
     - High-DPI or zoomed views; may carry finer detail.

**Preferred nominal size (normative guidance):** when a processor or host displays a **single** icon from an FMF triple, it **SHOULD** prefer ``*_16.svg`` unless the UI context is explicitly high-density (then ``*_32`` / ``*_64`` **MAY** be used). Libraries **SHALL** still ship all three sizes when they ship icons at all. The Synarius standard library (``name="std"``; elementary arithmetic) **SHALL** treat the **16×16** asset as canonical for palette and property previews.

**Naming convention (normative for v0.1 when multiple icons are present):** files **SHALL** live in the same directory (typically ``resources/icons/``) and **SHALL** be named::

   <stem>_16.svg
   <stem>_32.svg
   <stem>_64.svg

where ``<stem>`` is a shared prefix (e.g. element id or icon id). The ``_16`` / ``_32`` / ``_64`` suffix **SHALL** denote the **intended nominal resolution** the graphic is optimized for.

**XML binding:** ``<Graphics>`` **SHOULD** declare all three paths explicitly so hosts need not infer missing files. List ``icon16`` first to reflect the preferred default:

.. code-block:: xml

   <Graphics icon16="resources/icons/add_16.svg"
             icon32="resources/icons/add_32.svg"
             icon64="resources/icons/add_64.svg"/>

Processors **MAY** accept a legacy single-attribute form ``icon=".../add_32.svg"`` and **MAY** resolve sibling ``add_16.svg`` / ``add_64.svg`` by stem substitution; portable libraries **SHOULD NOT** rely on that.

C.3.2 Behavior: FMFL references (normative)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Inside ``elementDescription.xml``, ``<Behavior>`` **SHALL** list one or more FMFL sources using **child elements** ``<FMFL/>`` (not a loose ``src`` string on ``<Behavior>`` alone).

**Required attribute**

* ``file`` — path relative to the **element** directory (e.g. ``behavior/add.fmfl``).

**Optional attribute**

* ``profile`` — string identifying a **behavior variant** (e.g. ``default``, ``optimized``). If omitted, processors **SHALL** treat the profile as ``default``. When multiple ``<FMFL>`` entries exist, each **SHALL** have a unique ``profile`` value for that element.

**v0.1 minimal form (one file):**

.. code-block:: xml

   <Behavior>
     <FMFL file="behavior/add.fmfl"/>
   </Behavior>

**Future-facing form (multiple profiles):**

.. code-block:: xml

   <Behavior>
     <FMFL profile="default" file="behavior/add.fmfl"/>
     <FMFL profile="optimized" file="behavior/add_opt.fmfl"/>
   </Behavior>

**Legacy (deprecated):** ``<Source fmfl="..."/>`` **MAY** be accepted by processors for backward compatibility; new libraries **SHALL** use ``<FMFL file="..."/>``.

C.4 XML structures (informative examples)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*Normative rules are in C.1–C.3; the following fragments are consistent examples.*

**Example skeleton: ``libraryDescription.xml``**

.. code-block:: xml

   <?xml version="1.0" encoding="UTF-8"?>
   <LibraryDescription fmfVersion="0.1" name="std" version="1.0.0">
     <Description>Primitive arithmetic elements for Synarius (reference: std).</Description>
     <Vendor>Synarius</Vendor>
     <elements>
       <Element id="Add" path="components/Add/elementDescription.xml"/>
     </elements>
     <Capabilities>
       <Capability id="pure_function"/>
     </Capabilities>
     <ExecutionProfiles>
       <Hint id="hosted_python"/>
     </ExecutionProfiles>
     <RuntimeContributions/>
   </LibraryDescription>

**Example skeleton: ``elementDescription.xml`` (Add)**

.. code-block:: xml

   <?xml version="1.0" encoding="UTF-8"?>
   <ElementDescription id="Add" name="Add">
     <Description>Binary real addition.</Description>
     <Ports>
       <Port kind="in" name="in0" type="real"/>
       <Port kind="in" name="in1" type="real"/>
       <Port kind="out" name="out" type="real"/>
     </Ports>
     <Parameters/>
     <Behavior>
       <FMFL file="behavior/add.fmfl"/>
     </Behavior>
     <Graphics icon16="resources/icons/add_16.svg"
               icon32="resources/icons/add_32.svg"
               icon64="resources/icons/add_64.svg"/>
   </ElementDescription>
