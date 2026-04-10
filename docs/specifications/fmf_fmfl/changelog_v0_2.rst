..
   FMF/FMFL — changelog and compatibility (v0.2 vs v0.1).

================================================================================
Changelog: specification v0.2 (addendum)
================================================================================

:Status: Draft v0.2

This document records **what specification v0.2 adds or clarifies** relative to the **v0.1 baseline** documents :doc:`fmf_v0_1` and :doc:`fmfl_v0_1`. Unless stated here as **superseded**, the v0.1 normative text remains in force for packaging and language details **except** where :doc:`execution_semantics_v0_2` **refines** evaluation order and cycle handling (see M.1.1).

--------------------------------------------------------------------------------
M.1 What v0.2 clarifies (normative intent)
--------------------------------------------------------------------------------

* **FMF** remains **XML-normative** for library manifests and ``elementDescription.xml`` (no change to file layout rules in v0.1).
* **FMFL** is explicitly **not** XML: it is the **textual**, line-oriented **behavioral IR** used between **graph lowering** and **target-language** generation (see :doc:`architecture_and_pipeline_v0_2`).
* **Two-stage codegen** is **normatively recommended**: **(1)** graph → FMFL, **(2)** FMFL → target code with profiles. v0.1 already described “model graph → FMFL → target”; v0.2 **assigns** the **prototype XML-IR role** to **FMFL** instead of a separate behavioral XML layer.
* **Identity:** FMF XML **SHALL NOT** be treated as an alternate encoding of FMFL semantics; behavioral meaning for codegen is carried in **FMFL** (files referenced from FMF or produced by a host from the graph).
* **Execution semantics core** — :doc:`execution_semantics_v0_2` introduces **[NORMATIVE]** rules for: canonical cycle (trigger / evaluation / commit); execution modes (**periodic**, **interrupt**, **free_running**; **scheduled** **[RESERVED]**); dependency-based evaluation order; cycle detection/classification vs **[IMPLEMENTATION-DEFINED]** resolution; state commit discipline; determinism; minimal numeric **float** shapes (rank 0–2); and **[OUT-OF-SCOPE]** runtime/experiment concerns.
* **Graphical vs logical identity** — §4 clarifies that **evaluation** uses a **logical** dependency graph **after** lowering; **graphical** instance IDs / UUIDs **SHALL NOT** alone imply **distinct** logical variables; **multiple** graphical occurrences **MAY** map to shared FMFL names **when** the host defines that mapping.
* **Delayed cyclic feedback** — §5 ties **discrete-time** **commit** semantics to **feedback** behavior: **inputs** closing a **delayed** cycle **read** **committed** values from the **previous** step; **outputs** apply after **commit** (aligned with embedded / fixed-step practice).
* **Synarius Core pipeline note** — :doc:`architecture_and_pipeline_v0_2`, §J.1, records (informative) that the current **scalar dataflow** path is **acyclic**-oriented and **compile-time** cycle rejection unless extended by future work.

--------------------------------------------------------------------------------
M.1.0 Execution semantics — sharpened clauses (same v0.2 document)
--------------------------------------------------------------------------------

* **Logical vs physical time** — **Periodic** steps advance **logical time** by the declared step **[NORMATIVE]**; **mapping** logical time to physical time is **[OUT-OF-SCOPE]** (no normative “host policy” exception for logical progression).
* **Cycle classification** — **SHALL** distinguish **acyclic** vs **cyclic** dependencies; further classes (e.g. algebraic vs delayed) are **[IMPLEMENTATION-DEFINED]**.
* **Defaults** — v0.1 “unread numerics read as zero” is **provisional** compatibility; future specifications **MAY** deprecate implicit defaulting (:doc:`execution_semantics_v0_2`, §8).
* **scheduled** mode — **Use SHALL NOT** constitute **conformance** to **v0.2** **execution semantics** (mode remains **[RESERVED]**).
* **free_running** — **Number** and **timing** of steps are **not specified by the model** **[NORMATIVE]**.

--------------------------------------------------------------------------------
M.1.1 Refinements vs v0.1 (evaluation order) **[NORMATIVE]**
--------------------------------------------------------------------------------

* :doc:`fmfl_v0_1`, D.3, ties observable order to **textual** order in the FMFL file.
* **v0.2** **[NORMATIVE]:** where a **dependency graph** is explicit, **acyclic** evaluation order **SHALL** follow a **topological** order consistent with that graph; FMFL textual order **SHALL** be **consistent** with dependencies; conflicts **SHALL** be **rejected** or **corrected**. See :doc:`execution_semantics_v0_2`, §4.

--------------------------------------------------------------------------------
M.2 What remains unchanged from v0.1 (baseline)
--------------------------------------------------------------------------------

* ``libraryDescription.xml`` structure, ``fmfVersion="0.1"`` usage in existing libraries (:doc:`fmf_v0_1`).
* FMFL **init** / **equations** phases, **purity** intent, semantic types at **interface** level, and standard library surface (:doc:`fmfl_v0_1`) — **refined** only where :doc:`execution_semantics_v0_2` explicitly adds rules (e.g. §9 numeric core uses **float** for **evaluation** with **[IMPLEMENTATION-DEFINED]** mapping from **Real** / **Int** / **Bool**).
* Behavior reference: ``<Behavior><FMFL file="..."/></Behavior>`` in ``elementDescription.xml``.

--------------------------------------------------------------------------------
M.3 Versioning and compatibility (informative)
--------------------------------------------------------------------------------

* **Existing v0.1 libraries** remain **valid** at the **file** level; processors implementing v0.2 **SHOULD** apply :doc:`execution_semantics_v0_2` when interpreting **execution** behavior.
* Processors **MAY** advertise support for **“FMF/FMFL specification v0.2”** when they implement :doc:`architecture_and_pipeline_v0_2`, :doc:`execution_semantics_v0_2`, and this changelog; that **SHOULD NOT** require changing ``fmfVersion`` or the FMFL header line until a future normative revision explicitly bumps those fields.
* When a future release introduces **``fmfVersion="0.2"``** or **``fmfl 0.2``** file headers, this document **SHOULD** be updated with migration rules; v0.2 as **documentation** does not by itself mandate a numeric version bump in XML.

--------------------------------------------------------------------------------
M.4 Supersedes (partial, by reference)
--------------------------------------------------------------------------------

* **Evaluation order** on **acyclic** models: **superseded in part** by :doc:`execution_semantics_v0_2`, §4, as described in **M.1.1** (dependency graph takes precedence where explicit).

No other paragraph in :doc:`fmf_v0_1` or :doc:`fmfl_v0_1` is fully void; v0.2 is an **addendum** with **targeted** refinements.
