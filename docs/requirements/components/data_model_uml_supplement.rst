Data Model UML Supplement Requirements
======================================

.. comp:: Persistent hash_name lifecycle
   :id: CORE-COMP-MODEL-005
   :status: Must

   The ``BaseObject`` shall persist ``id`` and ``hash_name``.
   ``hash_name`` shall be generated as ``<name>@id<id>`` and updated when ``name`` changes while preserving the ``@id<id>`` suffix.

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
