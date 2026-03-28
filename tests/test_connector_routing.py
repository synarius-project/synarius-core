import unittest

from synarius_core.model.connector_routing import (
    auto_orthogonal_bends,
    encode_bends_from_polyline,
    orthogonal_drag_segments,
    orthogonal_polyline,
    polyline_for_endpoints,
)


class ConnectorRoutingTest(unittest.TestCase):
    def test_auto_then_expand_matches_hvh(self) -> None:
        sx, sy, tx, ty = 0.0, 0.0, 200.0, 80.0
        b = auto_orthogonal_bends(sx, sy, tx, ty)
        self.assertEqual(len(b), 2)
        x_mid, y_end = b[0], b[1]
        self.assertAlmostEqual(y_end, ty)
        poly = orthogonal_polyline(sx, sy, tx, ty, b)
        self.assertGreaterEqual(len(poly), 3)
        self.assertAlmostEqual(poly[0][0], sx)
        self.assertAlmostEqual(poly[0][1], sy)
        self.assertAlmostEqual(poly[-1][0], tx)
        self.assertAlmostEqual(poly[-1][1], ty)
        self.assertAlmostEqual(poly[1][0], x_mid)
        self.assertAlmostEqual(poly[1][1], sy)

    def test_encode_roundtrip(self) -> None:
        sx, sy, tx, ty = 10.0, 20.0, 300.0, 120.0
        b = [150.0, 120.0]
        poly = orthogonal_polyline(sx, sy, tx, ty, b)
        b2 = encode_bends_from_polyline(sx, sy, tx, ty, poly)
        self.assertEqual(len(b2), 2)
        self.assertAlmostEqual(b2[0], 150.0)
        self.assertAlmostEqual(b2[1], 120.0)

    def test_polyline_for_endpoints_empty_uses_straight_when_no_knee(self) -> None:
        p = polyline_for_endpoints(0.0, 0.0, 50.0, 0.0, [])
        self.assertEqual(len(p), 2)

    def test_orthogonal_drag_segments_on_actual_polyline(self) -> None:
        sx, sy, tx, ty = 0.0, 0.0, 200.0, 80.0
        b = [100.0, 80.0]
        segs = orthogonal_drag_segments(sx, sy, tx, ty, b)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0][4], 0)
        self.assertEqual(segs[0][5], "x")
        self.assertEqual(segs[1][4], 1)
        self.assertEqual(segs[1][5], "y")
        x1, y1, x2, y2, _, _ = segs[0]
        self.assertAlmostEqual(x1, x2)
        mx, my = (x1 + x2) * 0.5, (y1 + y2) * 0.5
        self.assertAlmostEqual(mx, 100.0)

    def test_connector_model_polyline_xy(self) -> None:
        from uuid import uuid4

        from synarius_core.model import Connector

        c = Connector(
            name="c",
            source_instance_id=uuid4(),
            source_pin="out",
            target_instance_id=uuid4(),
            target_pin="in",
            orthogonal_bends=[100.0, 50.0],
        )
        poly = c.polyline_xy((0.0, 0.0), (200.0, 50.0))
        self.assertGreaterEqual(len(poly), 2)


if __name__ == "__main__":
    unittest.main()
