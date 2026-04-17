..
   Synarius — Code-generation architecture: four-layer model, FMFL/FMF
   specifications, and Stage-2 implementation plan.

================================================================================
Code-Generation Architecture, Specifications, and Implementation Plan
================================================================================

:Status: Concept (pre-specification)
:Version: 0.8
:Scope: synarius-core — FMFL IR, code-generation pipeline, backend architecture
:Supersedes: Concept v0.3

.. note::

   Sections explicitly labelled **[FUTURE]** or enclosed in a note block
   reading "future work" describe architectural intent for subsequent
   implementation cycles.  Nothing in those sections is normative for the
   current implementation cycle.  All other sections describe the current
   target state.

.. contents:: Contents
   :depth: 4
   :local:

================================================================================
1  Architecture of Code Generation
================================================================================

--------------------------------------------------------------------------------
1.1  Problem Statement
--------------------------------------------------------------------------------

The :doc:`architecture_and_pipeline_v0_2` specification, section J, requires a
strictly sequential two-stage code-generation pipeline.  Stage 1 lowers the
model graph into a complete FMFL intermediate representation.  Stage 2
transforms that FMFL text into target-language source code.  The two stages are
separated by a well-defined boundary: the FMFL text.

The current implementation violates this requirement at every level.

``codegen_kernel.generate_fmfl_document`` and
``python_step_emit.generate_unrolled_python_step_document`` both traverse
``CompiledDataflow`` directly through ``iter_equation_items``.  They share the
same input and run in parallel.  The Python emitter accesses the typed equation
dataclasses ``EqKennlinie``, ``EqKennfeld``, and ``EqKennwert`` as its primary
semantic sources.  It reads wire references from their ``in_x`` and ``in_y``
fields, determines lookup semantics from the dataclass type, and emits calls to
``syn_curve_lookup_linear_clamp`` and ``syn_map_lookup_bilinear_clamp`` based on
structural graph data rather than on a parsed FMFL text.  The FMFL text
produced by Stage 1 is not consumed anywhere.

The absence of a real stage boundary produces three compounding deficiencies.

First, there is no separation of concerns.  Semantic decisions about what to
compute are mixed with syntactic decisions about how to express it in Python.
The backend contains model logic; the model logic contains backend assumptions.

Second, every new code-generation target must re-implement graph traversal from
scratch.  A C backend would duplicate the entire ``iter_equation_items`` loop,
all block-type dispatch branches, and all wire-resolution logic.  There is no
shared semantic layer that would allow a backend to consume a language-neutral
description of the computation.

Third, the FMFL text is not a self-contained artifact.  Its correctness cannot
be verified independently of the graph.  The historical omission of equation
lines for ``std.Kennlinie`` and ``std.Kennfeld`` — blocks whose inputs existed
only in the graph — is a direct consequence: because Stage 2 never needed the
FMFL to be complete, there was no pressure to make it complete.

--------------------------------------------------------------------------------
1.2  Architectural Principles
--------------------------------------------------------------------------------

The architecture defined in this document is governed by four principles.
Each principle applies uniformly to all layers and all implementation stages.

**Separation of semantics and realization.**  The definition of *what* is
computed is owned by the FMFL layer alone.  The definition of *how* that
computation is realized — in what numeric type, on what platform, with what
scheduling context — is owned by the three non-semantic layers.  These
responsibilities must never merge.  A component that contains both semantic
and realization logic in a single unit violates this principle and must be
refactored.

**No hidden semantics in backends.**  Every semantic rule applied during code
generation must be traceable to an explicit, documented source: the FMFL text,
the Implementation Profile, the Target Binding, or the Build Policy.  A backend
that handles a specific block type, a specific operator, or a specific edge
case based on knowledge derived from the graph — rather than from the FMFL
text — introduces hidden semantics.  The correct resolution is always to make
the FMFL text explicit, not to add compensating logic in the backend.

**Explicit over implicit.**  Default behavior is a specification, not the
absence of specification.  Section 1.5 defines normative default semantics
precisely.  Deviating from the default requires an explicitly named and
documented Implementation Profile.  A backend that silently falls back to
assumed defaults when a profile is underspecified must be rejected; it must
instead produce a diagnostic that identifies the underspecified parameter.

**Deterministic execution defined in FMFL.**  The evaluation order of all
statements in the equations phase is determined exclusively by the textual
order of statements in the FMFL ``equations:`` block.  Stage 1 is responsible
for emitting statements in a valid topological order.  Stage 2 is responsible
for preserving that order exactly.  No backend may reorder statements, merge
assignments, or infer an alternative execution order from the graph.

--------------------------------------------------------------------------------
1.3  The Four-Layer Architecture
--------------------------------------------------------------------------------

All code generation in Synarius is governed by four distinct input layers.
Each layer has a precisely defined scope, a defined set of permitted concerns,
and an explicit set of concerns it must not address.

The four layers and their positions in the pipeline are::

    ┌──────────────────────────────────────────────────────┐
    │  Layer 1 · FMFL            model logic               │
    │  Layer 2 · Impl. Profile   realization parameters    │
    │  Layer 3 · Target Binding  platform integration      │
    │  Layer 4 · Build Policy    output configuration      │
    └──────────────────────────────────────────────────────┘

Each layer answers a distinct, non-overlapping question:

* **FMFL** defines *what* the system computes — the operations, the
  dataflow, and the evaluation order.
* **Implementation Profile** defines *how* abstract values are realized —
  the numeric type, rounding mode, and approximation behavior.
* **Target Binding** defines *where* and *in which environment* the
  computation runs — the runtime types, storage layout, and lifecycle
  contracts.
* **Build Policy** defines *how* the output artifact is structured and
  emitted — file layout, formatting, and instrumentation toggles.

No layer may answer the question of another layer.

1.3.1  FMFL — Model Logic
~~~~~~~~~~~~~~~~~~~~~~~~~~

FMFL is the single source of truth for model semantics.

FMFL defines the complete dataflow between named values through ordered
assignment statements.  It defines the operations applied to those values:
arithmetic expressions using the binary operators ``+``, ``-``, ``*``, and
``/``; calls to the lookup primitives ``param_scalar``, ``curve_lookup``, and
``map_lookup`` as specified in :doc:`../compiler_lowering_rules`; and calls to
standard-library functions.  FMFL defines the evaluation order of all
statements, which Stage 1 emits in a topological order consistent with the
dependency graph per :doc:`execution_semantics_v0_2`, section 4.  FMFL defines
the delayed-feedback annotation ``prev(expr)`` for values that must be read
from the committed state of the previous evaluation step.

FMFL must not contain platform-specific numeric types, instrumentation or
logging annotations, initialization routines, lifecycle entry points, build
configuration, file naming, or any reference to the host runtime environment.

1.3.1.1  Explanation
^^^^^^^^^^^^^^^^^^^^^

The requirement that FMFL be the single source of truth for model semantics
is not merely a structural preference — it is a correctness requirement.

When a backend infers semantic information from sources other than the FMFL
text, two representations of the same model's semantics exist simultaneously:
one in the FMFL text and one reconstructed inside the backend.  These two
representations will diverge.  The divergence may be subtle — a difference in
the handling of a specific block type, a difference in the treatment of
feedback edges under a particular topology — but it will exist.  Because the
divergence is implicit, it cannot be detected by comparing the two
representations.  It is detectable only by observing different behavior at
runtime, typically in an edge case that was not covered by the original
development tests.

The correct model is that Stage 1 encodes all semantic information into the
FMFL text, and Stage 2 reads only that text.  If Stage 1 encodes the
computation correctly and completely, then any Stage 2 implementation that
parses the FMFL text correctly will produce a semantically equivalent target
program.  This property — that the FMFL text alone is sufficient to reconstruct
the computation — is the definition of semantic completeness, and it is what
enables backend independence.

