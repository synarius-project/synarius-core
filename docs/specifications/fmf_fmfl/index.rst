..
   FMF & FMFL v0.1 — overview, principles, interaction, runtime (conceptual), future work.

================================================================================
FMF & FMFL (v0.1)
================================================================================

:Status: Draft v0.1
:Audience: Implementers of Synarius Core, loaders, code generators, and libraries

This section specifies the *Functional Model Format* (FMF) and *Functional Model Language* (FMFL) for Synarius. Detailed normative text is split into the documents below; this page collects scope, principles, cross-cutting interaction, and forward-looking notes.

.. toctree::
   :maxdepth: 1

   fmf_v0_1
   fmfl_v0_1
   normative_summaries_v0_1
   deliverables_examples

--------------------------------------------------------------------------------
A. Scope and Positioning
--------------------------------------------------------------------------------

**What is FMF?**

The *Functional Model Format* (FMF) is a file-based packaging and exchange format for *libraries* of functional modeling elements. It organizes metadata, interface descriptions, references to behavioral artifacts, and optional resources (e.g. icons) in a directory tree. FMF is inspired by the *structure* and *metadata discipline* of FMI 3.0 (e.g. clear root manifest, hierarchical resources), but it is **not** an FMI clone: it does not define a C API, binary co-simulation interfaces, or FMI-specific semantics.

**What is FMFL?**

The *Functional Model Language* (FMFL) is a **language-neutral**, **textual** intermediate representation (IR) of *behavior*: expressions, equations, and dataflow over **semantic types** (Real, Int, Bool), with **init** and **equations** phases. Its **concrete syntax is Python-like** (indented ``init:`` / ``equations:`` suites, no semicolons) to simplify tooling and the Python-first host path, while semantics remain target-agnostic. A code generation stage may lower a model graph (or library element definitions) into FMFL, then emit target languages (Python, C, Java, etc.).

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
2. **Generative pipeline** — Model graph → FMFL → target code is a first-class design path.
3. **Determinism** — Statement **order in FMFL** defines evaluation order; unassigned numerics read as **zero**; algebraic loops and cycles are **allowed**, with resolution left to authors (see :doc:`fmfl_v0_1`, D.3).
4. **File-based, library-oriented** — A library is a directory; discovery starts at ``libraryDescription.xml``.
5. **FMI-inspired structure, not FMI-bound** — Root manifest, version fields, and resource layout echo FMI ergonomics without importing FMI runtime obligations.
6. **Separation of structure and runtime** — FMF/FMFL describe *what* an element is and *how* it computes; *how* it is scheduled in a real-time loop or FMU is a host concern (hints only in v0.1).

**Default choices (v0.1)**

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
G. Runtime and execution concept (conceptual only)
--------------------------------------------------------------------------------

**Execution profiles (non-normative v0.1)**

* *Emulation* — deterministic stepping without real-time guarantees.
* *Live / real-time* — same semantics, host enforces scheduling and I/O.
* *FMU via Python* — future package bridges FMFL-generated or wrapped logic; not specified here.
* *Hosted Python* — Synarius Core runs generated or interpreted FMFL-backed instances in-process.

**Host lifecycle (informative; outside FMFL semantics)**

#. *Load* — read FMF, parse FMFL, validate names and behavior profiles.
#. *Configure* — bind parameters, allocate storage.
#. *Init phase* — execute FMFL ``init:`` suites once per instance (**no side effects** in v0.1).
#. *Step* — repeat **equations phase** (FMFL ``equations:``) per evaluation cycle; pure functional w.r.t. instance contract.
#. *Stop* — release resources; order relative to contributions TBD in later versions.

Normative definitions of **init** and **equations** phases are in :doc:`fmfl_v0_1`, D.2.

**Library runtime contributions (forward-looking)**

Libraries **MAY** later declare: initializers, services (logging, buses), adapters (Arduino, FMU). v0.1 only reserves XML containers; processors **MAY** ignore unknown sections.

--------------------------------------------------------------------------------
H. Future extensions (v0.2+)
--------------------------------------------------------------------------------

* **State** variables (persistent across steps) and richer collections (arrays, structs, enums) on top of semantic Real/Int/Bool.
* Units and dimensions.
* Explicit discrete states, events, clocks; continuous dynamics (ODEs).
* External functions with declared contracts.
* Backend-specific extension blocks (strictly namespaced).
* Stronger alignment with FMI packaging for co-simulation *where applicable*.
* Published XSD/Relax-NG schemas and conformance test suites.
