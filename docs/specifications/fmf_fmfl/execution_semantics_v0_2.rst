..
   FMF/FMFL v0.2 — execution semantics core (canonical cycle, modes, order, cycles, state, determinism).

================================================================================
Execution semantics core (v0.2)
================================================================================

:Status: Draft v0.2
:Audience: Implementers of Synarius Core, compilers, backends, and verification tools

This document defines the **minimal canonical execution semantics** for FMF/FMFL **v0.2**. It **refines** evaluation order and cycle handling relative to the **v0.1 baseline** (:doc:`fmfl_v0_1`, especially D.3) where this document is **more specific**; see :doc:`changelog_v0_2`.

**Relationship to :doc:`fmf_v0_1` and :doc:`fmfl_v0_1`:** Packaging, FMFL concrete syntax, ``init`` / ``equations`` phases, and port typing remain in the v0.1 baseline unless this document **explicitly** supersedes a rule. **Runtime/experiment** behavior (pacing, solvers, debug) is **[OUT-OF-SCOPE]** here.

--------------------------------------------------------------------------------
0. Status labels (conventions)
--------------------------------------------------------------------------------

Throughout this document, bracketed labels classify requirements:

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Label
     - Meaning
   * - **[NORMATIVE]**
     - Required for conformance to this specification.
   * - **[IMPLEMENTATION-DEFINED]**
     - Behavior is fixed by the implementation but **MUST** be **documented** (see §6, §9).
   * - **[TOOL-DEFINED]**
     - Behavior of tools (e.g. editors) without semantic force; **MUST NOT** alter core model meaning.
   * - **[RESERVED]**
     - Syntax or mode names may appear; **full semantics are not** defined in v0.2.
   * - **[OUT-OF-SCOPE]**
     - Not specified here; may be specified by hosts, experiments, or future spec versions.

--------------------------------------------------------------------------------
1. Logical model vs runtime / experiment **[OUT-OF-SCOPE]**
--------------------------------------------------------------------------------

**[NORMATIVE]** FMF and FMFL **SHALL** describe **product system behavior**: structure, dataflow, equations, and the **logical** execution semantics in §2–§8.

**[OUT-OF-SCOPE]** for this specification:

* Real-time vs accelerated vs maximum-speed execution.
* Solver selection, numerical integration method, tolerance heuristics.
* Debug modes, profiling, tracing, logging policy.
* Experiment configuration, test harnesses, replay of recordings.
* Host scheduling policy beyond the **execution modes** named in §3 (as abstract triggers only).

**Logical time progression** is **defined by the model** (§2–§3). **Mapping** of **logical time** to **physical** (wall-clock or real-time) **time** is **[OUT-OF-SCOPE]** here; hosts **MAY** perform such mapping, but it is not specified by FMF/FMFL v0.2.

--------------------------------------------------------------------------------
2. Canonical execution cycle **[NORMATIVE]**
--------------------------------------------------------------------------------

**[NORMATIVE]** Every FMFL model **SHALL** be reducible to the following **logical** cycle for each **step** (or each **trigger** in interrupt-driven execution):

1. **Trigger** — An execution mode (§3) requests a step.
2. **Evaluation** — Read **committed** state (§7); compute outputs and candidate next state using **side-effect-free** evaluation (§7).
3. **State update (commit)** — **Atomically** commit the new state after evaluation completes (§7).

**[NORMATIVE]** Side effects on **committed** state **MUST NOT** occur during **evaluation**; commits **MUST** occur only after evaluation of the step completes.

--------------------------------------------------------------------------------
3. Execution modes **[NORMATIVE]** / **[RESERVED]**
--------------------------------------------------------------------------------

**[NORMATIVE]** The following **logical** execution modes **SHALL** be distinguishable:

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Mode
     - Semantics
   * - **periodic**
     - **SHALL** be associated with a **step size** and a **time unit** (declared in the model or host binding; binding details **[IMPLEMENTATION-DEFINED]**). Each **periodic** step **SHALL** advance **logical time** by exactly that step size **[NORMATIVE]**; **logical time** is **defined by the model**, not by host policy. **Mapping** of **logical time** to **physical time** is **[OUT-OF-SCOPE]** (see §1).
   * - **interrupt**
     - **SHALL** be driven by **external** triggers; no fixed step size **SHALL** be required by this mode.
   * - **free_running**
     - **SHALL** execute **without** a normative fixed step size in this specification; pacing is **[OUT-OF-SCOPE]**. The **number** and **timing** of steps in **free_running** mode are **not specified by the model** **[NORMATIVE]**.
   * - **scheduled**
     - **[RESERVED]**. Mode name and optional schedule **expression** (e.g. cron-like) **MAY** appear; **full semantics MUST NOT** be defined in v0.2. Implementations **MUST NOT** claim full **scheduled** conformance until a future specification defines it. **Use** of **scheduled** mode **SHALL NOT** constitute **conformance** to **v0.2** **execution semantics** (the mode is not normatively defined here) **[NORMATIVE]**.

