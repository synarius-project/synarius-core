Parameter Data Model: DuckDB as Single Source of Truth (Provisional)
=====================================================================

Status
------

:Status: Provisional implementation concept
:Purpose: Interim chapter before integration into the main parameter data model specification
:Scope: ``synarius_core`` parameter subsystem architecture and migration direction


Goal
----

Define a minimal-complexity architecture where DuckDB is the **primary and only source of truth**
for parameter data, while model objects (``parameters``, ``data_set``, ``cal_param``) remain a
facade/API layer for CLI and GUI interaction.


Core decision (normative)
-------------------------

* DuckDB-backed repository state is canonical.
* Facade/model objects MUST NOT hold independent mutable parameter state.
* CLI and GUI operations MUST mutate/read through the same repository-backed guarded setters.


Architectural model
-------------------

Layers:

1. **Repository layer (DuckDB, canonical state)**
   * schema + transactions
   * guarded write operations
   * consistency checks
2. **Facade layer (model tree / virtual attributes)**
   * ``parameters`` root, ``data_set`` nodes, ``cal_param`` nodes
   * virtual attribute projection from repository rows
   * no parallel in-memory truth
3. **CCP/UI layer**
   * ``new``, ``set``, ``get``, ``print``
   * both CLI and GUI call the same facade setters


Ownership and identity
----------------------

* All mutable parameter state MUST be owned by ``data_set_id`` rows in DuckDB.
* ``data_source`` remains import/provenance metadata and MUST NOT own mutable state.
* ``cal_param`` object identity maps to repository keys (parameter id + dataset scope as defined by schema).


Read/write contract
-------------------

Reads:

* Virtual ``cal_param`` getters read from DuckDB on demand (or via bounded cache with invalidation).
* ndarray-returning reads MUST be read-only views or copies.

Writes:

* All writes go through guarded repository methods in one deterministic path.
* Invalid writes MUST raise deterministic errors.
* Silent corrections MUST NOT occur.


Consistency and reshape behavior
--------------------------------

* Dataset-centric consistency checks execute in repository-backed write path.
* ``set <cal_param>.shape ...`` and ``xN_dim`` mutate canonical DuckDB state.
* New cells created by reshape are initialized with ``0``.
* Strict monotonicity of relevant axes is enforced.


Undo/redo and command log
-------------------------

* Undo/redo remains command-driven.
* Each user-visible mutation MUST correspond to one deterministic command-log entry.
* Replaying commands against the same initial DB state MUST reconstruct equivalent state.


Minimal persistence/runtime profile
-----------------------------------

Early development profile:

* DuckDB may run in-memory (no file) initially.
* Same API must support file-backed DB later without semantic changes.
* No second state container in parallel.
* During normal operation, prefer process-local DB handling that avoids arbitrary external concurrent mutation.


Migration concept from current state
------------------------------------

1. Introduce DuckDB-backed ``ParametersRepository`` behind existing runtime facade API.
2. Move mutable value/shape/axis/meta state into DB tables only.
3. Keep model objects as virtual projections; remove duplicate mutable fields.
4. Enforce ndarray non-bypass rule at repository boundaries.
5. Keep CCP surface stable (no protocol redesign).


Acceptance criteria (implementation-ready)
------------------------------------------

* Changing DB state externally is reflected by subsequent facade reads (after defined refresh boundary).
* No mutable parameter write succeeds without repository guard path.
* No writable ndarray reference can mutate canonical state outside guarded writes.
* ``data_set_id`` is the only mutable-state owner in schema and query paths.
* CLI and GUI produce identical outcomes for the same mutation command.


Out of scope in this provisional chapter
----------------------------------------

* merge/diff workflows
* advanced diagnostics framework
* provenance graph and lifecycle state machine
* protocol redesign beyond current CCP verbs