1.3.1.2  Typical Mistakes
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The following mistakes occur when the single-source-of-truth principle is not
observed.  Each represents a case where semantic information is held outside
the FMFL text.

A backend calls ``iter_equation_items(compiled)`` and reads the resulting typed
dataclasses.  It uses the type of the dataclass — for example,
``isinstance(ev, EqKennlinie)`` — to determine that a curve lookup must be
emitted, and it reads ``ev.in_x`` to obtain the input variable name.  This is
a semantic reconstruction from graph data.  The correct approach is for Stage 1
to emit ``KL1 = curve_lookup(ref, x_kl1)`` in the FMFL text, and for the
backend to read ``curve_lookup`` from the parsed ``CallExpr.func`` field.

A backend accesses ``CompiledDataflow.incoming`` to determine the order in
which wire sources must be resolved.  The evaluation order is already encoded
in the FMFL statement sequence; accessing the graph for ordering information
means the backend is substituting its own dependency resolution for the order
that Stage 1 already determined.

A backend accesses ``CompiledDataflow.feedback_edges`` to decide whether to
emit a ``prev`` wrapper.  The ``prev`` annotation is already present in the
FMFL text as ``prev(name)``; the backend should read it from the parsed
``PrevExpr`` node.

A backend treats the absence of a ``CallExpr`` node in the FMFL as evidence
that a particular block type was not used, and uses that absence to omit a
conditional import.  The presence or absence of an import must be determined
from the FMFL text, not from inference about what the graph might have
contained.

1.3.1.3  Example
^^^^^^^^^^^^^^^^^

The following FMFL equations block is a minimal complete example covering the
constructs that Stage 1 currently emits:

.. code-block:: text

   equations:
     # x_input: no incoming edge (initial value / stimulation)
     # y_input: no incoming edge (initial value / stimulation)
     scaled = x_input * 2.5
     out_curve = curve_lookup(@active_dataset.motor.torque_curve, scaled)
     out_map   = map_lookup(@active_dataset.motor.efficiency_map, scaled, y_input)
     out_delay = prev(scaled)
     result    = out_curve + out_map

The semantics of this block are fully determined by the text alone.

``scaled`` is computed as the product of ``x_input`` and the literal ``2.5``.
``out_curve`` is computed by a one-dimensional linear interpolation over the
parameter data identified by ``@active_dataset.motor.torque_curve``, evaluated
at ``scaled``.  ``out_map`` is computed by a two-dimensional bilinear
interpolation over the parameter data identified by
``@active_dataset.motor.efficiency_map``, evaluated at ``(scaled, y_input)``.
``out_delay`` reads the value of ``scaled`` from the committed snapshot of the
previous evaluation step; it does not depend on the value of ``scaled`` in the
current step.  ``result`` is the sum of ``out_curve`` and ``out_map``.

A correct Stage 2 backend requires no further information to emit semantically
equivalent target code.  It does not need to know what type of graph node
produced each line.  It does not need to know which inputs were stimulated.
It does not need to access the graph at all.

1.3.2  Implementation Profile — Realization Parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Implementation Profile defines realization-specific aspects that govern
how abstract real-valued quantities are approximated in a concrete numeric
system.  These aspects alter numerical results relative to idealized real
arithmetic.  They are not part of the abstract model semantics.

It specifies how the abstract, type-free ``Real`` values defined by FMFL are
approximated as concrete numeric quantities in the generated code.  This
includes the numeric storage type for ``Real`` values, the rounding mode
applied to intermediate computations, the overflow and saturation behavior of
arithmetic operations, and the precision constraints imposed on lookup results.

**The Implementation Profile IS:**

* the sole layer that maps abstract ``Real`` values to concrete numeric types,
* the sole layer that defines rounding mode, saturation, and overflow behavior,
* the sole layer that introduces approximation error into an otherwise ideal
  computation.

**The Implementation Profile IS NOT:**

* a platform integration specification — that is the Target Binding (section
  1.3.3),
* a build output configuration — that is the Build Policy (section 1.3.4),
* a semantic specification — the mathematical meaning of each operation is
  owned by FMFL and is not changeable by the profile,
* an execution logic specification — the set of operations performed, the
  dataflow between named values, and the evaluation order are owned exclusively
  by FMFL and are not alterable by the profile.

**Semantic boundary.**  Changes to the Implementation Profile alter the
numerical results of a computation while leaving the abstract model structure
completely unchanged.  The FMFL text is identical before and after a profile
change; only the realization of abstract ``Real`` values in a concrete numeric
system differs.  An implementer who changes a profile parameter must expect
different numerical outputs but must not observe any change in which values
are computed, which operations are applied, or in what order.

**Layer assignment decision rule.**  Use this rule to determine which layer
a given property belongs to.  The rule is exhaustive; every property must
be assignable to exactly one layer.

.. list-table::
   :widths: 55 45
   :header-rows: 1

   * - If a property …
     - … it belongs to
   * - Changes *which values are computed* (alters the abstract mathematical
       result for any input)
     - **Layer 1 — FMFL** (semantic)
   * - Changes the *numerical results* of the system (alters computed
       values relative to idealized real arithmetic) but is *not* part of
       the abstract model logic
     - **Layer 2 — Implementation Profile** (realization)
   * - Only affects *integration into a runtime environment* — where values
       are stored, how the function is called, what types wrap the workspace
     - **Layer 3 — Target Binding** (platform)
   * - Has *no effect on any computed value* and only controls the structure
       or formatting of the generated artifact
     - **Layer 4 — Build Policy** (output configuration)

**Key test for borderline cases.**  Ask: "If I change this parameter and
re-generate for a fixed set of inputs, do the output values change?"

* Yes, and the change is in abstract mathematical meaning → FMFL.
* Yes, and the change is in numerical approximation only → Implementation Profile.
* No, but the integration contract changes → Target Binding.
* No, and nothing observable in execution changes → Build Policy.

The Implementation Profile must not alter the structural dataflow, the set of
operations, or the evaluation order; those are owned exclusively by FMFL.

In the current implementation cycle, the Implementation Profile layer exists
structurally but carries only the single default entry described in section
1.5.  It is represented as a string identifier — ``"python_float64"`` for the
default — whose only operational effect is the selection of a backend.  No
configurable profile format and no quantization semantics are implemented.

1.3.2.1  Explanation
^^^^^^^^^^^^^^^^^^^^^

The Implementation Profile separates two categories of concern that are
frequently conflated: concerns that affect *what* is computed (semantic
concerns, belonging to FMFL) and concerns that affect *how precisely* the
computation is realized in a given numeric system (realization concerns,
belonging to the profile).

A value of type ``Real`` in FMFL has idealized real-number semantics.  The
product of two ``Real`` values is their exact mathematical product.  No numeric
Implementation Profile can change this semantic definition; it can only choose
a realization that approximates it.  IEEE 754 double precision is one such
approximation.  A 16-bit fixed-point format with 8 fractional bits is another.
Both are realizations of the same ideal; they produce different numerical
results, but they compute the same *mathematical* quantity up to the precision
of their respective representations.

This distinction matters because it establishes what belongs in the profile and
what belongs in FMFL.  A decision that changes the mathematical meaning of an
operation — for example, using integer truncation instead of linear
interpolation in a lookup — is a semantic change and must be expressed in FMFL.
A decision that approximates an ideal mathematical operation in a particular
numeric system — for example, using round-to-nearest-even versus
round-toward-zero for intermediate products — is a realization decision and
belongs exclusively in the Implementation Profile.

An Implementation Profile that changes *which operations are performed*, *which
inputs are read*, or *what the output of an operation is under ideal arithmetic*
is not an Implementation Profile; it is a semantic specification that belongs
in FMFL.  A profile that specifies "use ``floor`` instead of ``round`` for this
signal" is a semantic change.  A profile that specifies "approximate the
``round`` operation using hardware-native rounding mode X" is a realization
parameter.