**[OUT-OF-SCOPE]** Real-time pacing vs as-fast-as-possible execution for any mode.

--------------------------------------------------------------------------------
4. Evaluation order **[NORMATIVE]**
--------------------------------------------------------------------------------

**[NORMATIVE]** Evaluation order **SHALL** be **derived from the dependency graph** implied by the model (ports, assignments, and dataflow), not from canvas or editor **layout**.

**[NORMATIVE]** That dependency graph is a graph of **logical** data dependencies **after** any host lowering from a **graphical** model to FMFL (or equivalent). **Graphical** element identifiers (e.g. canvas instance IDs, UUIDs in packaging metadata, or host-specific handles) **identify** **graphical** or **structural** occurrences; they **SHALL NOT** by themselves define **distinctness** of **logical** variables. **Multiple** graphical occurrences **MAY** map to the **same** logical name, port bundle, or merged wire in the lowered IR **when** the host’s mapping rules say so.

**[NORMATIVE]** **Acyclic** dependency graphs **SHALL** be evaluated in a **topological order** consistent with all edges.

**[NORMATIVE]** **Cycles** **MUST** be **detected** and **classified** (§5). **Silent** ignoring of cycles **MUST NOT** occur.

**[NORMATIVE]** FMF **MAY** declare an **explicit evaluation priority** among equations or instances. Such priority **SHALL** be treated as a **user override** of default ordering. It **MUST NOT** violate dependency constraints. If a declared priority **conflicts** with dependencies, the model **SHALL** be **rejected** or **corrected** before execution.

**[TOOL-DEFINED]** Order of elements on the **canvas**, **z-order**, or **visual** ordering in an editor **MUST NOT** define evaluation semantics.

**Refinement vs v0.1:** :doc:`fmfl_v0_1` D.3 ties observable order to **textual** statement order in the FMFL file. **For v0.2**, where the **dependency graph** is explicit, **that graph SHALL take precedence** for evaluation order on **acyclic** models. FMFL textual order **SHALL** be **consistent** with dependencies; if not, processors **SHALL** reject or correct the model **[NORMATIVE]**.

--------------------------------------------------------------------------------
5. Cycle handling **[NORMATIVE]** / **[IMPLEMENTATION-DEFINED]**
--------------------------------------------------------------------------------

**[NORMATIVE]** **Cycle detection** is **required**.

**[NORMATIVE]** **Cycle classification** **SHALL**, at **minimum**, distinguish:

* **acyclic** dependencies (no directed cycle in the dependency graph), and
* **cyclic** dependencies (at least one directed cycle).

**[IMPLEMENTATION-DEFINED]** **Further** classification (e.g. algebraic vs delayed feedback) **MAY** be provided; where present, it **MUST** be **documented** for the backend.

**[IMPLEMENTATION-DEFINED]** **Cycle resolution** (fixed-point iteration, tearing, rejection): strategy **MUST** be **documented** for each backend; **MUST NOT** be **silent**.

**[NORMATIVE]** **Discrete-time** execution with **explicit** per-step **commit** (§6) implies the following **feedback discipline** for **delayed** (non-algebraic) cycles: **inputs** that **close** a cycle **SHALL** observe **committed** values from the **previous** step (equivalently: **old** value at the **input** of the feedback arc for the current step’s evaluation), and **outputs** produced in that evaluation **SHALL** become **visible** to **downstream** consumers only **after** **commit** (**new** value at the **output** side for the **next** step). This matches microcontroller and fixed-step **delay** practice and is **consistent** with §6; it **SHALL NOT** be conflated with **algebraic** simultaneous equality unless the backend **documents** an algebraic solver.

**[NORMATIVE]** Different backends **MAY** resolve the same cycle differently; differences **MUST** be **exposed** (e.g. **warnings**, **metadata**, or **report** fields). **Silent** divergence **MUST NOT** occur.

