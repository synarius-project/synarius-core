import unittest

from synarius_core.model.connector_routing import (
    auto_orthogonal_bends,
    bends_absolute_to_relative,
    bends_relative_to_absolute,
    canonicalize_absolute_bends,
    encode_bends_from_polyline,
    orthogonal_drag_segments,
    orthogonal_polyline,
    polyline_for_endpoints,
    remove_axis_aligned_spikes,
    simplify_axis_aligned_polyline,
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

    def test_orthogonal_polyline_no_spurious_detour_when_y_drift_small(self) -> None:
        """Aligning vertical leg with target x must not add detour vertices on float noise."""
        sx, sy, tx, ty = 0.0, 100.0, 200.0, 50.0
        b = [tx, ty + 1e-5]
        poly = orthogonal_polyline(sx, sy, tx, ty, b)
        self.assertEqual(len(poly), 3, poly)
        self.assertAlmostEqual(poly[-1][0], tx)
        self.assertAlmostEqual(poly[-1][1], ty)

    def test_orthogonal_polyline_same_column_small_y_gap_no_detour(self) -> None:
        """Same x as target with a few px Δy (pin vs knee) must not use the same-x detour."""
        sx, sy, tx, ty = 0.0, 100.0, 200.0, 50.0
        b = [tx, ty + 3.0]
        poly = orthogonal_polyline(sx, sy, tx, ty, b)
        self.assertLessEqual(len(poly), 4, poly)
        self.assertAlmostEqual(poly[-1][0], tx)
        self.assertAlmostEqual(poly[-1][1], ty)

    def test_orthogonal_polyline_micro_align_px_near_tx_same_row(self) -> None:
        """Knee x slightly off target pin x (grid snap) but same row as target; no detour."""
        sx, sy, tx, ty = 0.0, 100.0, 200.0, 50.0
        b = [199.5, 50.0]
        poly = orthogonal_polyline(sx, sy, tx, ty, b)
        self.assertLessEqual(len(poly), 4, poly)
        self.assertAlmostEqual(poly[-1][0], tx)
        self.assertAlmostEqual(poly[-1][1], ty)

    def test_polyline_for_endpoints_simplifies(self) -> None:
        sx, sy, tx, ty = 0.0, 0.0, 200.0, 40.0
        messy = [(sx, sy), (30.0, 0.0), (60.0, 0.0), (60.0, 40.0), (tx, ty)]
        enc0 = encode_bends_from_polyline(sx, sy, tx, ty, messy)
        p = polyline_for_endpoints(sx, sy, tx, ty, enc0)
        self.assertLessEqual(len(p), len(messy))

    def test_remove_axis_aligned_spikes_vertical_tail(self) -> None:
        """Runtime log shape: same *x*, middle *y* outside span of neighbours (vertical tail)."""
        pts = [
            (210.0, 78.75),
            (241.5, 78.75),
            (241.5, 31.5),
            (241.5, 47.25),
            (288.75, 47.25),
        ]
        got = remove_axis_aligned_spikes(pts)
        self.assertEqual(len(got), 4, got)
        self.assertAlmostEqual(got[2][0], 241.5)
        self.assertAlmostEqual(got[2][1], 47.25)

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
        mx = (x1 + x2) * 0.5
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

    def test_simplify_axis_aligned_drops_collinear(self) -> None:
        pts = [(0.0, 0.0), (30.0, 0.0), (60.0, 0.0), (60.0, 40.0), (200.0, 40.0)]
        sim = simplify_axis_aligned_polyline(pts)
        self.assertEqual(
            sim,
            [(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (200.0, 40.0)],
        )

    def test_canonicalize_strips_redundant_support_from_poly(self) -> None:
        sx, sy, tx, ty = 0.0, 0.0, 200.0, 40.0
        messy = [(sx, sy), (30.0, 0.0), (60.0, 0.0), (60.0, 40.0), (tx, ty)]
        enc0 = encode_bends_from_polyline(sx, sy, tx, ty, messy)
        enc = canonicalize_absolute_bends(sx, sy, tx, ty, enc0)
        poly = orthogonal_polyline(sx, sy, tx, ty, enc)
        self.assertLessEqual(len(poly), len(messy))
        self.assertAlmostEqual(poly[0][0], sx)
        self.assertAlmostEqual(poly[-1][0], tx)

    def test_bends_relative_roundtrip(self) -> None:
        sx, sy = 10.0, 20.0
        abs_b = [100.0, 50.0, 200.0]
        rel = bends_absolute_to_relative(sx, sy, abs_b)
        self.assertAlmostEqual(rel[0], 90.0)
        self.assertAlmostEqual(rel[1], 30.0)
        self.assertAlmostEqual(rel[2], 190.0)
        back = bends_relative_to_absolute(sx, sy, rel)
        for a, b in zip(abs_b, back):
            self.assertAlmostEqual(a, b)

    def test_connector_stored_relative_moves_with_source(self) -> None:
        from uuid import uuid4

        from synarius_core.model import Connector

        c = Connector(
            name="c",
            source_instance_id=uuid4(),
            source_pin="out",
            target_instance_id=uuid4(),
            target_pin="in",
            orthogonal_bends=[90.0, 30.0],
        )
        p0 = c.polyline_xy((10.0, 20.0), (200.0, 50.0))
        p1 = c.polyline_xy((40.0, 20.0), (200.0, 50.0))
        self.assertAlmostEqual(p0[1][0] + 30.0, p1[1][0])
        self.assertAlmostEqual(p0[1][1], p1[1][1])


if __name__ == "__main__":
    unittest.main()