The Implementation Profile must never collapse into the Target Binding.  An
Implementation Profile entry answers "with what numeric precision?"; a Target
Binding entry answers "in what memory layout?".  These are orthogonal
questions.  Combining them in a single object creates an implicit dependency:
switching platforms would require changing the numeric precision, which would
invalidate any validation performed against the previous precision setting.

1.3.2.2  Typical Mistakes
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The following mistakes occur when realization concerns are not properly
isolated in the Implementation Profile.

A backend contains an ``if target == "embedded"`` branch that emits integer
arithmetic instead of floating-point arithmetic for division operations.  This
is a realization decision embedded in backend code rather than expressed in a
named Implementation Profile.  The consequence is that the realization behavior
is invisible to tools that inspect the profile, cannot be tested in isolation,
and cannot be reused across backends.  The correct approach is to define an
``"embedded_int16"`` profile that specifies integer arithmetic and to allow
any backend that supports the profile to emit the appropriate instructions.

A backend reads a ``build_for_production`` flag from the Build Policy and uses
it to switch between double-precision and single-precision arithmetic.  The
choice of numeric precision is a realization parameter, not a build
configuration parameter.  Mixing these concerns means that a build policy
change silently alters numerical results.  Numeric precision belongs in the
Implementation Profile; the Build Policy should only control non-semantic
output properties.

A backend selects a lookup implementation — linear vs. nearest-neighbor — based
on a ``fast_lookup`` flag passed through the Target Binding.  The choice of
interpolation algorithm is a semantic decision when it changes observable
output values.  It belongs in FMFL (via a different lookup primitive name) or,
if it is a pure approximation trade-off, in the Implementation Profile.  It
must not be embedded in the Target Binding, whose role is platform integration
rather than computation semantics.

1.3.2.3  Example
^^^^^^^^^^^^^^^^^

The following example illustrates the conceptual mapping from FMFL ``Real``
values to two different implementation types under two different profiles.

FMFL equation:

.. code-block:: text

   result = curve_lookup(@active_dataset.motor.torque_curve, speed)

Under the default profile ``"python_float64"``, ``speed`` and ``result`` are
realized as Python ``float`` (IEEE 754 double precision, 64 bits).  The lookup
result is computed using ``syn_curve_lookup_linear_clamp`` operating on
``numpy.float64`` arrays.  No rounding or saturation is applied.

Under a hypothetical future profile ``"embedded_q15"``, ``speed`` is realized
as a signed 16-bit integer with 15 fractional bits (Q1.15 format, range
approximately ``[-1, +1)``).  ``result`` is similarly a Q1.15 value.  The
lookup operates on a pre-scaled integer table.  The implementation of linear
interpolation uses integer multiply-and-shift arithmetic with configurable
rounding mode.

In both cases, the FMFL text is identical.  The mathematical intent is
identical.  Only the realization of that intent differs.  A conforming
Stage 2 implementation applies the profile uniformly across all expressions;
it does not make per-expression decisions about precision.

1.3.3  Target Binding — Platform Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Target Binding specifies the integration of generated code into a concrete
execution environment.  It defines the initialization routines the host invokes
before the first evaluation step, the scheduling context in which the
step function is called, the concrete types used for workspace storage and
inter-step state transfer, and the mechanism by which runtime services — the
parameter cache, the stimulation table, FMU step callbacks — are injected into
the generated function.

The Target Binding must not change model semantics, must not alter numeric
precision (that is exclusively a Layer 2 concern), and must not introduce
any constraint that changes the value produced by any equation for any fixed
set of inputs.  Holding FMFL and the Implementation Profile constant, a
change to the Target Binding must not alter the value produced by any
equation for any fixed set of inputs.

In the current implementation cycle, the Target Binding is implicit in the
Python backend.  The workspace is a ``dict[UUID, float]``, the step exchange
object is ``RunStepExchange``, and initialization is handled by the host.
These constitute the default Python binding.  They are not normative for other
targets.

1.3.3.1  Explanation
^^^^^^^^^^^^^^^^^^^^^

The Target Binding answers two questions that FMFL deliberately leaves open:
where does the computation run, and how does it connect to the surrounding
system.

FMFL defines a pure function: given a set of named input values, it produces a
set of named output values.  It does not specify where those values are stored,
who calls the function, or at what rate.  These are integration concerns.  They
vary across platforms — a desktop simulation stores values in a Python
dictionary; an embedded controller stores them in a statically allocated C
struct; a co-simulation interface stores them in an FMI 3.0 value reference
table.  None of these storage choices affect what the equations compute.

The separation is important because it allows the same FMFL model to be
deployed across multiple execution environments without modifying the model.
A model developed and validated against the default Python binding can be
deployed to an embedded target by supplying a different Target Binding and
regenerating the code.  If the Target Binding were embedded in the FMFL or in
the Implementation Profile, this cross-platform deployment would require
modifying the model, which would invalidate its validation status.

1.3.3.2  Typical Mistakes
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The following mistakes occur when platform integration concerns are not
isolated in the Target Binding.

A backend emits code that initializes the workspace dictionary to zero at the
start of the step function, reasoning that the host might not have initialized
it.  This changes the observable behavior of the function: inputs not present
in the workspace now silently read as zero rather than producing an
``KeyError``.  Initialization policy belongs in the Target Binding — or in the
host as specified by the Target Binding — not in the step function emitted by
the backend.

A backend emits code that applies physical unit conversion to inputs before
passing them to equations, because the host environment uses a different unit
convention.  Unit conversion is a semantic transformation.  If it is
necessary, it must be expressed in FMFL — either as explicit scaling operations
or as a defined port contract.  Embedding it in the Target Binding hides a
semantic transformation in a nominally non-semantic layer.

A backend conditionally emits a mutex acquire/release around the step function
body when a ``thread_safe`` flag is set in the Target Binding.  If the mutex
merely protects concurrent access without modifying values, this is a
legitimate Target Binding concern.  If the mutex causes certain inputs to be
read from a stale snapshot in a multi-threaded context, it changes observable
computation and is a semantic concern that must be documented in the FMFL or
the Target Binding specification.

1.3.3.3  Example
^^^^^^^^^^^^^^^^^

The following example shows how initialization logic is expressed in the Target
Binding without appearing in the FMFL or the generated step function.

The default Python binding specifies that the host is responsible for:

1. Allocating a ``dict[UUID, float]`` workspace before the first step.
2. Populating the workspace with initial values by executing the FMFL
   ``init:`` phase.
3. Constructing a ``RunStepExchange`` with the workspace, the previous-step
   snapshot (if feedback edges exist), the parameter cache, and the stimulation
   table.
4. Calling the generated ``run_equations(exchange)`` function once per step.
5. After ``run_equations`` returns, committing the workspace to the
   previous-step snapshot for the next step.

None of these responsibilities appear in the generated ``run_equations``
function.  The function body contains only the equation computations defined
in FMFL.  The setup and teardown logic belongs to the Target Binding
specification and is implemented by the host, not by the backend emitter.

A future embedded C binding would specify a different initialization contract:
a statically allocated ``ModelWorkspace`` struct, an ``init_workspace``
function generated from the FMFL ``init:`` phase, and a step function
``model_step(ModelWorkspace *ws, const ModelInputs *in, ModelOutputs *out)``
whose signature is defined by the Target Binding.  The equation logic inside
``model_step`` would be identical in structure to the Python equations; only
the surrounding integration code would differ.

1.3.4  Build Policy — Code Generation Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Build Policy specifies all aspects of the generated artifact that have no
effect on execution semantics.  It controls the structure of the output: single
versus multiple files, module layout, namespace organization, and the placement
of UUID constants.  It controls instrumentation: logging hooks, cycle counters,
and debug assertions injected around or within the step function.  It controls
tracing: signal-recording calls that capture intermediate values without
modifying them.  It controls output formatting: line length, comment style,
and generated-file header blocks.  It controls file naming and placement.

