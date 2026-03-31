..
   Synarius core — model element type strings (MODEL.*).

================================================================================
Core type system (model ``type`` attribute)
================================================================================

:Status: Draft (synarius-core)
:Scope: Python data model in ``synarius_core.model`` — not FMF library identity

--------------------------------------------------------------------------------
Purpose
--------------------------------------------------------------------------------

Every object in the Synarius **core model tree** carries a stable, namespace-qualified **``type``** string so hosts (CLI, Studio, persistence, codegen) can classify instances without relying only on ``isinstance``.

* **``type``** describes the **role in the core model** (e.g. composite container, variable, operator, connector).
* **``type_key``** on ``ElementaryInstance`` names the **functional / library** implementation (e.g. a palette or FMF element key). It is orthogonal to ``type``.

Additional namespaces (e.g. ``LIB.*``, ``SIM.*``) may be specified later for non-model resources; this document defines the **``MODEL.*``** family only.

--------------------------------------------------------------------------------
Representation
--------------------------------------------------------------------------------

* **Storage:** ``type`` is a **non-virtual** entry in ``AttributeDict`` (stored value, not a computed virtual field).
* **Exposure:** ``exposed`` is **true** so consoles and serializers can list it like other public attributes.
* **Writability:** ``writable`` is **false**. Attempts to assign via ``BaseObject.set("type", …)`` **SHALL** raise ``PermissionError``.

The canonical Python API is ``ModelElementType`` in ``synarius_core.model.element_type`` (``str``-based ``Enum``). The string value stored and returned for ``get("type")`` **SHALL** match ``ModelElementType.<MEMBER>.value``.

--------------------------------------------------------------------------------
Reserved top-level attribute keys (model objects)
--------------------------------------------------------------------------------

Some top-level ``AttributeDict`` keys are **reserved namespaces** with normative meaning.

* **``pin``**: unified pin map for diagram/FMU connectivity metadata (see ``pin_model.rst``).
* **``fmu``**: optional subtree for FMU configuration on ``MODEL.ELEMENTARY`` instances (library/plugin convention; map of path, FMI metadata, ``extra_meta``, optional ``variables``, …). Access via ``get("fmu.path")``, etc.

  * **``fmu.variables``**: optional JSON-serializable **list** of dicts (FMI scalar-style metadata: ``name``, ``value_reference``, ``causality``, ``variability``, ``data_type``, …). Hosts **SHOULD** use the same ``name`` strings as diagram connector pins declared via ``fmu_ports`` / ``pin`` when a wire maps to that FMU variable. The catalog is metadata for inspect/runtime; binding remains diagram ``Connector`` endpoints plus ``pin`` names.

Hosts **SHOULD NOT** reuse reserved keys for unrelated purposes. Additional reserved keys **SHALL** be added only via specification updates.

--------------------------------------------------------------------------------
Normative values (v0.1)
--------------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Value
     - Python class
   * - ``MODEL.COMPLEX``
     - ``ComplexInstance``
   * - ``MODEL.ELEMENTARY``
     - ``ElementaryInstance`` (base only; prefer specialized types below when applicable)
   * - ``MODEL.VARIABLE``
     - ``Variable``
   * - ``MODEL.BASIC_OPERATOR``
     - ``BasicOperator``
   * - ``MODEL.CONNECTOR``
     - ``Connector``

FMU co-simulation blocks in the diagram use **``MODEL.ELEMENTARY``** with a stable ``type_key`` from an FMF library element (plugin-delivered) and the reserved ``fmu`` attribute subtree — not a distinct ``MODEL.*`` literal.

New ``MODEL.*`` literals **SHALL** be added only by extending ``ModelElementType`` and the corresponding constructors; hosts **SHALL NOT** rewrite ``type`` after construction.

--------------------------------------------------------------------------------
Evolution
--------------------------------------------------------------------------------

Future specifications may define further namespaces (e.g. ``LIB.<manifestName>`` for catalog entries). Those are **not** stored in this ``type`` field unless explicitly merged into a later core-wide resource model.
