import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.model.diagram_geometry import (  # noqa: E402
    _VARIABLE_WIDTH,
    variable_diagram_block_width_scene,
)
from synarius_core.model.data_model import Model, Variable  # noqa: E402


class DiagramGeometryWidthTest(unittest.TestCase):
    def test_short_name_uses_minimum_width(self) -> None:
        w = variable_diagram_block_width_scene("x")
        self.assertAlmostEqual(w, _VARIABLE_WIDTH, places=4)

    def test_long_name_widens_block(self) -> None:
        name = "very_long_variable_identifier_name"
        w_long = variable_diagram_block_width_scene(name)
        w_short = variable_diagram_block_width_scene("a")
        self.assertGreater(w_long, w_short)

    def test_variable_diagram_block_width_virtual(self) -> None:
        root = Model.new("main").root
        v = Variable(name="ab", type_key="Variable")
        root.paste(v)
        self.assertGreaterEqual(float(v.get("diagram_block_width")), _VARIABLE_WIDTH)
        self.assertFalse(v.attribute_dict.exposed("diagram_block_width"))
        self.assertFalse(v.attribute_dict.writable("diagram_block_width"))


if __name__ == "__main__":
    unittest.main()