The Build Policy must not alter any computed value, must not select between
different numeric representations, and must not affect the execution semantics
of the generated step function for any valid input.  Two builds that differ
only in their Build Policy must produce identical computed values for all
inputs.  A Build Policy parameter that causes a backend to emit different
equations, different arithmetic operations, or different values for any input
is non-conformant and must be reclassified into the appropriate layer.

In the current implementation cycle, the Build Policy is fixed and not
configurable.  The emitted Python file has a standard header, UUID constants
at module level, and a single ``run_equations`` function.  No instrumentation
is implemented.

1.3.4.1  Explanation
^^^^^^^^^^^^^^^^^^^^^

The Build Policy exists to keep non-semantic output configuration from
contaminating the three meaningful layers.

Consider logging.  Adding a log call after each equation assignment might be
useful for debugging.  But a log call is not part of the computation; it does
not affect the values produced by the equations.  If the decision to add
logging were embedded in FMFL, every model would carry logging annotations
regardless of whether the target environment supports them.  If it were embedded
in the Implementation Profile, changing the logging configuration would
invalidate the numeric realization specification.  If it were embedded in the
Target Binding, enabling logging for a specific build would require defining a
new target binding for what is functionally the same platform.

The Build Policy is the correct location because it is the only layer whose
parameters are definitionally non-semantic: its parameters have no effect on
any computed value.  Two builds that differ only in their Build Policy must
produce functionally equivalent programs.  "Functionally equivalent" means
that for all valid inputs, both programs produce the same output values; side
effects such as log output are permitted to differ.

1.3.4.2  Typical Mistakes
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The following mistakes occur when build-time configuration concerns are not
isolated in the Build Policy.

A backend embeds a ``DEBUG`` constant into the FMFL ``equations:`` block as
a named value that controls conditional execution.  The value of ``DEBUG``
affects whether certain branches execute, making it a semantic input rather
than a build option.  Debug-conditional behavior must either be a permanent
part of the model (expressed in FMFL) or a build configuration option
expressed in the Build Policy that selects between two different code
structures with identical semantics.

A backend emits different equation code depending on whether the Build Policy
requests a release build, reasoning that release builds should omit
range-check assertions.  If the assertions detect and reject invalid values
that would cause downstream computation errors, removing them changes the
observable behavior of the program in the face of invalid inputs.  This is a
semantic change disguised as a build option.  Range checks that affect output
values must be expressed in FMFL; range checks that produce only diagnostic
output without affecting return values are a Build Policy concern and must be
controlled by the Build Policy exclusively.

A backend mixes file naming templates with workspace type definitions.  The
name of the output file is a Build Policy concern; the type used for the
workspace is a Target Binding concern.  Mixing them in a single configuration
object means that changing the output filename requires updating the same
descriptor that defines the workspace type, creating an unnecessary coupling.

1.3.4.3  Example
^^^^^^^^^^^^^^^^^

The following example shows how the Build Policy enables per-step logging
without changing the equations.

Under the default Build Policy, ``run_equations`` is emitted without any
logging:

.. code-block:: python

   def run_equations(exchange: RunStepExchange) -> None:
       ws = exchange.workspace
       ws[N_speed] = float(ws.get(N_x_input, 0.0)) * 2.5
       _kl = _pc.get(N_curve)
       if _kl is not None:
           ws[N_out_curve] = syn_curve_lookup_linear_clamp(_kl[0], _kl[1],
                                                           float(ws.get(N_speed, 0.0)))
       else:
           ws[N_out_curve] = 0.0

Under a hypothetical ``trace_all_signals`` Build Policy, the same equations
are emitted with non-intrusive signal capture calls injected after each
assignment:

.. code-block:: python

   def run_equations(exchange: RunStepExchange) -> None:
       ws = exchange.workspace
       ws[N_speed] = float(ws.get(N_x_input, 0.0)) * 2.5
       _trace("speed", ws[N_speed])
       _kl = _pc.get(N_curve)
       if _kl is not None:
           ws[N_out_curve] = syn_curve_lookup_linear_clamp(_kl[0], _kl[1],
                                                           float(ws.get(N_speed, 0.0)))
       else:
           ws[N_out_curve] = 0.0
       _trace("out_curve", ws[N_out_curve])

The ``_trace`` function is a read-only observer; it does not modify ``ws``.
The computed values of ``speed`` and ``out_curve`` are identical in both
versions.  The Build Policy controls whether ``_trace`` is emitted; the
FMFL, the Implementation Profile, and the Target Binding are unchanged.

--------------------------------------------------------------------------------
1.4  Execution Pipeline
--------------------------------------------------------------------------------

The normative code-generation pipeline has the following structure::

    ┌──────────────┐
    │  Model Graph │
    └──────┬───────┘
           │  Stage 1: semantic lowering
           │  (graph → complete FMFL text)
           ▼
    ┌─────────────┐
    │ FMFL (text) │  ◄── sole semantic input to Stage 2
    └──────┬──────┘
           │
           │  ┌───────────────────────┐
           │  │ Implementation Profile│  Layer 2
           │  │ (realization params)  │
           │  └───────────────────────┘
           │  ┌───────────────────────┐
           ├──► Target Binding        │  Layer 3
           │  │ (platform integration)│
           │  └───────────────────────┘
           │  ┌───────────────────────┐
           │  │ Build Policy          │  Layer 4
           │  │ (output configuration)│
           │  └───────────────────────┘
           │
           │  Stage 2: syntactic lowering
           │  (FMFL + layers 2–4 → target code)
           ▼
    ┌──────────────┐
    │ Target Code  │
    └──────────────┘

**Stage 2 must not access ``CompiledDataflow`` for semantic information.**
The FMFL text is its sole semantic input.  UUID-to-label mappings and
parameter-node identifiers may flow from ``CompiledDataflow`` into Stage 2
through the ``CodegenContext`` descriptor as structural identity data only, as
specified in section 3.4.  No equation logic, no wire-connection data, and no
typed equation dataclass field may cross the stage boundary.

**Why this constraint is necessary.**  When Stage 2 accesses ``CompiledDataflow``
for semantic data, two independent representations of the model's computation
exist simultaneously: the FMFL text and the graph.  These representations are
maintained by different code paths and will inevitably diverge as the codebase
evolves.  The FMFL text may be complete and correct while the backend produces
different output because it reads from the graph; or the graph may be updated
and the FMFL may be stale.  Neither divergence is detectable without executing
both and comparing results.  The only way to guarantee consistency is to
eliminate the second source: Stage 2 must read exclusively from the FMFL text.

In addition, a Stage 2 that accesses ``CompiledDataflow`` cannot be tested
independently.  Every test requires a fully compiled model graph.  A Stage 2
that reads only from FMFL text can be tested with synthetic inputs — any
string conforming to the minimal normal form — without any model, any compiler
pass, or any connection to the rest of the codebase.

**Consequences of violation.**  A backend that accesses ``CompiledDataflow``
for semantic information introduces a hidden dependency on the graph
representation.  Any change to ``CompiledDataflow`` — adding a field,
renaming a class, changing the wiring convention — can silently break the
backend.  The backend becomes de facto part of Stage 1, even though it
is architecturally positioned as Stage 2.  Backend independence, testability,
and multi-target reuse are all negated.

**Explicitly forbidden operations in Stage 2.**

1. Calling ``iter_equation_items(compiled)`` or any function that traverses
   ``CompiledDataflow.node_by_id`` or ``CompiledDataflow.incoming`` for any
   purpose related to equation resolution or dependency resolution.
2. Reading any field of any ``Eq*`` dataclass (``EqKennlinie``, ``EqOperator``,
   ``EqVarWire``, etc.).
