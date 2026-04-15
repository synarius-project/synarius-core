..
   FMF/FMFL v0.2 — roles (FMF XML vs FMFL IR), two-stage codegen, relation to prototype XML IR.

================================================================================
Architecture and code generation pipeline (v0.2)
================================================================================

:Status: Draft v0.2
:Audience: Implementers of Synarius Core, loaders, code generators, editors, and libraries

This document **normatively clarifies** (for specification level v0.2) how the *Functional Model Format* (FMF), *Functional Model Language* (FMFL), and **graph-to-code generation** relate. **Execution semantics** (trigger / evaluation / commit, modes, order, cycles, state, determinism) are specified in :doc:`execution_semantics_v0_2`. Detailed packaging and FMFL grammar remain in :doc:`fmf_v0_1` and :doc:`fmfl_v0_1` unless a v0.2 document explicitly **supersedes** a statement (see :doc:`changelog_v0_2`).

--------------------------------------------------------------------------------
I. Roles: FMF (XML) vs FMFL (textual IR)
--------------------------------------------------------------------------------

**FMF — XML for structure and packaging**

* FMF **SHALL** use **XML** for normative library and element **metadata**: manifests, ports, parameters, graphics references, and **pointers** to behavioral artifacts.
* Normative layout and elements are defined in :doc:`fmf_v0_1`. Processors **SHALL** treat ``libraryDescription.xml`` and per-element ``elementDescription.xml`` as the authoritative structural description of a library.

**FMFL — not XML; line-oriented behavioral IR**

* FMFL **SHALL NOT** be defined as an XML vocabulary. It is a **UTF-8, line-oriented, textual** intermediate representation of *behavior* (phases, assignments, expressions, dataflow) with a **Python-like** concrete syntax as specified in :doc:`fmfl_v0_1`.
* FMFL is the **canonical semantic layer** for *what to compute* for an element or a lowered subsystem, independent of target language.

**Non-goals (normative)**

* There **SHALL NOT** be a normative requirement to serialize FMFL *as XML* (e.g. embedding the FMFL program tree as a second XML IR that duplicates FMFL semantics).
* FMF **MAY** reference FMFL **files** (``*.fmfl``) from ``elementDescription.xml`` as in v0.1; that is **not** “FMFL expressed as element XML”, but **reference by path**.

--------------------------------------------------------------------------------
J. Two-stage code generation pipeline
--------------------------------------------------------------------------------

Implementations **SHOULD** structure full **graph-to-source** compilation as **two** conceptual stages:

**Stage 1 — Graph → FMFL (semantic lowering)**

* **Input:** A host model graph (instances, connections, operators, parameters, foreign blocks such as FMUs as declared in the host).
* **Output:** One or more **FMFL compilation units** (text), expressing evaluation order, equations, and **init** / **equations** phases per :doc:`fmfl_v0_1`.
* **Responsibility:** Preserve **simulation semantics** and **determinism** rules (statement order, port wiring). This stage **SHALL NOT** depend on a particular target programming language.

**Stage 2 — FMFL → target code (syntactic lowering)**

* **Input:** Parsed FMFL (AST or equivalent) plus **type / target profiles** (mapping semantic Real/Int/Bool to concrete representations).
* **Output:** Source files in Python, C, or other **dialect-specific** targets, or bytecode / linkage artifacts as defined by the host toolchain.
* **Responsibility:** **Syntax**, idioms, and **profiles** (e.g. float width, fixed-point); **SHALL NOT** redefine FMFL semantics.

**Informative diagram (ASCII)**

::

    +-------------+     Stage 1      +-------------+     Stage 2      +--------------+
    | Model graph | --------------> | FMFL (text) | --------------> | Target code  |
    +-------------+                  +-------------+                  | (Python, C,  |
         ^                                ^                          |  ...)        |
         |                                |                          +--------------+
         |  FMF library elements          |
         |  reference *.fmfl  ------------+
         |
    +-------------+
    | FMF XML     |  (library + element metadata only; not a substitute for FMFL)
    +-------------+

**Relation to earlier prototype pipelines**

* Some prototypes used an **XML module** as the **sole** IR between a graphical editor and a Python generator. In the Synarius architecture, that **role** — *machine-oriented intermediate program between graph and target code* — is **filled by FMFL**, not by a parallel XML IR for the same behavior.
* **XML** remains appropriate for **FMF** (packaging). **FMFL** remains the **behavioral** IR for lowering from the graph and for **second-stage** generators.

--------------------------------------------------------------------------------
J.1 Graphical identity vs logical variables (normative clarification)
--------------------------------------------------------------------------------

**[NORMATIVE]** A **graphical** model **MAY** assign **stable identifiers** to **elements** and **connections** (for editing, diff/merge, and packaging). Those identifiers **SHALL** be treated as **referring to graphical or structural occurrences**, not necessarily to **pairwise distinct** logical variables in the lowered program.

**[NORMATIVE]** **Lowering** from the graph to FMFL (stage 1) **SHALL** define how **ports**, **wires**, and **shared** parameters map to **logical** names and **dependencies**. **Several** graphical instances **MAY** contribute to **one** logical signal or **one** equation block after fusion, fan-in, or library expansion.

**Informative (Synarius Core scalar dataflow).** The **dataflow** compile pass in ``synarius_core.dataflow_sim`` (``CompiledDataflow``) implements:

* **Delayed feedback** — directed cycles among **non-FMU** diagram nodes are accepted. The compiler computes a **minimal** set of **feedback edges** (removed from the DAG used for evaluation order) and treats each as a **one-step delay**: the source is read from the **workspace snapshot at step start** (``RunStepExchange.workspace_previous``), consistent with :doc:`execution_semantics_v0_2` §5–§6.
* **FMU on a cycle** — if an FMU diagram block lies on a directed cycle, compilation **fails** (no ``CompiledDataflow``); delayed feedback for FMUs is not implemented yet.
* **Logical fusion** — optional attribute ``dataflow.scalar_slot_id`` on a diagram node (UUID string of another node’s id) maps several instances to **one** scalar workspace slot; FMU blocks **must not** use slot fusion.

--------------------------------------------------------------------------------
J.2 Delay policy (Synarius Core implementation)
--------------------------------------------------------------------------------

**Informative.** Until a dedicated **Delay** block or per-connector delay metadata exists in the diagram model, the compiler **infers** unit delay on feedback arcs (greedy cycle breaking). **Algebraic** cycles (simultaneous equations without delay) are **not** simulated; they become **delayed** by construction. A future normative option is an **explicit** delay element so users control which arc carries the register.

--------------------------------------------------------------------------------
K. Plugins and generators (cross-reference)
--------------------------------------------------------------------------------

The :doc:`../plugin_concept_v0_3_plugin_api` document defines plugin capabilities (e.g. compile-time and runtime hooks). **FMFL** is part of the **core behavioral contract**; plugins **MUST NOT** redefine FMFL semantics (see plugin API). Generators that emit target code from FMFL are **consumers** of the IR specified in :doc:`fmfl_v0_1`.

--------------------------------------------------------------------------------
L. References
--------------------------------------------------------------------------------

* :doc:`index` — umbrella scope and principles (updated for v0.2).
* :doc:`changelog_v0_2` — what v0.2 adds vs v0.1 baseline.
* :doc:`execution_semantics_v0_2` — canonical execution semantics core (v0.2).
* :doc:`fmf_v0_1` — FMF XML specification (v0.1 baseline).
* :doc:`fmfl_v0_1` — FMFL language (v0.1 baseline).
