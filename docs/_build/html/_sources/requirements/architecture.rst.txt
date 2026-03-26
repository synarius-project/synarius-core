Architecture Requirements
=========================

.. arch:: Commands received by the controller as strings shall be parsed deterministically, typed explicitly, and executed unambiguously with clear error propagation.
   :id: CORE-ARCH-001

.. arch:: The command set shall implement the Controller Command Protocol defined in the dedicated protocol specification.
   :id: CORE-ARCH-002

.. arch:: A two-stage code generation architecture shall be used: model graph -> line-oriented XML intermediate -> configurable language/codegen backend.
   :id: CORE-ARCH-003

.. arch:: All graph-model classes shall inherit from a common base class with unique object ID, parent reference, attribute dictionary, and body dictionary for immediate child elements.
   :id: CORE-ARCH-004

.. arch:: Data classes shall provide consistent interfaces for the Controller Command Protocol, including attribute getter/setter behavior.
   :id: CORE-ARCH-005

.. arch:: Process logic should follow fail-fast behavior and must not silently suppress errors.
   :id: CORE-ARCH-006

.. arch:: The architecture should separate analysis frontend and code generation backend via a replaceable backend interface.
   :id: CORE-ARCH-007

.. arch:: Core logic could be structured for high testability without GUI dependencies using reproducible script/fixture-based scenarios.
   :id: CORE-ARCH-008