3. Accessing ``CompiledDataflow.feedback_edges`` to infer ``prev`` semantics
   (``prev`` is already encoded in the FMFL text as ``prev(name)``).
4. Accessing ``CompiledDataflow.topo_order`` to infer or reconstruct evaluation
   order (the FMFL statement sequence already encodes topological order; no
   Stage-2 code may substitute its own ordering).
5. Using the type or attributes of any graph node (``Variable``,
   ``ElementaryInstance``, ``BasicOperator``) to determine what code to emit.
6. Importing from ``synarius_core.dataflow_sim.equation_walk`` in any backend
   or Stage-2 module.
7. Performing semantic inference from graph structure — that is, determining
   the meaning, type, or role of any value by examining graph topology,
   node types, or edge connectivity rather than by reading the explicit FMFL
   text.  Examples: inferring that a signal is a feedback value from
   ``feedback_edges``; inferring that a value is a lookup result from the
   block type of its source node; inferring evaluation order from
   ``incoming`` edge counts.

**Harmless-looking violations (explicitly forbidden).**  The following
patterns appear benign but violate the stage boundary unconditionally:

* *Reading ``CompiledDataflow`` just for validation:*  A backend that
  accesses ``CompiledDataflow`` to cross-check whether the FMFL text is
  consistent with the graph is performing semantic interpretation from
  graph data.  Validation of Stage-1 output is a Stage-1 responsibility.
  Stage 2 must trust the FMFL text and must not independently verify it
  against the graph.
* *Using ``CompiledDataflow`` for convenience:*  A backend that accesses
  ``CompiledDataflow`` because the information is "already available there"
  or "easier to read from the graph" introduces a structural dependency
  regardless of intent.  Convenience is not a justification.
* *Checking dependencies using original graph data:*  Any traversal of
  ``CompiledDataflow.incoming``, ``feedback_edges``, or ``topo_order``
  to determine how values relate to each other is dependency resolution
  from graph data, even when the FMFL text is also present and could
  supply the same information.

**Absolute rule.**  Any semantic interpretation performed outside the FMFL
text is forbidden, without exception and without regard to intent, convenience,
or transitional status.

Stage 1 is solely responsible for the completeness of the FMFL output.  If a
semantic rule cannot be expressed in the current FMFL grammar, Stage 1 must be
extended and, if necessary, the FMFL grammar must be extended.  Routing missing
semantic information through a side channel into Stage 2 is not permitted under
any circumstances.

--------------------------------------------------------------------------------
1.5  Default Semantics
--------------------------------------------------------------------------------

**Normative default (applies when no Implementation Profile is specified):**

   Untyped numeric FMFL values are interpreted as idealized real-valued
   quantities.  This interpretation is normative and independent of any
   backend, runtime, or target system.  There is no implicit quantization,
   no implicit overflow behavior, no implicit saturation, and no
   target-specific numeric assumption of any kind.

This rule is non-negotiable.  It is not overridable by a Target Binding, a
Build Policy, or by a backend implementation choice.  It is superseded only
by an explicit, named Implementation Profile (section 1.3.2) that is
documented, reviewed, and passed to Stage 2 through ``CodegenContext.profile``.
An Implementation Profile must be present and explicit before any deviation
from idealized real arithmetic is permitted; the absence of a profile is not
a license to apply target-platform numeric behavior silently.

A backend that applies any numeric approximation — including IEEE 754
truncation, wrap-around on overflow, or platform-specific NaN propagation — on
a signal that is governed by the default profile, without an explicit
Implementation Profile authorizing that behavior, is non-conformant.

The default profile corresponds to the idealized double-precision floating-point
mode of Simulink: arithmetic operations are defined over the mathematical real
numbers, not over any finite-precision number system.  This is the
Simulink-like default behavior: the abstract model is exact; only the
Implementation Profile introduces approximation.

The following behaviors are definitively excluded from the default profile.
None of them may appear in default-profile generated code without an explicit
Implementation Profile authorizing them:

* Fixed-point or integer arithmetic for any ``Real``-typed signal.
* Saturation on overflow for any arithmetic operation.
* Implicit rounding of intermediate results to a reduced precision.
* Clamping of lookup inputs or outputs beyond the behavior defined in
  :doc:`../compiler_lowering_rules` (``curve_lookup`` and ``map_lookup``
  clamp inputs to the defined axis range; this is part of their normative
  semantics, not a numeric approximation).
* Any behavior that depends on the target platform's numeric hardware.

**Division by zero.**  Division is defined for all non-zero denominators and
produces the exact mathematical quotient.  Division by zero is undefined under
idealized real arithmetic; the default profile does not prescribe a result.
Every implementation must document its treatment of division by zero in the
Target Binding specification.  Silent production of a platform-specific result
— for example, IEEE 754 ``+Inf`` or ``NaN`` — is not permitted without that
documentation.

**On the Python ``float`` implementation.**  The current Python backend uses
Python ``float`` (IEEE 754 double-precision, 64 bits).  This is not normative.
It is a conformant approximation of idealized real arithmetic: the difference
between an ideal ``Real`` computation and the corresponding IEEE 754
double-precision computation falls within the precision limits of the
representation and is accepted as a faithful approximation for engineering
purposes.  The use of Python ``float`` is an implementation detail of the
default Python Target Binding; it is not a property of the default semantics.
A future backend that uses a different numeric type for the same default profile
is conformant, provided that its behavior constitutes a faithful approximation
of idealized real arithmetic.

--------------------------------------------------------------------------------
1.6  Separation Constraints
--------------------------------------------------------------------------------

The following rules define what each layer may and must not contain, and which
cross-layer contaminations are explicitly forbidden.  These constraints are
normative.  An implementation that violates them has a design defect that must
be corrected before the implementation can be considered conformant.

**Layer 1 — FMFL.**  May contain: assignment statements, arithmetic
expressions, lookup function calls (``param_scalar``, ``curve_lookup``,
``map_lookup``), the delayed-feedback annotation ``prev``, and comment lines.
Must not contain: numeric type names, platform type names, backend-specific
runtime function names, instrumentation or logging calls, UUID literals,
memory addresses, initialization logic, scheduling directives, lifecycle
entry points, or any construct that references the execution environment.

**Layer 2 — Implementation Profile.**  May contain: numeric storage type
selectors (``float64``, ``float32``, ``int16``), rounding-mode identifiers,
overflow and saturation behavior specifications, per-signal type overrides, and
approximation-error bounds.  Must not contain: dataflow definitions, execution
logic (the set of operations performed, which inputs are read, what the output
of an operation is under ideal arithmetic), operation semantics, evaluation
order specifications, platform integration specifications, runtime type names,
storage layout definitions, workspace type definitions, file naming
conventions, or instrumentation configuration.  Must not alter which
computations are performed or in what order.

**Layer 3 — Target Binding.**  May contain: runtime type names, workspace type
definitions, step-function signatures, lifecycle entry-point names, service-
injection descriptors, and platform-specific initialization contracts.  Must
not contain: definitions of which operations are performed, in what order, on
what values, or with what numeric precision.  Must not modify computation
semantics.  Must not introduce behavioral changes — that is, must not cause
the generated step function to produce different output values for any fixed
set of inputs.  Numeric precision is owned by Layer 2; computation semantics
are owned by Layer 1.

**Layer 4 — Build Policy.**  May contain: file-name templates, line-length
limits, comment-style identifiers, instrumentation toggle flags, output
directory paths, and tracing configuration.  Must not contain anything that
affects the execution semantics of the generated code, must not select between
numeric representations, must not influence which computations are performed,
and must not contain semantic logic of any kind.  Conformance test: two runs
with identical Layer 1–3 inputs but differing Build Policies must produce
functionally equivalent programs.  A Build Policy that causes a backend to
emit different equations, different arithmetic operations, or different values
for any input is non-conformant and the misclassified parameter must be moved
to the appropriate layer.

