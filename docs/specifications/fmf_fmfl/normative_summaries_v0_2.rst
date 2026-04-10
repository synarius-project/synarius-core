..
   FMF/FMFL v0.2 — one-page normative summaries (addendum).

================================================================================
Normative summaries (v0.2 addendum)
================================================================================

:Status: Draft v0.2

Checklists for **v0.2** rules. Full normative text: :doc:`architecture_and_pipeline_v0_2`, :doc:`execution_semantics_v0_2`, :doc:`changelog_v0_2`. **v0.1 baseline:** :doc:`normative_summaries_v0_1`, :doc:`fmf_v0_1`, :doc:`fmfl_v0_1`.

Labels: **[NORMATIVE]**, **[IMPLEMENTATION-DEFINED]**, **[TOOL-DEFINED]**, **[RESERVED]**, **[OUT-OF-SCOPE]** — see §0 in :doc:`execution_semantics_v0_2`.

FMF / FMFL roles
----------------

* **[NORMATIVE]** **FMF** = XML for structure; **FMFL** = textual behavioral IR (not XML).
* **[NORMATIVE]** Graph lowering → **FMFL** → target code (two stages); see :doc:`architecture_and_pipeline_v0_2`.

Model vs runtime
----------------

* **[NORMATIVE]** FMF/FMFL define **product system** behavior (logical semantics).
* **[OUT-OF-SCOPE]** Experimentation, pacing (real-time vs accelerated), mapping logical time to physical time, solver choice, debug/profiling — :doc:`execution_semantics_v0_2`, §1.

Canonical cycle **[NORMATIVE]**
--------------------------------

* **trigger** → **evaluation** (read committed state; side-effect-free w.r.t. commit) → **state update (commit)** (atomic).

Execution modes **[NORMATIVE]** / **[RESERVED]**
------------------------------------------------

* **periodic** — step size + time unit (binding **[IMPLEMENTATION-DEFINED]**); each step advances **logical time** by that step **[NORMATIVE]**; logical→physical time **[OUT-OF-SCOPE]**.
* **interrupt** — externally triggered.
* **free_running** — no normative fixed step size; **number** and **timing** of steps **not specified by the model**.
* **scheduled** — **[RESERVED]**; **MUST NOT** claim full semantics in v0.2; **use does not constitute** v0.2 **execution-semantics conformance**.

Evaluation order **[NORMATIVE]** / **[TOOL-DEFINED]**
------------------------------------------------------

* **[NORMATIVE]** Order **SHALL** follow **dependency graph**; acyclic → topological order.
* **[NORMATIVE]** The dependency graph is **logical** after lowering; **graphical** IDs (UUIDs, canvas instances) **SHALL NOT** alone determine distinct logical variables; **multiple** graphical elements **MAY** map to one logical signal **when** lowering defines that.
* **[NORMATIVE]** FMF **MAY** set explicit priority; **MUST NOT** violate dependencies; else reject/correct.
* **[TOOL-DEFINED]** Editor/canvas layout **MUST NOT** define semantics.

Cycles **[NORMATIVE]** / **[IMPLEMENTATION-DEFINED]**
-------------------------------------------------------

* **[NORMATIVE]** Detection **required**; classification **SHALL** distinguish **acyclic** vs **cyclic**; **MUST NOT** be silent.
* **[NORMATIVE]** **Delayed** feedback in discrete-time commit semantics: **old** at cycle **input** (read prior commit), **new** after **commit** for the **next** step — see :doc:`execution_semantics_v0_2`, §5.
* **[IMPLEMENTATION-DEFINED]** Further cycle classes (e.g. algebraic vs delayed) **MAY** be documented per backend.
* **[IMPLEMENTATION-DEFINED]** Resolution strategy **MUST** be **documented**; backends **MAY** differ **if** exposed (warnings/metadata).

State & determinism
-------------------

* **[NORMATIVE]** Committed state read → evaluate → atomic commit; no mid-evaluation commit.
* **[NORMATIVE]** Same model + backend + input sequence → deterministic committed-state sequence (given fixed numeric behavior).
* **[IMPLEMENTATION-DEFINED]** Float vs quantized etc.; **MUST** be documented.
* **[NORMATIVE]** Acyclic models **SHOULD** have backend-independent order.

Defaults & numerics (minimal)
-----------------------------

* **[IMPLEMENTATION-DEFINED]** Full defaulting rules for unassigned names — **MUST** be documented (v0.1 “zero” is **provisional** compatibility only; future specs **MAY** deprecate implicit defaulting).
* **[NORMATIVE]** Numeric **evaluation** values **SHALL** be **float**; shapes rank 0, 1, 2 only; interpolation **[OUT-OF-SCOPE]** (v0.2).
