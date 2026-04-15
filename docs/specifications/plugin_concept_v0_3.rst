..
   Synarius plugin documentation — hub page (v0.3).

================================================================================
Synarius plugins (v0.3)
================================================================================

:Status: Living specification (architecture + API)
:Version: 0.3

This set of pages describes how **Synarius plugins** extend compilation and runtime behavior,
how they relate to **Synarius libraries** (see :doc:`library_catalog`) and the **Synarius core**
(controller, CCP), and the concrete **Python contracts** that ``synarius_core`` implements and
third-party plugins follow.

**Contents**

.. toctree::
   :maxdepth: 2

   plugin_concept_v0_3_technical
   plugin_concept_v0_3_plugin_api

* :doc:`plugin_concept_v0_3_technical` — Architecture: responsibilities of the library, plugins,
  registries, and controller dispatch; CCP navigation; ``type_key`` rules.
* :doc:`plugin_concept_v0_3_plugin_api` — Plugin API: ``pluginDescription.xml``, discovery,
  capabilities, and the ``SynariusPlugin`` contribution model (compile passes, element-type
  handlers, simulation runtime).

Plugins **must not** redefine FMFL model semantics; semantics stay in FMFL and library
descriptors. Plugins supply processing, binding, and execution.