**Cross-layer orthogonality rules.**  The following pairwise contaminations are
explicitly prohibited.

The Implementation Profile must not collapse into the Target Binding.  Numeric
precision (Layer 2) and platform type layout (Layer 3) are orthogonal concerns.
A single Implementation Profile must be applicable to multiple Target Bindings
(e.g. the same ``"python_float64"`` profile applies to both the default Python
binding and a hypothetical NumPy-array binding).  A single Target Binding must
be applicable with multiple Implementation Profiles (e.g. the embedded C
binding applies to both ``"float32"`` and ``"int16_q15"`` profiles).

The Build Policy must not be used to switch between numeric representations.
Selecting between double-precision and single-precision arithmetic is a Layer 2
decision.  A Build Policy flag labelled ``high_precision`` or
``production_mode`` that controls arithmetic precision is a Layer 2 concern
misplaced in Layer 4.

The Target Binding must not introduce numeric precision constraints.  A Target
Binding for an embedded platform that silently reduces all intermediate
computations to 32-bit float — without a corresponding Implementation Profile
entry — violates the normative default semantics of section 1.5 and is
non-conformant.

The FMFL layer must not carry any concern that belongs to Layers 2, 3, or 4.
An FMFL file that contains a ``float32`` type annotation is embedding a Layer 2
concern in Layer 1.  An FMFL file that references a platform-specific memory
address is embedding a Layer 3 concern.  An FMFL file that contains a logging
call is embedding a Layer 4 concern.  All three are violations.

================================================================================
2  Specifications
================================================================================

--------------------------------------------------------------------------------
2.1  FMF Specification
--------------------------------------------------------------------------------

The Functional Model Format (FMF) is a file-based packaging and exchange format
for libraries of functional modeling elements.  It is specified normatively in
:doc:`fmf_v0_1` and referenced in the v0.2 architecture clarification in
:doc:`architecture_and_pipeline_v0_2`, section I.

FMF uses XML for all normative library and element metadata.  A library is
rooted at a ``libraryDescription.xml`` manifest.  Each element is described
by an ``elementDescription.xml`` file in a dedicated subdirectory under
``components/``.  The element description declares ports, optional parameters,
and a ``<Behavior>`` block containing one or more references to FMFL files.
FMF is the packaging layer.  It does not carry behavioral semantics.
Behavioral semantics are carried exclusively by the referenced FMFL files.

FMF must not be used as an intermediate representation for behavioral content.
The role of machine-oriented behavioral IR between the graph and target code is
assigned to FMFL.  An XML encoding of FMFL semantics would duplicate the FMFL
layer in a different format and is not a permitted FMF extension.

Stage 1 reads FMF metadata to determine port names, parameter types, and
element identities.  The FMFL output of Stage 1 does not embed FMF content; it
references FMF-declared names as plain identifiers.

--------------------------------------------------------------------------------
2.2  FMFL Specification
--------------------------------------------------------------------------------

The Functional Model Language (FMFL) is a UTF-8, line-oriented, textual
intermediate representation of computational behavior.  Its concrete syntax is
Python-like — indented ``init:`` and ``equations:`` suites, no semicolons,
``#`` for comments — while its semantics are target-agnostic.  FMFL is
specified normatively in :doc:`fmfl_v0_1`.  The subsections below define the
normative properties of the FMFL subset produced by Stage 1 and consumed by
Stage 2 in the current implementation cycle.

2.2.1  Core Semantics
~~~~~~~~~~~~~~~~~~~~~~

FMFL defines two execution phases per compilation unit: the ``init:`` phase,
executed once after configuration, and the ``equations:`` phase, executed once
per evaluation step.  For the code-generation pipeline defined in this
document, Stage 2 processes the ``equations:`` phase exclusively.

The operations in the ``equations:`` phase are pure.  Given fixed inputs, the
same set of assignment statements produces the same set of output values.
There are no side effects.  The only construct that reads from outside the
current step is the ``prev(expr)`` annotation, which reads the committed state
snapshot of the previous step; this is a read of an immutable snapshot, not a
side effect on the current step.

Determinism is enforced through statement order.  Stage 1 emits statements in
a topological order derived from the dependency graph.  A statement assigning
value ``A`` appears before any statement that reads ``A`` as a non-``prev``
operand.  No processor of FMFL may reorder statements; see
:doc:`execution_semantics_v0_2`, section 4.

2.2.2  Minimal Normal Form
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The FMFL ``equations:`` block produced by Stage 1 is in a minimal normal form
with the following structural properties.

Every statement is either a comment line or a simple assignment of the form
``name = expr``.  There are no compound statements, conditionals, loops, or
multi-target assignments.  Every left-hand-side name appears at most once in the
block.

Every expression is one of: a name reference; a ``prev``-wrapped name
reference; a binary expression ``a op b`` with ``op`` in
``{"+", "-", "*", "/"}`` and both operands being name or ``prev`` references;
or a function call ``func(arg1, arg2, …)`` with each argument being a name or
``prev`` reference.  There are no nested binary expressions; compound
arithmetic is expressed through intermediate named assignments.  This flatness
follows from the one-assignment-per-node structure of the compiled dataflow
graph.

2.2.3  Default Typing
~~~~~~~~~~~~~~~~~~~~~~

FMFL v0.1 carries no explicit type annotations on names.  All untyped numeric
names denote values of the abstract semantic type ``Real``.  This is the
normative default typing rule.  ``Real`` denotes an idealized real-valued
quantity; it does not imply any concrete storage type.  The mapping from
``Real`` to a concrete representation is exclusively a concern of the
Implementation Profile (section 1.3.2).

The absence of a type annotation is correct and must remain valid indefinitely
for backward compatibility.  It is not a warning condition.  A future grammar
revision may introduce optional type annotations; their absence must not be
treated as an error by any conforming processor.

2.2.4  Future Extensions
~~~~~~~~~~~~~~~~~~~~~~~~~

.. note::

   The following extensions are future work.  They are not part of the current
   implementation cycle.  Nothing in this section is normative.

**Explicit model typing.**  A future revision of the FMFL grammar will
introduce optional type annotations on assignment targets and function
arguments, for example ``speed : Real = x_input * gain`` or
``index : Int = floor(speed)``.  The annotation syntax and the set of
supported type identifiers will be defined in a FMFL v0.2 grammar document.
The type system will be additive: unannotated names continue to denote
``Real``.

**Quantization.**  An Implementation Profile with quantization semantics will
map annotated or inferred types to fixed-point formats specified by word length,
fraction length, signedness, rounding mode, and overflow behavior.
Quantization is entirely a Layer 2 concern.  The FMFL text will not change
when a quantized profile is applied to a model.

**Fixed-point arithmetic.**  Fixed-point support requires both a quantization-
capable Implementation Profile and a backend that emits fixed-point arithmetic
instructions.  A backend receives the profile's format specifications via
``CodegenContext`` and emits type-specific arithmetic for each expression.
The FMFL parser and AST are unchanged.

**Dual typing.**  Dual typing separates the logical type — owned by the FMFL
layer, describing the mathematical nature of a value — from the implementation
type — owned by the Implementation Profile, describing its concrete realization.
A single FMFL model may therefore be realized simultaneously at multiple
precision levels.  A ``Real``-typed signal representing vehicle speed in m/s
may be realized as IEEE 754 double in a simulation kernel and as a Q1.15
fixed-point value in an embedded controller.  The logical type establishes the
correctness criterion; the implementation type describes the approximation.
Verification compares computed results against the logical type semantics.

================================================================================
3  Change Concept and Implementation Plan
================================================================================

--------------------------------------------------------------------------------
3.1  Current State Analysis
--------------------------------------------------------------------------------

