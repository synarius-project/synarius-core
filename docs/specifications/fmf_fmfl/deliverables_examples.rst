..
   FMF & FMFL v0.1 — on-disk example library (Add) wired via literalinclude.

================================================================================
Deliverables: complete examples
================================================================================

Sample **std** library layout (Add-only minimal tree; ``name="std"`` per :doc:`fmf_v0_1`, C.1.1). Files live under ``docs/specifications/examples/std/`` for tooling and tests. Icons match Studio BasicOperator styling; **``add_16.svg``** is the preferred single-resolution asset (see :doc:`fmf_v0_1`, C.3.1). Regenerate with ``python scripts/generate_operator_library_svgs.py`` in ``synarius-core``.

**Sample library folder structure**

.. code-block:: text

   std/
     libraryDescription.xml
     components/
       Add/
         elementDescription.xml
         behavior/
           add.fmfl
         resources/
           icons/
             add_16.svg
             add_32.svg
             add_64.svg

**Full sample ``libraryDescription.xml``**

.. literalinclude:: ../examples/std/libraryDescription.xml
   :language: xml

**Full sample ``elementDescription.xml`` for Add**

.. literalinclude:: ../examples/std/components/Add/elementDescription.xml
   :language: xml

**Full sample FMFL for Add**

.. literalinclude:: ../examples/std/components/Add/behavior/add.fmfl
   :language: text
