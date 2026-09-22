"""Tests for Pyre masked grid control-point relaxation triggers."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from nornir_imageregistration.grid_subdivision import ITKGridDivision
from nornir_imageregistration.transforms import Rigid
from nornir_imageregistration.transforms.gridtransform import GridTransform
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback

from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.controllers.transform_display import TransformGesture
from pyre.controllers import masked_grid_relax


def _identity_grid(shape: tuple[int, int] = (48, 48), cell: tuple[int, int] = (16, 16)) -> GridTransform:
    grid = ITKGridDivision(source_shape=shape, cell_size=cell)
    grid.PopulateTargetPoints(
        Rigid(target_offset=(0.0, 0.0), source_rotation_center=(shape[0] / 2.0, shape[1] / 2.0), angle=0.0))
    return GridTransform(grid)


def _mask_covering_points(
        points: np.ndarray,
        *,
        hole_index: int | None = None) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64)
    height = int(np.floor(pts[:, 0].max())) + 2
    width = int(np.floor(pts[:, 1].max())) + 2
    mask = np.ones((max(height, 1), max(width, 1)), dtype=bool)
    if hole_index is not None:
        y = int(np.floor(pts[hole_index, 0]))
        x = int(np.floor(pts[hole_index, 1]))
        mask[y, x] = False
    return mask


def _mesh() -> MeshWithRBFFallback:
    points = np.array([
        [10.0, 20.0, 100.0, 200.0],
        [30.0, 40.0, 300.0, 400.0],
        [50.0, 60.0, 500.0, 600.0],
        [70.0, 80.0, 700.0, 800.0],
    ], dtype=np.float32)
    return MeshWithRBFFallback(points)


def _enqueue_relax_sync(controller: TransformController, *args, **kwargs) -> None:
    """Run a relax wave on the headless inline path.

    Other tests may create a QApplication; production then posts the wave to
    the process-wide thread pool, which this unit test does not own.
    """
    with patch("pyre.controllers.transformcontroller.QApplication.instance", return_value=None):
        controller.enqueue_masked_grid_relax(*args, **kwargs)


class TestMaskedGridRelaxTriggers(unittest.TestCase):
    def test_enqueue_while_in_flight_cancels_and_coalesces(self) -> None:
        controller = TransformController(_identity_grid())
        controller._masked_relax_in_flight = True
        controller._masked_relax_generation = 3
        with patch.object(controller, '_start_masked_grid_relax_wave') as start:
            controller.enqueue_masked_grid_relax([2, 5])
            start.assert_not_called()
        self.assertEqual(controller._masked_relax_generation, 4)
        self.assertEqual(controller._masked_relax_pending_seeds, {2, 5})

    def test_mesh_mode_does_not_enqueue(self) -> None:
        controller = TransformController(_mesh())
        with patch.object(controller, '_start_masked_grid_relax_wave') as start:
            controller.enqueue_masked_grid_relax([0])
            start.assert_not_called()

    def test_no_wave_during_interactive_drag(self) -> None:
        controller = TransformController(_identity_grid())
        controller.begin_interactive_edit(Space.Target, ViewType.Target, TransformGesture.CONTROL_POINT_DRAG)
        with patch.object(controller, '_start_masked_grid_relax_wave') as start:
            controller.enqueue_masked_grid_relax([0])
            start.assert_not_called()
        controller.end_interactive_edit()

    def test_end_interactive_edit_enqueues_moved_indices(self) -> None:
        controller = TransformController(_identity_grid())
        controller.begin_interactive_edit(Space.Target, ViewType.Target, TransformGesture.CONTROL_POINT_DRAG)
        controller.MovePoint(0, ImageDX=5.0, ImageDY=0.0, space=Space.Target)
        with patch.object(controller, 'enqueue_masked_grid_relax') as enqueue:
            controller.end_interactive_edit()
            enqueue.assert_called_once()
            args, kwargs = enqueue.call_args
            self.assertEqual(args[0], [0])
            self.assertIn('undo_points', kwargs)
            self.assertIsNotNone(kwargs['undo_points'])

    def test_pinned_points_stay_put_after_wave(self) -> None:
        transform = _identity_grid()
        controller = TransformController(transform)
        n = controller.NumPoints
        # All fixed (no masks → all unmasked)
        before = copy.deepcopy(controller.points)
        controller.MovePoint(0, ImageDX=4.0, ImageDY=0.0, space=Space.Target)
        _enqueue_relax_sync(controller, [0], undo_points=before)
        after = controller.points
        np.testing.assert_allclose(after[0, 0:2], before[0, 0:2] + np.array([0.0, 4.0]))
        np.testing.assert_allclose(after[1:, 0:2], before[1:, 0:2])
        self.assertEqual(n, controller.NumPoints)

    def test_free_neighbors_move_when_mask_marks_staircase(self) -> None:
        transform = _identity_grid(shape=(64, 64), cell=(16, 16))
        controller = TransformController(transform)
        points = np.asarray(transform.TargetPoints)
        # Only seed 0 has tissue in the target mask; all other cells are free.
        src = np.ones((64, 64), dtype=bool)
        tgt = np.zeros((64, 64), dtype=bool)
        y0, x0 = points[0]
        tgt[int(y0) - 4:int(y0) + 5, int(x0) - 4:int(x0) + 5] = True

        before = copy.deepcopy(controller.points)
        controller.MovePoint(0, ImageDX=8.0, ImageDY=0.0, space=Space.Target)
        mock_config = MagicMock()
        mock_config.FixedImages = None
        mock_config.WarpedImages = None
        mock_config.SourceImageViewModel = None
        mock_config.TargetImageViewModel = None
        # Fixed* = Source (mapped); Warped* = Target (control)
        mock_config.FixedImageMaskViewModel.Image = src
        mock_config.WarpedImageMaskViewModel.Image = tgt
        with patch('pyre.state.get_current_stos_config', return_value=mock_config), \
                patch('pyre.controllers.masked_grid_relax.resolve_min_unmasked', return_value=0.25):
            _enqueue_relax_sync(controller, [0], undo_points=before)

        after = controller.points
        neighbor = 1  # right neighbor on row-major grid with cols > 1
        self.assertFalse(
            np.allclose(after[neighbor, 0:2], before[neighbor, 0:2]),
            "Free neighbor of a moved fixed seed should relax")
        np.testing.assert_allclose(after[0, 0:2], before[0, 0:2] + np.array([0.0, 8.0]))

    def test_source_pin_cache_reused_across_waves(self) -> None:
        from nornir_imageregistration.grid_subdivision import source_ok_for_grid_points as real_source_ok

        transform = _identity_grid(shape=(64, 64), cell=(16, 16))
        controller = TransformController(transform)
        src = np.ones((64, 64), dtype=bool)
        tgt = np.ones((64, 64), dtype=bool)
        mock_config = MagicMock()
        mock_config.FixedImages = None
        mock_config.WarpedImages = None
        mock_config.SourceImageViewModel = None
        mock_config.TargetImageViewModel = None
        mock_config.FixedImageMaskViewModel.Image = src
        mock_config.WarpedImageMaskViewModel.Image = tgt

        with patch('pyre.state.get_current_stos_config', return_value=mock_config), \
                patch('pyre.controllers.masked_grid_relax.resolve_min_unmasked', return_value=0.25), \
                patch(
                    'pyre.controllers.masked_grid_relax.source_ok_for_grid_points',
                    wraps=real_source_ok,
                ) as source_ok_fn:
            _enqueue_relax_sync(controller, [0])
            _enqueue_relax_sync(controller, [1])
            self.assertEqual(1, source_ok_fn.call_count)
            self.assertIsNotNone(controller._masked_relax_source_pin_cache)


class TestControlPointMaskSkip(unittest.TestCase):
    def test_indices_on_mask_include_source_or_target(self) -> None:
        source = np.array([[10.0, 10.0], [20.0, 20.0]], dtype=np.float64)
        target = np.array([[5.0, 5.0], [15.0, 15.0]], dtype=np.float64)
        src_mask = np.ones((32, 32), dtype=bool)
        tgt_mask = np.ones((32, 32), dtype=bool)
        src_mask[20, 20] = False
        tgt_mask[5, 5] = False
        masked = masked_grid_relax.control_point_indices_on_mask(
            source, target, src_mask, tgt_mask)
        self.assertEqual(masked, {0, 1})

    def test_indices_on_mask_empty_when_no_masks(self) -> None:
        points = np.array([[1.0, 2.0]], dtype=np.float64)
        self.assertEqual(
            masked_grid_relax.control_point_indices_on_mask(points, points, None, None),
            set(),
        )

    def test_neighbor_seeds_exclude_selected_free_points(self) -> None:
        seeds = masked_grid_relax.neighbor_seeds_for_free_points([0], (3, 3))
        self.assertEqual(sorted(seeds), [1, 3])

    def test_spacebar_skips_masked_mesh_alignment(self) -> None:
        controller = TransformController(_mesh())
        src = _mask_covering_points(controller.SourcePoints)
        tgt = _mask_covering_points(controller.TargetPoints, hole_index=0)

        def _align(**_kwargs: object) -> object:
            raise AssertionError("masked mesh point should not be aligned")

        with patch(
                "pyre.controllers.masked_grid_relax.resolve_stos_masks",
                return_value=(src, tgt),
        ):
            with patch.object(controller, "enqueue_masked_grid_relax") as relax:
                added = controller.enqueue_point_registrations([0], align_fn=_align)
        self.assertEqual(added, [])
        relax.assert_not_called()

    def test_spacebar_on_masked_grid_point_relaxes_instead(self) -> None:
        controller = TransformController(_identity_grid())
        src = _mask_covering_points(controller.SourcePoints)
        tgt = _mask_covering_points(controller.TargetPoints, hole_index=0)

        def _align(**_kwargs: object) -> object:
            raise AssertionError("masked grid point should not be aligned")

        with patch(
                "pyre.controllers.masked_grid_relax.resolve_stos_masks",
                return_value=(src, tgt),
        ):
            with patch.object(controller, "enqueue_masked_grid_relax") as relax:
                added = controller.enqueue_point_registrations([0], align_fn=_align)
        self.assertEqual(added, [])
        relax.assert_called_once()
        seeds = list(relax.call_args.args[0])
        self.assertNotIn(0, seeds)
        self.assertTrue(seeds)

    def test_spacebar_mixed_selection_registers_unmasked_only(self) -> None:
        controller = TransformController(_identity_grid())
        src = _mask_covering_points(controller.SourcePoints)
        tgt = _mask_covering_points(controller.TargetPoints, hole_index=0)
        aligned: list[object] = []

        def _align(**_kwargs: object) -> object:
            aligned.append(_kwargs)
            record = MagicMock()
            record.weight = 0
            record.peak = None
            return record

        unmasked_id = controller.point_id_for_index(1)
        with patch(
                "pyre.controllers.masked_grid_relax.resolve_stos_masks",
                return_value=(src, tgt),
        ):
            with patch.object(controller, "enqueue_masked_grid_relax") as relax:
                added = controller.enqueue_point_registrations([0, 1], align_fn=_align)
        self.assertEqual(added, [unmasked_id])
        self.assertEqual(len(aligned), 1)
        relax.assert_not_called()

    def test_alignment_window_off_image_skips_without_dispatch(self) -> None:
        """A live pixel is not enough; the alignment ROI must have tissue too."""
        points = np.array([
            [2.0, 2.0, 2.0, 2.0],
            [16.0, 16.0, 16.0, 16.0],
            [20.0, 8.0, 20.0, 8.0],
            [8.0, 20.0, 8.0, 20.0],
        ], dtype=np.float32)
        controller = TransformController(MeshWithRBFFallback(points))
        mask = np.ones((32, 32), dtype=bool)

        def _align(**_kwargs: object) -> object:
            raise AssertionError("edge alignment ROI should not be dispatched")

        with patch(
                "pyre.controllers.masked_grid_relax.resolve_stos_masks",
                return_value=(mask, mask),
        ), patch(
                "pyre.controllers.masked_grid_relax.resolve_min_unmasked",
                return_value=0.25,
        ):
            added = controller.enqueue_point_registrations(
                [0],
                align_fn=_align,
                alignment_area=np.array([80, 80], dtype=np.int32),
            )
        self.assertEqual(added, [])

    def test_interior_alignment_window_still_registers(self) -> None:
        points = np.array([
            [2.0, 2.0, 2.0, 2.0],
            [16.0, 16.0, 16.0, 16.0],
            [20.0, 8.0, 20.0, 8.0],
            [8.0, 20.0, 8.0, 20.0],
        ], dtype=np.float32)
        controller = TransformController(MeshWithRBFFallback(points))
        mask = np.ones((32, 32), dtype=bool)
        aligned: list[object] = []

        def _align(**_kwargs: object) -> object:
            aligned.append(_kwargs)
            record = MagicMock()
            record.weight = 0
            record.peak = None
            return record

        interior_id = controller.point_id_for_index(1)
        with patch(
                "pyre.controllers.masked_grid_relax.resolve_stos_masks",
                return_value=(mask, mask),
        ), patch(
                "pyre.controllers.masked_grid_relax.resolve_min_unmasked",
                return_value=0.25,
        ):
            added = controller.enqueue_point_registrations(
                [1],
                align_fn=_align,
                alignment_area=np.array([16, 16], dtype=np.int32),
            )
        self.assertEqual(added, [interior_id])
        self.assertEqual(len(aligned), 1)


class TestEitherRoiIsMasked(unittest.TestCase):
    def test_edge_window_is_masked_without_warping_the_transform(self) -> None:
        from pyre.common import either_roi_is_masked

        mask = np.ones((32, 32), dtype=bool)
        transform = MagicMock()
        with patch(
                "nornir_imageregistration.local_distortion_correction.ApproximateRigidTransformByTargetPoints",
        ) as approx:
            self.assertTrue(either_roi_is_masked(
                transform,
                mask,
                mask,
                [2.0, 2.0],
                (80, 80),
                source_controlpoint=[2.0, 2.0],
            ))
            approx.assert_not_called()

    def test_interior_window_is_not_masked(self) -> None:
        from pyre.common import either_roi_is_masked

        mask = np.ones((32, 32), dtype=bool)
        self.assertFalse(either_roi_is_masked(
            MagicMock(),
            mask,
            mask,
            [16.0, 16.0],
            (16, 16),
            source_controlpoint=[16.0, 16.0],
        ))


if __name__ == '__main__':
    unittest.main()
