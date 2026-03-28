..
   FMF & FMFL v0.1 — one-page normative summaries.

================================================================================
Normative summaries (v0.1)
================================================================================

:Status: Draft v0.1

Short normative checklists for implementers. For full rules, see :doc:`fmf_v0_1` and :doc:`fmfl_v0_1`.

FMF v0.1 (concise)
--------------------

* A **library** is a directory containing ``libraryDescription.xml`` with ``fmfVersion="0.1"``, ``name``, ``version``, and an ``elements`` list referencing each ``elementDescription.xml``.
* Default layout: ``components/<ElementId>/elementDescription.xml``, optional ``behavior/*.fmfl``, optional triple SVG icons ``resources/icons/<stem>_16.svg``, ``_32``, ``_64``.
* **Preferred icon:** when only one file is used, **``*_16.svg``**; standard library (``std``) arithmetic **SHALL** use that preference.
* **Host references:** ``<LibName>.<ElementId>``; library ``name`` **std** **MAY** be omitted (``Add`` ≡ ``std.Add``). Reserved name ``std``; see :doc:`fmf_v0_1`, C.1.1.
* **Behavior:** ``<Behavior>`` **SHALL** contain ``<FMFL file="..."/>`` (optional ``profile``); legacy ``<Source fmfl="..."/>`` is deprecated.
* Each **element** declares ``id``, ``name``, ``Ports`` (in/out), optional ``Parameters``, **Behavior** → FMFL, optional ``Graphics`` (``icon16`` / ``icon32`` / ``icon64``; list ``icon16`` first).

FMFL v0.1 (concise)
--------------------

* **Phases:** **init** (once, initial values, **no side effects** in v0.1) and **equations** (each step, **pure**).
* Textual IR: ``fmfl 0.1``, Python-like ``init:`` / ``equations:`` indented suites — **not** ``run:`` (non-conforming; optional legacy alias).
* **Determinism:** order = source order; unread numerics = **0**; algebraic loops **allowed** (author responsibility).
* **Names:** input ports, output ports, **local** temporaries, **parameters** (constant); **state** reserved for v0.2+.
* **Types:** semantic **Real**, **Int**, **Bool** in the model; concrete storage via **type / target profiles** at codegen.
* Standard library **SHALL** include **Add**, **Sub**, **Mul**, **Div** (see :doc:`fmfl_v0_1`, section E).
