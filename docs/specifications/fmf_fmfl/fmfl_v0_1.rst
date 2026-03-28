..
   FMFL v0.1 — Functional Model Language (IR), execution phases, types, standard library.

================================================================================
FMFL v0.1 specification
================================================================================

:Status: Draft v0.1

This document specifies the *Functional Model Language* (FMFL), semantic types, execution phases, and the normative **Standard Library** surface. For FMF packaging and XML, see :doc:`fmf_v0_1`. The concrete syntax is **Python-like** (indented suites, no semicolons, ``#`` comments) while semantics remain target-agnostic.

--------------------------------------------------------------------------------
D. FMFL v0.1 specification
--------------------------------------------------------------------------------

D.1 Purpose
~~~~~~~~~~~

FMFL is an **intermediate** representation: compact, easy to parse, and easy to lower to multiple targets. It is **not** a user-facing modeling language; it may be generated from a graph editor or from library templates.

D.2 Execution phases (v0.1, normative)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hosts **SHALL** support the following **two** behavioral phases for each FMFL unit bound to an element instance:

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Phase
     - Semantics
   * - **1. Init phase**
     - Executed **once** after configuration. Assigns **initial values** to local names and **MAY** assign output ports for initial outputs. **SHALL NOT** cause **side effects** in v0.1 (no I/O, no mutation outside the instance’s assigned variables/ports/parameters as defined by this specification).
   * - **2. Equations phase**
     - Executed **once per evaluation step**. **Pure functional** evaluation: given fixed inputs (input ports, parameters, and any state defined in v0.2+), assignments define outputs; v0.1 does not specify host I/O during this phase.

Load, configure, stop, and scheduling are **host** concerns (see :doc:`index`, section G).

D.3 Determinism and evaluation order
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **Evaluation order** within a phase is defined **only** by the **textual order** of statements in the FMFL file (and by any explicit dataflow implied by assignments). Hosts **SHALL NOT** reorder statements in a way that changes observable results relative to that order.
* **Numeric values** of locals not assigned before use **SHALL** be treated as **numeric zero** of the expression’s semantic type context (v0.1: real context uses **0.0**). Authors **SHOULD** assign explicitly where readability matters.
* **Algebraic loops**, **cyclic equation systems**, and **temporary local variables** are **permitted**; resolving consistency (fixed-point, tearing, rejection) is **the responsibility of library and model authors**, not the v0.1 host contract.

D.4 Ports, local variables, parameters, and state
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Category
     - Meaning
   * - **Input port**
     - External input to the element (declared in FMF with ``kind="in"``). Read-only in FMFL.
   * - **Output port**
     - External output (``kind="out"``). Assigned in FMFL.
   * - **Local variable**
     - **Temporary** name introduced by assignment inside the FMFL unit; not an external port.
   * - **Parameter**
     - **Constant** for the instance, declared in FMF; exposed as a read-only name in FMFL.
   * - **State** *(v0.2+)*
     - **Persistent** across steps; not normative in v0.1.

Assignments **MAY** target output ports and local variables in the **equations** suite; the **init** suite **MAY** assign locals and output ports for initialization.

D.5 Semantic type system (v0.1)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

FMFL uses **abstract semantic types** only; the IR **SHALL NOT** fix concrete storage (e.g. IEEE ``float``, ``float64``, ``int16``).

.. list-table::
   :header-rows: 1
   :widths: 18 82

   * - Semantic type
     - Role
   * - **Real**
     - Real-valued scalar (algebraic use in v0.1).
   * - **Int**
     - Integer scalar *(minimal use in v0.1; literals and ports **MAY** use ``int`` in FMF)*.
   * - **Bool**
     - Boolean scalar.

**Type profiles / target profiles** (development vs controller, fixed-point, etc.) **SHALL** map these semantic types to concrete representations during code generation. Example (informative): *Development*: ``Real`` → IEEE ``float64``; *Embedded controller*: ``Real`` → fixed-point or integer-based representation. **One** semantic definition in the model; **profiles** decide numeric representation and codegen — no duplicate parallel float/int FMFL dialects as a default.

FMF ``<Port type="..."/>`` uses lowercase tokens ``real``, ``int``, ``bool`` aligned to **Real**, **Int**, **Bool**.

D.6 Minimal language core
~~~~~~~~~~~~~~~~~~~~~~~~~

**Files**

* UTF-8 text, line-oriented.
* Optional first line: ``fmfl 0.1`` (recommended).

**Literals**

* Real literals: lexical subset of Python 3 floating literals.
* Integer literals: lexical subset of Python 3 integers.
* Boolean literals: ``True``, ``False``.

**References**

* Identifiers: Python identifier rules. Names **MUST** resolve to an input port, output port, parameter, or local already assigned in an earlier line or in **init**.

**Operators (scalar, v0.1)**

* Arithmetic: ``+``, ``-``, ``*``, ``/`` with usual precedence; unary ``-``.
* Intrinsics: ``abs``, ``min``, ``max`` as in the Standard Library note below.

**Assignments**

* One statement per line: ``<target> = <expr>`` (no semicolon).
* ``<target>`` is an **output port** or a **local variable** (locals may be introduced by first assignment).

**Comments**

* ``#`` to end of line.

D.7 Initialization and equations blocks (syntax)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Structure**

* ``init:`` and ``equations:`` each introduce an indented suite (Python indentation rules; 4 spaces **RECOMMENDED**).
* Empty suites **SHALL** contain ``pass`` on an indented line.

**``init:``**

* Runs in the **init phase** (D.2). **No side effects** (v0.1).

**``equations:``**

* Runs in the **equations phase** (D.2). **Pure** evaluation for that step.

The keyword ``run:`` is **deprecated** and **SHALL NOT** appear in conforming v0.1 FMFL; processors **MAY** accept ``run:`` as an alias for ``equations:`` when documented as a transitional extension.

D.8 Syntax sketch (informative)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   file ::= [VERSION_LINE] (INIT_BLOCK | EQUATIONS_BLOCK)+
   VERSION_LINE ::= "fmfl" VERSION NEWLINE
   INIT_BLOCK ::= "init:" NEWLINE INDENT statement+ DEDENT
   EQUATIONS_BLOCK ::= "equations:" NEWLINE INDENT statement+ DEDENT
   statement ::= assign NEWLINE
   assign ::= TARGET "=" expr

D.9 Examples (informative)
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Add**

.. code-block:: python

   fmfl 0.1

   init:
       pass

   equations:
       out = in0 + in1

**Mul**

.. code-block:: python

   fmfl 0.1

   init:
       pass

   equations:
       out = in0 * in1

--------------------------------------------------------------------------------
E. Standard library (normative, v0.1)
--------------------------------------------------------------------------------

The FMF v0.1 **standard library** (library ``name`` **SHALL** be ``std``; host references **SHALL** use ``std.<ElementId>`` or unqualified ``<ElementId>`` per :doc:`fmf_v0_1`, C.1.1) **SHALL** provide at least the following elements for interoperability:

* **Add**
* **Sub**
* **Mul**
* **Div**

Each **SHALL** use the port names and semantics in the table below. **SHOULD** additionally provide **Neg**, **Abs**, **Min**, and **Max** with the same naming conventions where extended interoperability is desired.

.. list-table::
   :header-rows: 1
   :widths: 12 28 20 40

   * - id
     - Purpose
     - Ports
     - FMFL (``equations`` suite)
   * - Add
     - Real addition
     - ``in0``, ``in1`` → ``out``
     - ``out = in0 + in1``
   * - Sub
     - Real subtraction
     - ``in0``, ``in1`` → ``out``
     - ``out = in0 - in1``
   * - Mul
     - Real multiplication
     - ``in0``, ``in1`` → ``out``
     - ``out = in0 * in1``
   * - Div
     - Real division
     - ``in0``, ``in1`` → ``out``
     - ``out = in0 / in1``
   * - Neg
     - Unary negation
     - ``in0`` → ``out``
     - ``out = -in0``
   * - Abs
     - Absolute value
     - ``in0`` → ``out``
     - ``out = abs(in0)``  *(see note)*
   * - Min
     - Minimum of two reals
     - ``in0``, ``in1`` → ``out``
     - ``out = min(in0, in1)``
   * - Max
     - Maximum of two reals
     - ``in0``, ``in1`` → ``out``
     - ``out = max(in0, in1)``

For **Add**, **Sub**, **Mul**, and **Div**, graphics **SHALL** follow the FMF triple-icon rules with **``*_16.svg`` preferred** for single-resolution hosts (see :doc:`fmf_v0_1`, C.3.1). Icon artwork is aligned with Synarius Studio BasicOperator vector glyphs (blue fill ``#2468dc``, dark stroke ``#16161c``).

**Note on ``abs``, ``min``, ``max``:** these are **intrinsic** functions; code generators **SHALL** map them to safe target equivalents. If a host cannot implement an intrinsic, that element **SHALL NOT** be exposed in that profile.
