SPDM v0.1 (Synarius Parameter Data Model)
=========================================

Status: Draft mini-specification

Scope
-----

SPDM v0.1 defines a canonical, XML-based parameter model for Synarius that is:

- strongly typed
- semantically rich
- suitable for simulation and code generation
- variant-capable
- designed for loss-minimizing import/export with DCM2, CDFX, and PAR

1. Conceptual Model
-------------------

Parameter
~~~~~~~~~

A uniquely identified configuration/calibration item.

- Required: ``id``, ``typeRef``
- Optional: ``path``, ``unitRef``, ``quantity``, ``defaultValue``, ``constraints``, ``metadata``

ParameterSet
~~~~~~~~~~~~

A versionable container of concrete parameter values.

- Supports inheritance via ``baseSetRef``
- Contains values for parameter IDs
- May carry variant-specific overrides

ParameterValue
~~~~~~~~~~~~~~

Typed assignment for one parameter in a set.

- ``BaseValue``: unconditional
- ``Override``: conditional via variant condition
- Can carry coded and physical form where needed

Type system
~~~~~~~~~~~

- Scalar: ``int``, ``float``, ``bool``, ``string``
- Enum: named literals, optional coded representation
- Array: 1D..nD values
- Curve/Table/Map: axis-based values
- Struct: named fields with typed values

Units and quantities
~~~~~~~~~~~~~~~~~~~~

- Unit is referenced via ``unitRef``
- Physical quantity is optional metadata (example: torque)
- Conversion/coding metadata can be carried in metadata or extensions

Constraints
~~~~~~~~~~~

- Numeric ranges (min/max; hard/soft semantics)
- Validity ranges
- Enum domain restrictions
- Recursive constraints for arrays/structs

Variants
~~~~~~~~

- Conditions are named expressions in ``VariantModel``
- ``Override`` entries reference condition IDs
- Resolution is deterministic by priority
- Priority ties among active overrides are invalid

Defaults vs actual values
~~~~~~~~~~~~~~~~~~~~~~~~~

- ``defaultValue`` lives in ``ParameterDefinition``
- actual values live in ``ParameterSet``
- if no actual value exists, fallback is ``defaultValue``

Metadata
~~~~~~~~

Namespaced metadata may appear on package, parameter, set, and value levels.
Typical content:

- source origin descriptors
- author/timestamp/comment
- release/process flags

2. Design Principles
--------------------

1. Canonical model first: SPDM is normative internally.
2. Semantics/storage separation: model semantics are independent from XML carrier details.
3. Import information preservation: unmapped source details must be retained in metadata/extensions.
4. Explicit representation: coded and physical values may coexist.
5. Safe extensibility: versioned schema + namespace extensions + round-trip of unknown extensions.

3. XML Representation
---------------------

Root
~~~~

- Element: ``spdm:ParameterPackage``
- Namespace: ``urn:synarius:spdm:0.1``
- Required attributes: ``schemaVersion``, ``packageId``, ``createdAt``

Normative top-level order
~~~~~~~~~~~~~~~~~~~~~~~~~

1. ``TypeDefinitions``
2. ``UnitDefinitions``
3. ``ParameterDefinitions``
4. ``VariantModel``
5. ``ParameterSets``
6. ``Extensions`` (optional)

ParameterDefinition shape
~~~~~~~~~~~~~~~~~~~~~~~~~

- Required attributes: ``id``, ``typeRef``
- Optional attributes: ``unitRef``, ``quantity``, ``path``
- Optional children: ``DisplayName``, ``Description``, ``DefaultValue``, ``Constraints``, ``Metadata``

Value encoding
~~~~~~~~~~~~~~

- ``ScalarValue(kind,value)``
- ``EnumValue(literal,coded?)``
- ``ArrayValue(dimensions)`` with ``Item*``
- ``CurveValue`` with ``AxisX`` + ``Values``
- ``MapValue`` with ``AxisX`` + ``AxisY`` + ``Values``
- ``StructValue`` with recursive ``FieldValue(name, Value)``

Variant handling
~~~~~~~~~~~~~~~~

- ``VariantModel/Condition(id, expression)``
- ``Override(conditionRef, priority)``
- Resolve by descending priority, tie -> validation error

4. XSD (reference)
------------------

The following XSD is a structural baseline for SPDM v0.1.
Semantic checks (cross-reference validity, dimensional consistency, override conflict checks) are implemented by application validators in addition to XSD.

.. literalinclude:: examples/spdm/spdm-0.1.xsd
   :language: xml

5. Example SPDM file
--------------------

.. literalinclude:: examples/spdm/parameter_package_example.xml
   :language: xml

6. Mapping Considerations
-------------------------

DCM2 -> SPDM
~~~~~~~~~~~~

Easy:

- FESTWERT/FESTWERTE -> scalar/array
- KENNLINIE -> curve
- KENNFELD -> map/table

Ambiguous/loss-prone:

- implicit typing
- limited explicit unit/quantity information
- tool-specific flags/comments

CDFX -> SPDM
~~~~~~~~~~~~

Easy:

- rich typed XML, including coded/physical forms
- direct mapping for arrays/curves/maps/structures

Ambiguous/loss-prone:

- process/QM metadata outside SPDM core

PAR -> SPDM
~~~~~~~~~~~

Easy:

- straightforward key/value import for common scalar/vector cases

Ambiguous/loss-prone:

- tool-dependent dialect differences
- often incomplete units/constraints/variant semantics

Import policy:

- preserve source identifiers, comments, checksums in origin metadata for round-trip traceability

7. Implementation Notes
-----------------------

Parsing strategy
~~~~~~~~~~~~~~~~

1. XML parse stage
2. Typed IR construction
3. Semantic validation + normalization

Suggested internal structures
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``Package``, ``TypeDef``, ``UnitDef``, ``ParameterDef``, ``ParameterSet``, ``Condition``
- ``ValueNode`` tagged union (Scalar/Enum/Array/Curve/Map/Struct)
- parsed condition AST for deterministic evaluation

Versioning
~~~~~~~~~~

- ``schemaVersion`` follows semantic versioning
- minor = backward compatible
- major = potentially breaking

Validation
~~~~~~~~~~

- XSD for structure and primitive constraints
- semantic validator for:
  - unresolved references
  - dimension mismatch
  - enum/code mismatch
  - active override priority conflicts

8. Minimum Compliance Profile (v0.1)
------------------------------------

An implementation is SPDM v0.1 compliant if it can:

1. parse all core value forms (scalar/enum/array/curve/map/struct)
2. resolve defaults and set values deterministically
3. evaluate variant overrides with deterministic conflict handling
4. preserve origin metadata needed for round-trip conversion
5. reject structurally invalid XML and semantically invalid references
