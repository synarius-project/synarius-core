..
   FMF & FMFL — overview (v0.2 addendum + v0.1 baseline), principles, interaction, runtime (conceptual), future work.

================================================================================
FMF & FMFL (v0.2 addendum, v0.1 baseline)
================================================================================

:Status: Draft v0.2 (addendum + v0.1 baseline)
:Audience: Implementers of Synarius Core, loaders, code generators, and libraries

This section specifies the *Functional Model Format* (FMF) and *Functional Model Language* (FMFL) for Synarius. **Specification v0.2** adds normative clarification of **roles** (FMF as XML packaging vs FMFL as textual behavioral IR), the **two-stage code generation pipeline** (:doc:`architecture_and_pipeline_v0_2`), and a **minimal execution semantics core** (:doc:`execution_semantics_v0_2`); see :doc:`changelog_v0_2`. **Normative details** for XML layout and FMFL grammar remain in the **v0.1 baseline** documents unless a v0.2 document **supersedes** them (see changelog).

.. toctree::
   :maxdepth: 1

   architecture_and_pipeline_v0_2
   execution_semantics_v0_2
   changelog_v0_2
   normative_summaries_v0_2
   fmf_v0_1
   fmfl_v0_1
   normative_summaries_v0_1
   deliverables_examples

--------------------------------------------------------------------------------
A. Scope and Positioning
--------------------------------------------------------------------------------

**What is FMF?**

The *Functional Model Format* (FMF) is a file-based packaging and exchange format for *libraries* of functional modeling elements. It organizes metadata, interface descriptions, references to behavioral artifacts, and optional resources (e.g. icons) in a directory tree. **Normatively, FMF uses XML** for manifests and element descriptions (see :doc:`fmf_v0_1`). FMF is inspired by the *structure* and *metadata discipline* of FMI 3.0 (e.g. clear root manifest, hierarchical resources), but it is **not** an FMI clone: it does not define a C API, binary co-simulation interfaces, or FMI-specific semantics.

**What is FMFL?**

The *Functional Model Language* (FMFL) is a **language-neutral**, **textual** intermediate representation (IR) of *behavior*: expressions, equations, and dataflow over **semantic types** (Real, Int, Bool), with **init** and **equations** phases. Its **concrete syntax is Python-like** (indented ``init:`` / ``equations:`` suites, no semicolons) to simplify tooling and the Python-first host path, while semantics remain target-agnostic. **FMFL is not an XML format**; it is **line-oriented text**. A code generation stage lowers a model graph (or library element definitions) into FMFL, then emits target languages (Python, C, Java, etc.); see :doc:`architecture_and_pipeline_v0_2`.

**How they relate**

* An FMF *library* contains *elements* (components). Each element declares *ports*, optional *parameters*, and a **reference** to one or more FMFL units that define executable meaning for that element.
* FMFL files live *inside* the library tree (or are referenced by relative path). They are not embedded ad hoc target-language source as a normative v0.1 feature.
* Synarius may later map FMFL to a hosted Python runtime, generated C, or an FMU-oriented Python package; those are **consumers** of FMFL, not definitions of it.

**Explicitly out of scope for v0.1**

* Arbitrary embedded target-language fragments as the primary behavior mechanism.
* Full dimensional analysis, units-of-measure algebra, and physical unit systems beyond semantic ``real``/``int``/``bool`` ports.
* States, events, clocks, hybrid or continuous-time semantics.
* Formal XML Schema / XSD publication (informative examples only).
* Normative mapping to FMI binary interfaces or ``fmi3*`` C APIs.
* Complete execution runtime API for emulation, live systems, or FMU (see section G only).

--------------------------------------------------------------------------------
B. Design Principles
--------------------------------------------------------------------------------

1. **Language-neutral semantics** — Behavior is expressed in FMFL, not in Python/C/Java inside the normative core.
2. **Generative pipeline** — Model graph → FMFL → target code is a first-class design path (detailed in :doc:`architecture_and_pipeline_v0_2`, v0.2).
3. **Determinism and evaluation order** — **v0.2** **[NORMATIVE]** rules for dependency-based order, cycle detection, state commit, and determinism are in :doc:`execution_semantics_v0_2`. The v0.1 textual-order rule (:doc:`fmfl_v0_1`, D.3) is **refined** when it conflicts with an explicit dependency graph (:doc:`changelog_v0_2`, M.1.1). Defaults for unassigned numerics are **[IMPLEMENTATION-DEFINED]**; the v0.1 “zero” rule is **provisional** compatibility only (:doc:`execution_semantics_v0_2`, §8).
4. **File-based, library-oriented** — A library is a directory; discovery starts at ``libraryDescription.xml``.
5. **FMI-inspired structure, not FMI-bound** — Root manifest, version fields, and resource layout echo FMI ergonomics without importing FMI runtime obligations.
6. **Separation of logical model vs runtime** — FMF/FMFL specify **logical** system behavior and the **canonical execution cycle** (:doc:`execution_semantics_v0_2`). **Experimentation**, **pacing** (real-time vs accelerated), and **solver** choice are **[OUT-OF-SCOPE]** for this specification (§1 of :doc:`execution_semantics_v0_2`). Host scheduling hints in XML remain informative only where v0.1 allows.

