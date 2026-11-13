"""Creating a control point from a target-space click must not move the drawn image.

Pyre draws the source image with the forward map (source triangulation), while ``InverseTransform`` of a mesh uses
the target triangulation. On RC1 0004/0005 (Quantized ds32, 2026-11-13) the two differed by up to ~235 px, so a new
point placed with the inverse map pinned a different source pixel under the cursor and the image jumped.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import nornir_imageregistration
import numpy as np
from nornir_imageregistration.transforms import factory
from pyre import mesh_hull_affine
from pyre.controllers.transformcontroller import TransformController
from pyre.space import Space

# MeshTransform line of RC1 0005 -> 0004 (Quantized, ds32) as saved by Pyre.
RC1_0005_0004_MESH = (
    "MeshTransform_double_2_2 vp 156 0.202934197 0.1855532634 3302.018 2278.521 0.2176207865 0.3441741314 "
    "3006.939 1750.531 0.0776978245 0.3779634162 3438.489 1430.546 0 0.404766301 3670.804 1224.242 0.5139801511 "
    "0.2673975759 2132.805 2458.644 0.6300341762 0.2406453797 1779.448 2720.815 0.6210646345 0.0958947182 2033.697 "
    "3209.943 0.512498829 0 2551.632 3382.896 0.3719892447 0.045353825 2935.676 3013.058 0.2807620389 0.0402340497 "
    "3263.781 2891.775 0.1394740766 0.1263035632 3612.726 2389.219 0.0727311492 0.2638722375 3626.906 1818.961 "
    "0.42000226 0.1232009703 2675.644 2817.511 0.8624161396 0.1749415747 1088.416 3289.49 0.883551208 0.1850114824 "
    "1014.028 3292.221 0.7894927699 0.2045568173 1288.18 3083.869 0.8763620682 0.355982499 1026.063 2998.923 "
    "0.7232058663 0.2276461381 1479.561 2908.565 0.7370920984 0.3754512659 1518.204 2802.09 0.6929628056 "
    "0.4295623649 1559.318 2493.763 0.8538796794 0.3181618006 1138.947 3080.708 0.451956597 0.6707676055 2090.247 "
    "1327.178 0.4050126064 0.4809807417 2491.906 1958.207 0.4328962295 0.5727364424 2277.959 1656.499 0.5044726772 "
    "0.8673430443 1665.224 670.549 0.2776015465 0.8331561638 2499.16 551.354 0.1629606805 0.7821729047 2959.076 "
    "601.311 0.0978026973 0.6772848035 3301.874 895.049 0.2081899087 0.5657072993 3061.201 1411.772 0.9378430419 "
    "0.8735002009 113.861 1231.384 1 0.6371688813 209.431 2129.611 0.8836366688 0.4973225767 796.399 2486.284 "
    "0.7394292909 0.5050110932 1290.85 2277.494 0.5441991738 0.3780657338 2010.77 2291.702 0.7483322967 "
    "0.8002939322 858.34 1256.239 0.7279925392 0.9762311666 684.668 603.185 0.6443827072 0.8352328072 1193.191 "
    "943.461 0.4141678778 0.9559037744 1884.121 271.159 0.4886408985 1 1586.375 192.497 "
    "fp 8 0 16 16 682.606 404.757 3677.64 3765.08 39")

# Target-space clicks where the inverse map was 120-235 px off the forward map.
MISMATCHED_CLICKS = ((2252.6, 2674.5), (2372.5, 2913.5), (2181.7, 2876.5))


def _forward(model, source_yx: np.ndarray) -> np.ndarray:
    mapped = mesh_hull_affine.map_points(model, np.asarray(source_yx, dtype=np.float64).reshape(1, 2),
                                         forward=True, extrapolate=True)
    return nornir_imageregistration.EnsureNumpyArray(mapped, dtype=np.float64).reshape(2)


class TestCreatePointUsesForwardMap(unittest.TestCase):

    def test_inverse_map_disagrees_with_forward_map_on_this_mesh(self) -> None:
        """Guards the fixture: the bug only shows where the two maps disagree."""
        model = factory.LoadTransform(RC1_0005_0004_MESH, pixelSpacing=1)
        click = np.array(MISMATCHED_CLICKS[0])
        source = nornir_imageregistration.EnsureNumpyArray(
            mesh_hull_affine.map_points(model, click.reshape(1, 2), forward=False, extrapolate=True),
            dtype=np.float64).reshape(2)
        self.assertGreater(float(np.hypot(*(_forward(model, source) - click))), 100.0)

    def test_created_point_source_is_drawn_under_the_click(self) -> None:
        for click_yx in MISMATCHED_CLICKS:
            with self.subTest(click=click_yx):
                model = factory.LoadTransform(RC1_0005_0004_MESH, pixelSpacing=1)
                click = np.array(click_yx, dtype=np.float64)
                with patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool"):
                    controller = TransformController(model)
                    pair = controller.map_pair_for_control_point_create(Space.Target, click)
                source = np.asarray(pair.source, dtype=np.float64)
                np.testing.assert_allclose(pair.target, click)
                self.assertLess(float(np.hypot(*(_forward(model, source) - click))), 1.0)

    def test_adding_the_point_does_not_move_the_image_at_the_click(self) -> None:
        model = factory.LoadTransform(RC1_0005_0004_MESH, pixelSpacing=1)
        click = np.array(MISMATCHED_CLICKS[0], dtype=np.float64)
        with patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool"):
            controller = TransformController(model)
            pair = controller.map_pair_for_control_point_create(Space.Target, click)
        source = np.asarray(pair.source, dtype=np.float64)
        drawn_before = _forward(model, source)
        model.AddPoint(np.array([click[0], click[1], source[0], source[1]]))
        self.assertLess(float(np.hypot(*(_forward(model, source) - drawn_before))), 1.0)

    def test_consistent_maps_keep_the_inverse_answer(self) -> None:
        """Where forward and inverse agree, the refinement leaves the inverse answer in place."""
        model = factory.LoadTransform(RC1_0005_0004_MESH, pixelSpacing=1)
        source = np.array((1404.5, 3261.9))
        click = _forward(model, source)
        refined = mesh_hull_affine.source_under_target(model, click, source)
        np.testing.assert_allclose(refined, source, atol=0.05)


if __name__ == '__main__':
    unittest.main()
