Data Model Component Requirements
=================================

UML Diagram
-----------

.. uml:: data_model_uml.puml

The requirements on this page are intended as a supplement to the UML diagram above.
The software architecture of the data model must conform to this UML diagram.

.. comp:: Model aggregate with explicit infrastructure boundary
   :id: CORE-COMP-MODEL-012
   :status: Must

   The data model shall provide a top-level model/document aggregate that owns the root object and a shared model context.
   The model context shall host infrastructure services such as ID management, while domain objects remain focused on domain behavior.

.. comp:: Attached and detached object lifecycle
   :id: CORE-COMP-MODEL-013
   :status: Must

   Model objects may exist detached from a model context and become attached when inserted into a model.
   Attached objects shall have a model-registered ID; detached objects shall not be treated as persistent model members.

.. comp:: Central ID factory and registry operations
   :id: CORE-COMP-MODEL-014
   :status: Must

   A central ID factory shall provide ``new_id``, ``reserve``, ``contains``, and ``unregister`` operations.
   ID reservation shall reject duplicates within one model context.

.. comp:: ID lifecycle for load, delete, and paste/import
   :id: CORE-COMP-MODEL-015
   :status: Must

   Loading an existing model shall reserve all existing IDs and fail on duplicates.
   Deleting objects shall unregister IDs for the full removed subtree.
   Pasting within the same model shall remap IDs by default.

.. comp:: Tree-first navigation for CLI
   :id: CORE-COMP-MODEL-016
   :status: Must

   The data model shall support tree-oriented navigation semantics for CLI usage.
   Model objects shall provide ``get_root`` and ``get_root_model`` to resolve tree and model context ownership.

.. comp:: Node/Connector Model with Pins
   :id: CORE-COMP-MODEL-001
   :status: Must

   Elements provide defined inputs/outputs, and connections are modeled explicitly.

.. comp:: Stable Object Addressing
   :id: CORE-COMP-MODEL-002
   :status: Must

   Access by body key, name, display name, and ID is consistently supported.

.. comp:: ObjectHandler as Central Variable Layer
   :id: CORE-COMP-MODEL-003
   :status: Should

   Variable instances are consolidated so mapping and recorder features rely on a central structure.

.. comp:: Persistent Object Storage
   :id: CORE-COMP-MODEL-004
   :status: Must

   Objects are stored in a central SQLAlchemy + SQLite database, while model instances are represented in a model tree.
   A variable may appear multiple times in the model tree while still representing a single logical variable.

.. comp:: Persistent hash_name lifecycle
   :id: CORE-COMP-MODEL-005
   :status: Must

   The ``BaseObject`` shall persist ``id`` and ``hash_name``.
   ``hash_name`` shall be generated as ``<name>@<id>`` and updated when ``name`` changes while preserving the ``@<id>`` suffix.

.. comp:: Virtual attributes exposure and write rules
   :id: CORE-COMP-MODEL-006
   :status: Must

   ``AttributeDict`` shall expose ``id``, ``name``, ``hash_name``, and ``path`` as virtual attributes.
   ``id`` and ``hash_name`` shall be read-only; ``name`` shall be writable.
   ``path`` shall be read-only.

.. comp:: Child lookup and movement semantics
   :id: CORE-COMP-MODEL-007
   :status: Must

   ``ComplexInstance.get_child`` shall resolve children by ``id`` and by ``hash_name``.
   ``LocatableInstance`` shall not provide a ``move_to`` method.
   Position updates shall be performed via ``set_xy`` only.
   ``set_xy`` shall accept either a ``Point2D`` value or a 2-tuple ``(x, y)``.

.. comp:: BaseObject transient name and timestamps ownership
   :id: CORE-COMP-MODEL-008
   :status: Must

   ``BaseObject._name`` shall be transient and non-persistent.
   ``created_at`` and ``updated_at`` shall be managed by ``AttributeDict`` only.

.. comp:: Hash-indexed children map
   :id: CORE-COMP-MODEL-009
   :status: Must

   ``ComplexInstance`` shall maintain a dictionary of children keyed by ``hash_name``.

.. comp:: ElementaryInstance specializations
   :id: CORE-COMP-MODEL-010
   :status: Must

   ``ElementaryInstance`` shall be specialized by ``Variable`` and ``BasicOperator``.
   ``BasicOperator`` shall contain an ``operation`` field typed as a string enumeration
   with the values ``"+"``, ``"-"``, ``"*"``, and ``"/"`` to indicate the arithmetic operation.

.. comp:: Data model architecture compliance
   :id: CORE-COMP-MODEL-011
   :status: Must

   The software architecture of the data model shall conform to the UML diagram on this page.