--------------------------------------------------------------------------------
6. State semantics **[NORMATIVE]**
--------------------------------------------------------------------------------

**[NORMATIVE]** Each execution step **SHALL** consist of:

1. **Read** **committed** state (previous step’s committed values).
2. **Evaluate** outputs and **candidate** next state **without** mutating **committed** state during the expression evaluation phase.
3. **Commit** **atomically** after evaluation completes.

**[NORMATIVE]** Updates to **committed** state **MUST NOT** be visible **during** evaluation of the same step (single-assignment / commit discipline).

**[NORMATIVE]** **Evaluation** **SHALL** be **side-effect-free** with respect to **committed** state until **commit** (see also :doc:`fmfl_v0_1` D.2 for **equations** purity in v0.1).

--------------------------------------------------------------------------------
7. Determinism **[NORMATIVE]** / **[IMPLEMENTATION-DEFINED]**
--------------------------------------------------------------------------------

**[NORMATIVE]** For a fixed **model**, fixed **backend**, and fixed **input sequence** (logical inputs per step), execution **SHALL** be **deterministic**: repeated runs **SHALL** yield the same **committed** state sequence **when** numeric and resolution behavior are held fixed.

**[IMPLEMENTATION-DEFINED]** Differences in **numeric representation** (e.g. IEEE float vs fixed-point quantization) **MAY** change **observable** values; such differences **MUST** be **documented** as part of the backend profile.

**[NORMATIVE]** **Acyclic** models **SHOULD** admit a **backend-independent** evaluation order (same topological order across conforming backends).

--------------------------------------------------------------------------------
8. Default values **[IMPLEMENTATION-DEFINED]**
--------------------------------------------------------------------------------

**[NORMATIVE]** The v0.1 rule “unread numerics read as zero” (:doc:`fmfl_v0_1`, D.3) is **retained** for **compatibility** with existing material but is **provisional**; it **SHALL NOT** be treated as a **stable**, **immutable** semantic guarantee across future specification versions.

**[IMPLEMENTATION-DEFINED]** Exact **defaulting rules** for **unassigned** names, **partially** assigned structures, and **boundary** conversions **MUST** be **documented** by each implementation. Future specifications **MAY** tighten defaults and **MAY** **deprecate** **implicit** defaulting of **unread** numerics.

--------------------------------------------------------------------------------
9. Numeric types and shapes (minimal v0.2) **[NORMATIVE]**
--------------------------------------------------------------------------------

**[NORMATIVE]** For the **execution semantics core** in v0.2, **all numeric values** participating in **evaluation** **SHALL** be **floating-point**. **Rank-0** (scalar), **rank-1** (1D array), and **rank-2** (2D array) **SHALL** be the **only** normative **shape** classes for **numeric** data in this core.

**[NORMATIVE]** **Shapes** define **structure only**; domain semantics (e.g. “curve”, “map”) are **optional** annotations and **SHALL NOT** be part of **core** execution semantics.

**[NORMATIVE]** **Axes** (labels, grids) **MAY** be attached by hosts; they are **orthogonal** to value shape and **SHALL NOT** alter **core** evaluation rules.

**[OUT-OF-SCOPE]** **Interpolation** rules between grid points for v0.2.

**[IMPLEMENTATION-DEFINED]** Mapping from FMF/FMFL **semantic** types (**Real**, **Int**, **Bool** in :doc:`fmfl_v0_1`) to **float** tensors and boolean handling at **ports** **MUST** be **documented**.

--------------------------------------------------------------------------------
10. Explicit non-goals (v0.2)
--------------------------------------------------------------------------------

This specification **does not** **[NORMATIVE]** define:

* A full **type algebra** beyond §9.
* **Solver** or **integration** **behavior**.
* **Interpolation** (see §9).
* **GUI** or **editor** semantics beyond **[TOOL-DEFINED]** markers.
* **Experiment** or **runtime** **configuration** detail.
* **Detailed** **host** **scheduling** beyond §3.

--------------------------------------------------------------------------------
11. References
--------------------------------------------------------------------------------

* :doc:`architecture_and_pipeline_v0_2` — FMF/FMFL roles and codegen pipeline.
* :doc:`changelog_v0_2` — compatibility and supersessions.
* :doc:`fmf_v0_1`, :doc:`fmfl_v0_1` — v0.1 baseline.
* :doc:`../plugin_concept_v0_3_plugin_api` — plugins **MUST NOT** redefine core FMFL semantics.
