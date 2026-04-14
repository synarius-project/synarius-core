# `synarius_core.model` layout

The former monolith `data_model.py` is split into cohesive modules. `data_model.py` remains a **re-export shim** so `from synarius_core.model.data_model import …` keeps working.

| Module | Contents |
|--------|----------|
| `geometry.py` | `Point2D`, `Size2D` |
| `pin_helpers.py` | `Pin`, `PinDirection`, `PinDataType`, `pin_map_from_*`, internal pin/FMU helpers |
| `base.py` | `DuplicateIdError`, `DetachedObjectError`, `IdFactory`, `ModelContext`, `BaseObject`, `LocatableInstance` |
| `complex_instance.py` | `ComplexInstance` |
| `elementary.py` | `ElementaryInstance`, `BasicOperatorType`, `DEFAULT_FMU_LIBRARY_TYPE_KEY`, `elementary_fmu_block`, `elementary_diagram_subtitle_for_geometry` |
| `diagram_blocks.py` | `Variable`, `DataViewer`, `BasicOperator` |
| `signals.py` | `Signal`, `VariableMappingEntry`, `VariableDatabase`, `SignalContainer` |
| `connector.py` | `Connector` |
| `clone.py` | `_iter_subtree`, `_clone_for_paste` (paste/clone helpers used by `Model`) |
| `root_model.py` | `Model` aggregate |
| `diagram_geometry_constants.py` | Studio-aligned scene constants + shared helpers for `diagram_geometry` |

Dependency direction is roughly: geometry & pin helpers → base → complex → elementary → diagram blocks / signals / connector → clone → root model.
