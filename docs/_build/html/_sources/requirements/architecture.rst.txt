Architecture Requirements
=========================

.. arch:: Deterministic Command Interpreter
   :id: CORE-ARCH-001
   :status: Must

   Commands are received as strings by the controller, parsed deterministically, typed explicitly, and executed unambiguously with clear error propagation.

.. arch:: Two-Stage Code Generator
   :id: CORE-ARCH-003
   :status: Must

   The model graph is first transformed into a line-oriented XML representation. Configurable generators then produce code for multiple use cases and languages.

.. arch:: Unified Data Model
   :id: CORE-ARCH-004
   :status: Must

   All graph-model classes inherit from a common base class with:

   - unique object ID
   - parent reference
   - attribute dictionary
   - body dictionary of immediate child elements

.. arch:: Consistent Interfaces for Data Classes
   :id: CORE-ARCH-005
   :status: Must

   Data classes provide methods needed by the Controller Command Protocol, including getter/setter behavior for attributes.

.. arch:: Fail-Fast Error Handling
   :id: CORE-ARCH-006
   :status: Should

   Process logic must avoid silent error suppression and provide traceable error messages.

.. arch:: Exchangeable Codegen Backends
   :id: CORE-ARCH-007
   :status: Should

   A clear interface exists between analysis frontend and codegen backend.

.. arch:: High Testability
   :id: CORE-ARCH-008
   :status: Could

   Core logic can run without GUI dependencies and supports reproducible script-/fixture-based tests.

.. arch:: Controller Command Protocol
   :id: CORE-ARCH-002
   :status: Must

   Commands are an implementation of the Controller Command Protocol (see dedicated protocol specification).