The current implementation provides two code-generation entry points that
operate in parallel from ``CompiledDataflow``.

``codegen_kernel.generate_fmfl_document`` traverses ``CompiledDataflow`` via
``iter_equation_items`` and emits FMFL text.  As of the Stage-1 completeness
fix accompanying this concept document, it emits correct and complete FMFL
lines for all supported block types.  Its output is semantically complete and
ready to serve as the sole input to Stage 2.

``python_step_emit.generate_unrolled_python_step_document`` also traverses
``CompiledDataflow`` via ``iter_equation_items``.  It accesses ``EqKennlinie``,
``EqKennfeld``, and ``EqKennwert`` as primary semantic sources, reads
``in_x`` and ``in_y`` wire references directly, and emits lookup calls based
on dataclass type dispatch.  It does not call ``generate_fmfl_document``.  It
does not parse any FMFL text.  The FMFL output produced by
``codegen_kernel`` is not consumed anywhere in the current pipeline.

The stage boundary does not exist in the current implementation.  The FMFL
text is a diagnostic and documentation artifact; it is not a semantic input.
The two emitters can diverge silently if Stage 1 is updated without a
corresponding update to Stage 2.

--------------------------------------------------------------------------------
3.2  Target Architecture
--------------------------------------------------------------------------------

In the target architecture, the FMFL text produced by Stage 1 is the sole
semantic input to Stage 2.  ``python_step_emit`` will not call
``iter_equation_items``, will not access any field of any equation dataclass,
and will not import from ``equation_walk``.  Instead, it will call
``generate_fmfl_document`` to obtain the FMFL text, pass that text to
``fmfl_parser.parse_equations_block`` to obtain an ordered list of AST nodes,
and pass those nodes to a backend that implements ``FmflCodegenBackend``.

``CompiledDataflow`` remains available to Stage 2 through ``CodegenContext``,
but only through two narrow, strictly non-semantic channels: ``node_labels``
(a mapping from UUID to human-readable label, used only for comment
generation) and ``param_node_ids`` (the set of parameter-bound node UUIDs,
used only to resolve lookup-function argument names to their workspace keys).
No wire-connection data, no topological ordering data, and no equation
dataclass field may flow through ``CodegenContext`` into any backend.

The FMFL text and the Python output will be derived from a single shared
Stage-1 invocation.  Structural divergence between the two representations
becomes impossible once the migration is complete.

--------------------------------------------------------------------------------
3.3  Implementation Strategy
--------------------------------------------------------------------------------

3.3.1  Minimal FMFL Subset
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The FMFL parser for Stage 2 is not required to implement the complete FMFL
v0.1 grammar.  It is required to parse exactly the subset that Stage 1
currently emits, as defined by the minimal normal form in section 2.2.2:
comment lines, simple assignments, name references, ``prev``-wrapped name
references, binary expressions with a single operator, and single-level
function calls with name or ``prev`` arguments.

The parser must reject any input that does not conform to this subset with a
diagnostic that identifies the rejected construct and its line number.  Silent
degradation to a partial parse is not permitted.  An unknown construct that
Stage 1 does not currently emit must be rejected rather than silently treated
as a comment.

3.3.2  FMFL Parser
~~~~~~~~~~~~~~~~~~~

The parser is a new module ``synarius_core.dataflow_sim.fmfl_parser`` with the
following public interface::

    class FmflParseError(ValueError):
        """Raised when fmfl_text does not conform to the Stage-1 output subset."""

    def parse_equations_block(
        fmfl_text: str,
    ) -> list[AssignStmt | CommentStmt]:
        ...

The function accepts the complete FMFL document text and returns the ordered
list of statements from the ``equations:`` block.  The ``init:`` block is
parsed and discarded.  ``FmflParseError`` is raised with a message identifying
the offending line on any non-conforming input.

The parser may be implemented as a recursive-descent parser or as a
regex-based tokenizer followed by a rule-based AST builder.  A third-party
parser generator is not required and must not be introduced as a dependency.

3.3.3  AST Design
~~~~~~~~~~~~~~~~~~

The AST for the Stage-1 output subset is defined by the following frozen
dataclasses::

    @dataclass(frozen=True)
    class AssignStmt:
        target: str           # left-hand-side name
        rhs: Expr             # right-hand-side expression

    @dataclass(frozen=True)
    class BinOpExpr:
        left: Expr
        op: str               # one of: "+", "-", "*", "/"
        right: Expr

    @dataclass(frozen=True)
    class CallExpr:
        func: str             # e.g. "curve_lookup", "map_lookup", "param_scalar"
        args: tuple[Expr, ...]

    @dataclass(frozen=True)
    class NameExpr:
        name: str             # variable name or path, e.g. "@active_dataset.x.y"

    @dataclass(frozen=True)
    class PrevExpr:
        inner: Expr           # the delayed value (always a NameExpr in Stage-1 output)

    @dataclass(frozen=True)
    class CommentStmt:
        text: str             # comment content without leading "#"

    Expr = BinOpExpr | CallExpr | NameExpr | PrevExpr

All types are frozen dataclasses.  The AST is immutable after construction.
No reference to ``CompiledDataflow``, ``equation_walk``, or any Synarius model
type appears in the AST definition.

3.3.4  Backend Interface
~~~~~~~~~~~~~~~~~~~~~~~~~

The backend interface is defined in the new module
``synarius_core.dataflow_sim.codegen_backend``::

    class FmflCodegenBackend(Protocol):
        def emit_header(self, ctx: CodegenContext) -> str: ...
        def emit_statement(
            self,
            stmt: AssignStmt | CommentStmt,
            ctx: CodegenContext,
        ) -> list[str]: ...
        def emit_footer(self, ctx: CodegenContext) -> str: ...

    @dataclass
    class CodegenContext:
        fmfl_text: str                   # Stage-1 FMFL output (for diagnostics)
        profile: str                     # Layer 2: profile identifier
        binding: TargetBinding           # Layer 3: platform binding descriptor
        policy: BuildPolicy              # Layer 4: output configuration
        node_labels: dict[UUID, str]     # structural only: UUID → label
        param_node_ids: frozenset[UUID]  # structural only: parameter-bound UUIDs

    @dataclass
    class TargetBinding:
        name: str = "python_default"

    @dataclass
    class BuildPolicy:
        name: str = "python_default"

The backend interface receives the FMFL AST statement by statement.  It does
not receive the ``CompiledDataflow`` object.  ``node_labels`` and
``param_node_ids`` are the only information permitted to flow from
``CompiledDataflow`` into a backend, and only for annotation and workspace-key
resolution purposes respectively.

3.3.5  Python Backend Migration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Python backend is a new module
``synarius_core.dataflow_sim.python_backend`` that implements
``FmflCodegenBackend`` for the default profile ``"python_float64"``.

``emit_header`` emits the module docstring, the ``from __future__ import``
line, UUID constant definitions from ``ctx.node_labels``, and the conditional
import of ``lookup_ops`` when ``ctx.param_node_ids`` is non-empty.

``emit_statement`` maps each ``AssignStmt`` to one or more Python lines.  A
``NameExpr`` rhs becomes a ``float(ws.get(key, 0.0))`` read.  A ``BinOpExpr``
with ``/`` becomes a guarded division.  A ``CallExpr`` with
``func == "curve_lookup"`` becomes a call to
``syn_curve_lookup_linear_clamp``.  A ``CallExpr`` with
``func == "map_lookup"`` becomes a call to
``syn_map_lookup_bilinear_clamp``.  A ``CallExpr`` with
``func == "param_scalar"`` becomes a ``float(_pc.get(key, 0.0))`` read.  A
``PrevExpr`` routes the workspace read to the previous-step snapshot.

``emit_footer`` closes the function definition.

