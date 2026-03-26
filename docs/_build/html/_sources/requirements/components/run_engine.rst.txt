Run Engine Component Requirements
=================================

.. comp:: The run loop shall implement FMI-conform lifecycle handling including setupExperiment, enter/exit initialization, and cyclic doStep.
   :id: CORE-COMP-RUN-001

.. comp:: Simulation cycles should provide deterministic synchronization hooks.
   :id: CORE-COMP-RUN-002

.. comp:: A stimulus file should be loadable and applicable to mapped variables.
   :id: CORE-COMP-RUN-003

.. comp:: Stimulus signals from files should be freely mappable to variables.
   :id: CORE-COMP-RUN-004

.. comp:: Generic stimulation shall support at least ramp, sine, constant, and random signal generation.
   :id: CORE-COMP-RUN-005

.. comp:: MDF and CSV stimulus files should be supported for loading.
   :id: CORE-COMP-RUN-006

.. comp:: Stimulus and measurement data shall be held internally as pandas DataFrames.
   :id: CORE-COMP-RUN-007

.. comp:: Selected or all variables shall be measurable over simulation time and automatically persisted when simulation ends.
   :id: CORE-COMP-RUN-008

