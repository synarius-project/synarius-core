Data Model Component Requirements
=================================

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

