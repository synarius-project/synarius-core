..
   FMF library catalog and console tree (@libraries).

================================================================================
Library catalog (FMF discovery and console tree)
================================================================================

:Status: Draft (synarius-core)

--------------------------------------------------------------------------------
Purpose
--------------------------------------------------------------------------------

``synarius_core.library.LibraryCatalog`` loads every FMF library found on disk at **host startup** (when a ``SynariusController`` is constructed). Parsed metadata is exposed through a **generic navigation tree** that uses the same console commands as the simulation model: ``ls``, ``cd``, ``lsattr``.

This is separate from the ``Model`` aggregate: library nodes are **read-only** descriptors, not instantiable model objects.

--------------------------------------------------------------------------------
Discovery
--------------------------------------------------------------------------------

* The bundled standard library directory (see ``standard_library_root()``) is always scanned when present.
* Additionally, every immediate subdirectory of ``Lib/`` next to the ``synarius-core`` project root that contains ``libraryDescription.xml`` is loaded.
* Optional extra roots may be passed to ``LibraryCatalog(extra_roots=[...])``.

Duplicate filesystem paths are ignored. Duplicate **manifest** ``name`` attributes: the first wins; later libraries with the same ``name`` are skipped and recorded in ``catalog.load_errors``.

--------------------------------------------------------------------------------
Console integration
--------------------------------------------------------------------------------

* Alias root ``@libraries`` points to the catalog’s synthetic root (``LIB.CATALOG_ROOT``).
* Each loaded manifest becomes a child node (``LIB.LIBRARY``); segment name = manifest ``name`` (e.g. ``std``).
* Each ``<Element>`` entry becomes a child (``LIB.ELEMENT``); segment name = element ``id`` (e.g. ``Add``).
* Example path: ``@libraries/std/Add``.

``new`` and other model-mutating commands require the current working directory to be a ``ComplexInstance`` under the model (e.g. ``@main``), not under ``@libraries``.

--------------------------------------------------------------------------------
Types
--------------------------------------------------------------------------------

Library tree nodes expose a read-only ``type`` string in ``attribute_dict``:

* ``LIB.CATALOG_ROOT`` — root listing libraries
* ``LIB.LIBRARY`` — one ``libraryDescription.xml`` tree
* ``LIB.ELEMENT`` — one ``elementDescription.xml`` entry

These are distinct from core model ``MODEL.*`` types (see :doc:`core_type_system`).
