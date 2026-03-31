"""FMU file inspection and model binding (FMI 2.0 ``modelDescription.xml`` in ``.fmu`` ZIP).

Model-level FMU configuration on :class:`~synarius_core.model.ElementaryInstance` lives under the
``fmu`` attribute subtree (see :func:`~synarius_core.model.elementary_fmu_block`). Use the
controller commands ``fmu inspect``, ``fmu bind``, and ``fmu reload`` for CLI workflows, or
``get`` / ``set`` / ``lsattr`` on ``fmu.*`` and ``pin.*`` paths.

There is no separate ``fmu set`` verb: scalar and nested mapping fields use the generic ``set``
command (for example ``set <ref>.fmu.path "…"``). List-valued ``fmu.variables`` is best updated
via ``fmu bind`` / ``fmu reload`` or by replacing the whole list with a safely parsed literal.
"""

from synarius_core.fmu.bind import (
    FmuBindError,
    bind_elementary_from_fmu_path,
    bind_fmu_inspection_to_elementary,
    scalar_variables_to_fmu_ports,
)
from synarius_core.fmu.inspection import FmuInspectError, inspect_fmu_path, parse_model_description_xml

__all__ = [
    "FmuBindError",
    "FmuInspectError",
    "bind_elementary_from_fmu_path",
    "bind_fmu_inspection_to_elementary",
    "inspect_fmu_path",
    "parse_model_description_xml",
    "scalar_variables_to_fmu_ports",
]