Once the Python backend is complete, ``python_step_emit`` is rebuilt as an
orchestrator that calls ``generate_fmfl_document``, then
``parse_equations_block``, then constructs a ``CodegenContext``, instantiates
``PythonBackend``, and assembles the output from the three emit calls.  The
direct ``iter_equation_items`` call is removed.

--------------------------------------------------------------------------------
3.4  Transitional Constraints
--------------------------------------------------------------------------------

.. warning::

   This section describes a **TEMPORARY** state.  The presence of
   ``CompiledDataflow``-derived data in ``CodegenContext`` is a **temporary
   architectural compromise** introduced because the FMFL grammar does not yet
   encode all information needed by backends.  **This compromise must be
   removed** as the FMFL grammar is extended.  Every allowance granted below
   carries an explicit elimination obligation.  No new ``CompiledDataflow``
   access may be added under the guise of a transitional constraint.

**Context.**  During the current migration cycle, ``CodegenContext`` is
constructed by Stage 1 and carries two narrow projections of
``CompiledDataflow`` into Stage 2.  Both projections are identifier/constant
data — not semantic data and not subject to semantic interpretation.  Their
presence does not relax the Stage-2 constraint (section 1.4); it defines the
only access that is currently permitted.  Any use of these fields beyond the
permitted operations defined below violates the stage boundary.

**TEMPORARY — Allowed (exhaustive list).  No field outside this list is
permitted regardless of intent.**

1. ``node_labels: dict[UUID, str]`` — a mapping from node UUID to
   human-readable label, derived from ``CompiledDataflow``.  Permitted use:
   generating comment annotations in emitted code, for example
   ``# KL1: std.Kennlinie (curve lookup)``.  This is an identifier constant;
   it carries no semantic information.  No branching, no value computation,
   no type dispatch may depend on it.  Reading ``node_labels`` to determine
   what code to emit is forbidden.

2. ``param_node_ids: frozenset[UUID]`` — the set of parameter-bound node
   UUIDs, derived from ``CompiledDataflow.param_bound_node_ids``.  Permitted
   use: resolving the first argument of ``curve_lookup``, ``map_lookup``, and
   ``param_scalar`` calls from FMFL path strings to workspace UUIDs.  This is
   a name-binding operation (string → UUID) using a pre-existing constant; it
   is not a semantic operation.  No equation logic, no branching on block type,
   and no inference about model structure may depend on it.

**Forbidden (absolute, not subject to transitional exception).  Any semantic
interpretation performed using ``CompiledDataflow`` data is forbidden,
regardless of which field is accessed.**

* Accessing any field of any ``Eq*`` dataclass (``EqKennlinie``,
  ``EqKennfeld``, ``EqKennwert``, ``EqOperator``, ``EqVarWire``, etc.).
* Importing from ``equation_walk`` in any Stage-2 module.
* Calling ``iter_equation_items`` or any traversal that reads
  ``CompiledDataflow.node_by_id`` or ``CompiledDataflow.incoming``.
* Accessing ``CompiledDataflow.feedback_edges``, ``CompiledDataflow.topo_order``,
  or any field not explicitly listed in the *Allowed* list above.
* Adding any new field to ``CodegenContext`` that is populated from
  ``CompiledDataflow``.

**Elimination schedule.**  As the FMFL grammar is extended:

* When label information is encoded in FMFL comments or metadata,
  ``node_labels`` must be removed from ``CodegenContext``.
* When parameter path resolution is encoded in FMFL ``param_scalar`` /
  ``curve_lookup`` / ``map_lookup`` argument syntax, ``param_node_ids`` must
  be removed from ``CodegenContext``.

The goal state — ``CodegenContext`` carrying no reference to
``CompiledDataflow`` — is non-negotiable.  It is not a nice-to-have; it is
the condition under which the stage boundary becomes testable in isolation.

--------------------------------------------------------------------------------
3.5  Explicit Non-Goals
--------------------------------------------------------------------------------

The following items are intentionally outside the scope of the current
implementation cycle.

A complete FMFL v0.1 parser covering the full grammar defined in
:doc:`fmfl_v0_1` is not in scope.  The parser covers only the Stage-1 output
subset defined in section 2.2.2.

A configurable Implementation Profile format is not in scope.  The profile
carries only the string identifier ``"python_float64"`` and is used solely to
select the Python backend.

Fixed-point arithmetic, quantization semantics, saturation, rounding modes, and
overflow handling are not in scope.

A C backend, a MicroPython backend, or any target other than Python is not in
scope.

Configurable instrumentation or tracing via the Build Policy layer is not in
scope.

Per-signal type annotations in FMFL are not in scope.

Dual typing is not in scope.

Profile validation against FMFL signal types is not in scope.

Scheduled or free-running mode–specific code-generation paths are not in scope.

--------------------------------------------------------------------------------
3.6  Future Evolution
--------------------------------------------------------------------------------

.. note::

   The following items are future work.  They are not part of the current
   implementation cycle.

**Implementation Profile expansion.**  Once the structural separation of the
four layers is stable, the Implementation Profile string identifier will be
replaced by a structured descriptor carrying explicit numeric type mappings,
rounding modes, and overflow specifications.  ``CodegenContext`` will carry the
parsed descriptor.  Backends will dispatch on profile fields rather than on the
profile string.

**Quantization system.**  A quantization-capable profile will introduce
per-signal fixed-point format specifications.  A new backend, or an extension
of the Python backend, will emit quantized arithmetic.  The FMFL layer, the
parser, and the AST will not change.  Only the ``emit_statement``
implementation will differ from the floating-point case.

**Dual typing.**  Implementing dual typing requires explicit type annotations
in FMFL, a type-inference pass over the AST, and a profile mechanism that maps
logical types to implementation types.  The backend will emit type-specific
arithmetic for annotated signals and fall back to the default for unannotated
ones.

**Additional backends.**  A C backend will implement ``FmflCodegenBackend``
against a ``TargetBinding`` descriptor that specifies the workspace struct, the
step function signature, and the C runtime API.  It will share the FMFL parser,
the AST definition, and the ``CodegenContext`` type with the Python backend.
The only backend-specific code will be the ``emit_*`` implementations.

**Full FMFL v0.1 parser.**  When Stage 1 is extended to emit constructs beyond
the current minimal subset, the parser will be extended by adding new node
types to the AST.  Existing node types will not be modified.  Backends that
do not handle a new node type will receive it as an ``UnknownStmt`` and may
emit a comment or raise a diagnostic.

**Removal of CompiledDataflow from CodegenContext.**  As the FMFL grammar is
extended to carry parameter path resolution and UUID binding natively,
``node_labels`` and ``param_node_ids`` will be derivable from the parsed FMFL
AST without consulting ``CompiledDataflow``.  At that point, ``CodegenContext``
will carry no reference to ``CompiledDataflow``, and the stage boundary will be
fully clean.

================================================================================
References
================================================================================

* :doc:`architecture_and_pipeline_v0_2` — normative two-stage pipeline
  requirement (§J).
* :doc:`fmfl_v0_1` — FMFL grammar, execution phases, standard-library surface.
* :doc:`execution_semantics_v0_2` — topological evaluation order (§4),
  delayed feedback (§5), determinism (§7).
* :doc:`../compiler_lowering_rules` — lookup-primitive semantics, validation
  rules, codegen mapping (§1–§6).
* :doc:`../attribute_dict` — ``AttributeDict`` and ``AttributeEntry``
  (Implementation Profile anchor for future per-attribute metadata).
* ``synarius_core.dataflow_sim.codegen_kernel`` — current Stage-1 emitter.
* ``synarius_core.dataflow_sim.python_step_emit`` — current Stage-2 prototype;
  to be replaced by the migration described in section 3.3.5.
* ``synarius_core.dataflow_sim.equation_walk`` — Stage-1 internal dataclasses;
  must not be imported by backends after migration.
