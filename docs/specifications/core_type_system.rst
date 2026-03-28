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

New ``MODEL.*`` literals **SHALL** be added only by extending ``ModelElementType`` and the corresponding constructors; hosts **SHALL NOT** rewrite ``type`` after construction.

--------------------------------------------------------------------------------
Evolution
--------------------------------------------------------------------------------

Future specifications may define further namespaces (e.g. ``LIB.<manifestName>`` for catalog entries). Those are **not** stored in this ``type`` field unless explicitly merged into a later core-wide resource model.
