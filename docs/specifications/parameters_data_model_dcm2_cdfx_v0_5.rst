Parameter data model (DCM2/CDFX) for synarius-core v0.5
========================================================

Status
------

:Status: Draft concept (hardening iteration)
:Supersedes: ``parameters_data_model_dcm2_cdfx_v0_4.rst``
:Scope: ownership and mutation safety hardening


1. Purpose of this iteration
----------------------------

This iteration keeps the existing architecture and hardens two critical rules:

* ``data_set`` ownership of mutable state.
* ndarray exposure safety for guarded-write integrity.

No redesign is introduced.


2. Hard ownership rule (normative, unambiguous)
-----------------------------------------------

Definitions:

* ``data_source``: imported external artifact metadata.
* ``data_set``: mutable working parameter state.

Normative ownership:

* All mutable parameter state MUST be owned by ``data_set_id``.
* ``data_source`` MUST NEVER own mutable parameter state.
* Any schema/API path that implies mutable-state ownership by ``data_source`` is invalid in this model.

Operational implications:

* All mutable parameter rows (base + detail tables) MUST be addressable by ``data_set_id``.
* ``data_source`` references are informational/provenance linkage only.
* Query and mutation APIs MUST resolve mutable state through dataset scope.

Rationale:

* Prevents dual ownership, inconsistent updates, and ambiguous query semantics.


3. Guarded-write integrity vs ndarray mutability
------------------------------------------------

Problem statement:

* ``numpy.ndarray`` is mutable.
* Returning mutable ndarray references can bypass setter/guard logic.

Normative safety rule:

* Repository MUST NOT expose mutable ndarray references that can bypass guarded mutation.

Allowed read return modes:

* read-only ndarray view (``arr.flags.writeable = False``), or
* defensive copy.

Forbidden behavior:

* Returning writable references to repository-owned arrays.
* Any mutation path that changes persistent state without guarded setters/commands.

Mutation contract:

* Persistent updates MUST occur only through guarded mutation APIs (CLI/GUI parity unchanged).
* CLI and GUI MUST use the same guarded setter paths.


4. Deterministic error behavior (applies to both hardening points)
------------------------------------------------------------------

* Violations of ownership or ndarray safety rules MUST raise deterministic errors.
* Silent fallback, implicit correction, or hidden mutation MUST NOT occur.


5. Compatibility with prior iteration
-------------------------------------

All v0.4 rules remain in force unless tightened by this document.

In particular, unchanged:

* ``parameters`` as API/facade,
* repository abstraction,
* virtual ``cal_param`` attributes,
* guarded writes,
* dataset-centric consistency,
* replayable deterministic command logging.


6. Current implementation alignment
-----------------------------------

Current core implementation aligns with this hardening as follows:

* ``ParametersRepository`` is DuckDB-backed and used as the canonical mutable-state backend.
* Runtime default is process-local in-memory DuckDB (no shared external DB handle in normal operation).
* ndarray reads at repository boundaries are returned as copy or explicitly read-only arrays.
* Guarded mutation path remains mandatory for persistent changes.


7. DCM metadata mapping (implemented subset)
--------------------------------------------

The current DCM importer intentionally supports a focused subset for deterministic ingest.
Besides numeric payload and axis points, the following metadata is mapped:

* Parameter-level

  * ``LANGNAME`` -> ``display_name``
  * ``EINHEIT`` -> ``unit``
  * ``VAR`` / ``FUNKTION`` -> ``source_identifier`` (concatenated key/value parts)

* Axis-level

  * ``LANGNAME_X`` -> axis 0 name
  * ``LANGNAME_Y`` -> axis 1 name
  * ``EINHEIT_X`` -> axis 0 unit
  * ``EINHEIT_Y`` -> axis 1 unit

Storage/model surface:

* Parameter metadata remains in ``parameters_all``.
* Axis metadata is stored in ``parameter_axis_meta`` keyed by ``(parameter_id, axis_index)``.
* Runtime virtual attributes expose these fields as
  ``xN_name`` and ``xN_unit`` (with ``N`` in ``1..5``) for CLI/GUI parity.

Behavior rules:

* Missing metadata is represented as empty string.
* Metadata parse is case-insensitive by keyword.
* For malformed recognized metadata lines (keyword without value), parsing fails deterministically.
* Existing DCM files without metadata remain valid and import-compatible.

