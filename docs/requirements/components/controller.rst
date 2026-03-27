Controller Component Requirements
=================================

.. comp:: Script Execution
   :id: CORE-COMP-CTL-001
   :status: Must

   ``execScript`` executes ``.pyp`` scripts deterministically line-by-line.

.. comp:: Type Registry for ``new``
   :id: CORE-COMP-CTL-002
   :status: Must

   Constructors for element types are centrally registered and extensible.

.. comp:: Controller Command Protocol
   :id: CORE-COMP-CTL-003
   :status: Must

   Commands are an implementation of the Controller Command Protocol.

.. comp:: ``load`` command support
   :id: CORE-COMP-CTL-004
   :status: Must

   The controller shall implement a ``load`` command that reconstructs models from protocol-compliant command stacks.
   The command shall support deterministic execution, configurable ID policy (``remap``/``keep``), and transactional rollback on failure.