**Default choices (v0.1 baseline)**

* **One manifest per library**: ``libraryDescription.xml`` at the library root identifies the folder as an FMF library (analogous in *role* to a package marker, not to Python import semantics).
* **Per-element directories** under ``components/<ElementId>/`` keep interface, behavior, and assets co-located and avoid global name clashes in large libraries.
* **FMFL** uses a **Python-like** surface syntax: ``init:`` (once, no side effects in v0.1) and ``equations:`` (per step, pure) — not ``run:`` (deprecated alias only).
* **Host element references** (e.g. New operator): ``<LibName>.<ElementId>``; bundled standard library uses manifest ``name="std"`` and **MAY** be referenced without the ``std.`` prefix — see :doc:`fmf_v0_1`, C.1.1.

--------------------------------------------------------------------------------
F. Interaction between FMF and FMFL
--------------------------------------------------------------------------------

1. **Reference** — ``elementDescription.xml`` contains ``<Behavior>`` with one or more ``<FMFL file="..." profile="..."/>`` children (paths relative to the element directory). Loaders select a **profile** (defaulting to ``default``), resolve the FMFL file, and bind port and parameter names.
2. **Multiple elements** — One library lists many ``<Element>`` entries; each points to its own ``elementDescription.xml`` and FMFL sources.
3. **Model graph → FMFL** — A graph of instantiated elements compiles to one or more FMFL *compilation units* (e.g. one flattened unit per subsystem, or one per element with host wiring). v0.1 does not mandate flattening; it only requires that *library elements* ship FMFL for their local behavior.
4. **Code generation** — The generator consumes resolved FMFL (AST) plus **type / target profiles** mapping semantic types to concrete representations, and host binding of ports to memory/signals. Python is the first supported host: generated modules **MAY** expose a callable or class per instance implementing **init phase** once and **equations phase** per step.

.. _fmf-fmfl-runtime-concept:

--------------------------------------------------------------------------------
G. Runtime and execution concept (conceptual vs v0.2 core)
--------------------------------------------------------------------------------

**Canonical logical semantics (v0.2)** — The **trigger → evaluation → commit** cycle, execution **modes**, dependency **order**, **cycle** rules, **state** commit, **determinism**, and minimal **numeric** shapes are **[NORMATIVE]** in :doc:`execution_semantics_v0_2`.

**Execution profiles (informative; host / experiment — [OUT-OF-SCOPE] for core spec)**

* *Emulation*, *live*, *FMU via Python*, *hosted Python* — remain **informative** profiles; **real-time pacing** vs **maximum speed** is **[OUT-OF-SCOPE]** (:doc:`execution_semantics_v0_2`, §1, §3).

**Host lifecycle (informative; binding [OUT-OF-SCOPE] in detail)**

#. *Load* — read FMF, parse FMFL, validate names and behavior profiles.
#. *Configure* — bind parameters, allocate storage.
#. *Init phase* — execute FMFL ``init:`` suites once per instance (see :doc:`fmfl_v0_1`, D.2).
#. *Step* — **equations** phase per logical cycle; alignment with :doc:`execution_semantics_v0_2`, §2 and §7.
#. *Stop* — release resources; **[OUT-OF-SCOPE]** ordering details.

Normative definitions of **init** and **equations** *phases* (v0.1) remain in :doc:`fmfl_v0_1`, D.2; **v0.2** adds **commit** discipline and **order** rules as above.

**Library runtime contributions (forward-looking)**

Libraries **MAY** later declare: initializers, services (logging, buses), adapters (Arduino, FMU). v0.1 only reserves XML containers; processors **MAY** ignore unknown sections.

--------------------------------------------------------------------------------
H. Future extensions (beyond v0.2 addendum)
--------------------------------------------------------------------------------

**Addressed as normative clarification in v0.2** (see :doc:`architecture_and_pipeline_v0_2`, :doc:`execution_semantics_v0_2`, :doc:`changelog_v0_2`)

* **Pipeline / IR role** — Two-stage **graph → FMFL → target** pipeline; FMFL as **non-XML** behavioral IR; FMF remains XML for packaging.
* **Execution semantics core** — Canonical cycle; modes (**scheduled** **[RESERVED]**); dependency **order**; **cycle** detection/classification vs **[IMPLEMENTATION-DEFINED]** resolution; **state** commit; **determinism**; minimal **float** tensor shapes; **[OUT-OF-SCOPE]** runtime/experiment concerns.

**Still forward-looking**

* Richer **state** variables and collections beyond minimal float ranks in §9 of :doc:`execution_semantics_v0_2`.
* Units and dimensions.
* Explicit discrete states, events, clocks; continuous dynamics (ODEs).
* External functions with declared contracts.
* Backend-specific extension blocks (strictly namespaced).
* Stronger alignment with FMI packaging for co-simulation *where applicable*.
* Published XSD/Relax-NG schemas and conformance test suites.
