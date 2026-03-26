Run Engine Component Requirements
=================================

.. comp:: FMI-Conform Run Loop
   :id: CORE-COMP-RUN-001
   :status: Must

   The run loop implements setupExperiment, enter/exit initialization, and cyclic doStep.

.. comp:: Cycle Synchronization
   :id: CORE-COMP-RUN-002
   :status: Should

   After each simulation cycle, defined synchronization hooks are available.

.. comp:: File-Based Stimulation
   :id: CORE-COMP-RUN-003
   :status: Should

   A stimulus file can be loaded and its signals can drive variable stimulation.

.. comp:: Stimulus Mapping
   :id: CORE-COMP-RUN-004
   :status: Should

   Stimuli from a loaded file can be freely mapped to variables.

.. comp:: Generic Stimulation
   :id: CORE-COMP-RUN-005
   :status: Must

   Variables can be stimulated generically using ramp, sine, constant, and random signals.

.. comp:: Stimulus File Loading
   :id: CORE-COMP-RUN-006
   :status: Should

   MDF and CSV stimulus files can be loaded.

.. comp:: Internal Dataframe Representation
   :id: CORE-COMP-RUN-007
   :status: Must

   Stimulus and measurement files are internally represented as pandas DataFrames.

.. comp:: Simulation Measurement and Persistence
   :id: CORE-COMP-RUN-008
   :status: Must

   Selected or all variables are measured over simulation time and automatically persisted when simulation ends.

