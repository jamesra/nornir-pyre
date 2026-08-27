"""Tests for session-stable control-point IDs and the registration queue."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from numpy.typing import NDArray
from hypothesis import given, settings
from hypothesis import strategies as st

from nornir_imageregistration.alignment_record import AlignmentRecord
from nornir_imageregistration.computational_lib import ComputationLib, HasCupy
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from PyQt6.QtCore import QThread
from pyre.controllers.control_point_registration_queue import (
    ControlPointBusySet,
    ControlPointRegistrationQueue,
)
from nornir_imageregistration.image_permutation_helper import ImagePermutationHelper
from pyre.controllers.alignment_payload import (
    SharedImagePairRef,
    stage_image_pair,
)
from pyre.controllers.transformcontroller import (
    TransformController,
    _mapped_yx_host,
    run_control_point_alignment,
    run_shared_control_point_alignment,
    uses_process_pool_for_point_alignment,
)
from pyre.observable import ObservableSet
from pyre.space import Space
from pyre.views.transformcontrollerview import (
    POINT_INSTANCE_BUSY,
    POINT_INSTANCE_IDLE,
    control_point_instance_states,
)


def _fake_qapp() -> MagicMock:
    app = MagicMock()
    app.thread.return_value = QThread.currentThread()
    return app


def _mesh(n_points: int = 4) -> MeshWithRBFFallback:
    points = np.array(
        [
            [float(i * 10), float(i * 20), float(i * 100), float(i * 200)]
            for i in range(n_points)
        ],
        dtype=np.float64,
    )
    return MeshWithRBFFallback(points)


def _record(dy: float = 2.0, dx: float = 3.0, weight: float = 1.0) -> AlignmentRecord:
    return AlignmentRecord(peak=(dy, dx), weight=weight, angle=0.0)


def _permutation_helper(size: int = 64) -> ImagePermutationHelper:
    """A small real helper; staging needs genuine pixels, mask, and stats."""
    rng = np.random.default_rng(0)
    image = rng.random((size, size), dtype=np.float32)
    mask = np.ones((size, size), dtype=bool)
    return ImagePermutationHelper(image, mask)


class TestControlPointRegistrationQueue(unittest.TestCase):
    def test_enqueue_dedup_and_in_flight(self) -> None:
        queue = ControlPointRegistrationQueue()
        self.assertEqual(queue.enqueue([4, 4, 7]), [4, 7])
        self.assertEqual(queue.enqueue([4, 8]), [8])
        self.assertEqual(queue.take_next(), 4)
        self.assertEqual(queue.enqueue([4]), [])
        self.assertTrue(queue.contains(4))
        self.assertEqual(queue.in_flight_id, 4)

    def test_cancel_pending_and_in_flight(self) -> None:
        queue = ControlPointRegistrationQueue()
        queue.enqueue([1, 2, 3])
        queue.cancel(2)
        self.assertEqual(queue.take_next(), 1)
        queue.cancel(1)
        self.assertTrue(queue.is_cancelled(1))
        queue.finish(1)
        self.assertEqual(queue.take_next(), 3)
        self.assertFalse(queue.contains(1))

    def test_multiple_jobs_can_be_in_flight(self) -> None:
        queue = ControlPointRegistrationQueue()
        queue.enqueue([1, 2, 3])
        self.assertEqual(queue.take_next(), 1)
        self.assertEqual(queue.take_next(), 2)
        self.assertEqual(queue.in_flight_ids, frozenset({1, 2}))
        self.assertEqual(queue.in_flight_count, 2)
        self.assertEqual(queue.pending_count, 1)
        self.assertEqual(queue.queued_ids, frozenset({1, 2, 3}))
        self.assertFalse(queue.is_idle)
        queue.finish(1)
        self.assertEqual(queue.in_flight_ids, frozenset({2}))
        queue.finish(2)
        self.assertEqual(queue.take_next(), 3)
        queue.finish(3)
        self.assertTrue(queue.is_idle)

    def test_cancel_all_marks_every_in_flight_job(self) -> None:
        queue = ControlPointRegistrationQueue()
        queue.enqueue([1, 2, 3])
        queue.take_next()
        queue.take_next()
        queue.cancel_all()
        self.assertTrue(queue.is_cancelled(1))
        self.assertTrue(queue.is_cancelled(2))
        self.assertEqual(queue.pending_count, 0)
        self.assertIsNone(queue.take_next())


class TestControlPointBusySet(unittest.TestCase):
    """Reason-keyed union of busy session IDs."""

    def test_mark_unmark_union_and_change_flag(self) -> None:
        busy = ControlPointBusySet()
        self.assertTrue(busy.mark("register", [1, 2]))
        self.assertFalse(busy.mark("register", [1]))
        self.assertTrue(busy.mark("refine", [2, 3]))
        self.assertEqual(busy.ids, frozenset({1, 2, 3}))
        self.assertTrue(busy.unmark("register", [1, 2]))
        self.assertEqual(busy.ids, frozenset({2, 3}))
        self.assertFalse(busy.unmark("register", [1]))
        self.assertTrue(busy.clear("refine"))
        self.assertEqual(busy.ids, frozenset())
        self.assertFalse(busy.clear("refine"))

    def test_set_ids_replaces_reason_bucket(self) -> None:
        busy = ControlPointBusySet()
        busy.mark("register", [1, 2, 3])
        self.assertTrue(busy.set_ids("register", [2]))
        self.assertEqual(busy.ids, frozenset({2}))
        self.assertFalse(busy.set_ids("register", [2]))
        self.assertTrue(busy.set_ids("register", []))
        self.assertEqual(busy.ids, frozenset())


class TestBusyPointsOnController(unittest.TestCase):
    def test_enqueue_and_finish_update_busy_ids(self) -> None:
        controller = TransformController(_mesh(4))
        id0 = controller.point_id_for_index(0)
        id1 = controller.point_id_for_index(1)
        assert id0 is not None and id1 is not None
        pool = MagicMock()
        pool.add_task = MagicMock()
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
            qapp.instance.return_value = _fake_qapp()
            with patch(
                    "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                    return_value=pool,
            ):
                added = controller.enqueue_point_registrations(
                    [0, 1], align_fn=lambda **_: _record())
                self.assertEqual(set(added), {id0, id1})
                self.assertEqual(controller.busy_point_ids, frozenset({id0, id1}))
                self.assertEqual(controller.busy_point_indices, frozenset({0, 1}))
                controller._on_registration_finished(id0, np.array([0.0, 0.0]), None)
                self.assertEqual(controller.busy_point_ids, frozenset({id1}))
                controller._on_registration_finished(id1, np.array([0.0, 0.0]), None)
                self.assertEqual(controller.busy_point_ids, frozenset())

    def test_mark_drops_selected_indices(self) -> None:
        selection = ObservableSet(initial_set={0, 1, 2})
        controller = TransformController(_mesh(4), selected_points=selection)
        point_id = controller.point_id_for_index(1)
        assert point_id is not None
        controller.mark_busy_points("register", [point_id])
        self.assertEqual(set(selection), {0, 2})
        self.assertEqual(controller.busy_point_indices, frozenset({1}))
        self.assertTrue(controller.freeze_composite_display_during_point_drag())

    def test_listener_fires_only_when_union_changes(self) -> None:
        controller = TransformController(_mesh(4))
        calls: list[frozenset[int]] = []
        controller.AddOnBusyPointsChanged(lambda _c, ids: calls.append(ids))
        id0 = controller.point_id_for_index(0)
        id1 = controller.point_id_for_index(1)
        assert id0 is not None and id1 is not None
        controller.mark_busy_points("a", [id0])
        controller.mark_busy_points("a", [id0])
        controller.mark_busy_points("b", [id0])
        controller.mark_busy_points("b", [id1])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], frozenset({id0}))
        self.assertEqual(calls[1], frozenset({id0, id1}))


class TestBusyBlocksWholeTransformGestures(unittest.TestCase):
    def test_scale_warped_leaves_queued_points_unmoved(self) -> None:
        controller = TransformController(_mesh(4))
        before = np.array(controller.SourcePoints, copy=True)
        point_id = controller.point_id_for_index(0)
        assert point_id is not None
        controller.mark_busy_points("register", [point_id])
        controller.ScaleWarped(2.0)
        np.testing.assert_allclose(controller.SourcePoints, before)

    def test_rotate_leaves_queued_points_unmoved(self) -> None:
        controller = TransformController(_mesh(4))
        before = np.array(controller.SourcePoints, copy=True)
        point_id = controller.point_id_for_index(1)
        assert point_id is not None
        controller.mark_busy_points("register", [point_id])
        controller.Rotate(0.25, np.array([0.0, 0.0], dtype=np.float64), space=Space.Source)
        np.testing.assert_allclose(controller.SourcePoints, before)

    def test_wheel_helper_false_when_busy(self) -> None:
        from pyre.commands.navigationcommandbase import (
            wheel_applies_relative_scale,
            wheel_applies_warped_transform,
        )

        controller = TransformController(_mesh(4))
        self.assertTrue(wheel_applies_warped_transform(controller))
        self.assertTrue(wheel_applies_relative_scale(controller))
        point_id = controller.point_id_for_index(0)
        assert point_id is not None
        controller.mark_busy_points("register", [point_id])
        self.assertFalse(wheel_applies_warped_transform(controller))
        self.assertFalse(wheel_applies_relative_scale(controller))

    def test_wheel_scale_helper_false_when_selected(self) -> None:
        from pyre.commands.navigationcommandbase import (
            wheel_applies_relative_scale,
            wheel_applies_warped_transform,
        )

        selection = ObservableSet(initial_set={0})
        controller = TransformController(_mesh(4), selected_points=selection)
        self.assertTrue(controller.has_ui_control_point_selection())
        self.assertTrue(wheel_applies_warped_transform(controller))
        self.assertFalse(wheel_applies_relative_scale(controller))

    def test_scale_fixed_leaves_queued_points_unmoved(self) -> None:
        controller = TransformController(_mesh(4))
        before_target = np.array(controller.TargetPoints, copy=True)
        before_source = np.array(controller.SourcePoints, copy=True)
        point_id = controller.point_id_for_index(0)
        assert point_id is not None
        controller.mark_busy_points("register", [point_id])
        controller.ScaleFixed(2.0, np.array([0.0, 0.0], dtype=np.float64))
        np.testing.assert_allclose(controller.TargetPoints, before_target)
        np.testing.assert_allclose(controller.SourcePoints, before_source)

    def test_scale_fixed_leaves_selected_points_unmoved(self) -> None:
        selection = ObservableSet(initial_set={1})
        controller = TransformController(_mesh(4), selected_points=selection)
        before_target = np.array(controller.TargetPoints, copy=True)
        before_source = np.array(controller.SourcePoints, copy=True)
        controller.ScaleFixed(2.0, np.array([0.0, 0.0], dtype=np.float64))
        np.testing.assert_allclose(controller.TargetPoints, before_target)
        np.testing.assert_allclose(controller.SourcePoints, before_source)

    def test_scale_warped_leaves_selected_points_unmoved(self) -> None:
        selection = ObservableSet(initial_set={0})
        controller = TransformController(_mesh(4), selected_points=selection)
        before = np.array(controller.SourcePoints, copy=True)
        controller.ScaleWarped(2.0)
        np.testing.assert_allclose(controller.SourcePoints, before)

    def test_scale_warped_moves_idle_points(self) -> None:
        controller = TransformController(_mesh(4))
        before = np.array(controller.SourcePoints, copy=True)
        controller.ScaleWarped(2.0)
        np.testing.assert_allclose(controller.SourcePoints, before * 2.0)

    def test_warm_alignment_process_pool_calls_warm(self) -> None:
        from pyre.controllers.transformcontroller import (
            warm_alignment_process_pool,
            warmup_alignment_process_worker,
        )

        pool = MagicMock()
        with (
            patch("pyre.controllers.transformcontroller.pools.GetGlobalThreadPool"),
            patch(
                "pyre.controllers.transformcontroller.pools.GetGlobalLocalMachinePool",
                return_value=pool,
            ),
        ):
            warm_alignment_process_pool()
        pool.warm.assert_called_once_with(warmup_alignment_process_worker)


class TestControlPointInstanceStates(unittest.TestCase):
    def test_busy_overrides_selected_blink(self) -> None:
        mask = np.array([True, False, True], dtype=bool)
        tex = control_point_instance_states(3, mask, busy_indices={0, 2}, blink_phase=1)
        self.assertEqual(tex[0, 0], POINT_INSTANCE_BUSY)
        self.assertEqual(tex[1, 0], POINT_INSTANCE_IDLE)
        self.assertEqual(tex[2, 0], POINT_INSTANCE_BUSY)

    def test_selected_blinks_when_not_busy(self) -> None:
        mask = np.array([True, True], dtype=bool)
        even = control_point_instance_states(2, mask, busy_indices=(), blink_phase=0)
        odd = control_point_instance_states(2, mask, busy_indices=(), blink_phase=1)
        np.testing.assert_array_equal(even, np.array([[0.0], [0.0]], dtype=np.float32))
        np.testing.assert_array_equal(odd, np.array([[1.0], [1.0]], dtype=np.float32))


class TestSessionPointIds(unittest.TestCase):
    def test_ids_match_indices_on_load(self) -> None:
        controller = TransformController(_mesh(4))
        for index in range(4):
            self.assertEqual(controller.point_id_for_index(index), index)
            self.assertEqual(controller.index_for_point_id(index), index)

    def test_delete_shifts_index_not_id(self) -> None:
        controller = TransformController(_mesh(4))
        kept_id = controller.point_id_for_index(3)
        assert kept_id is not None
        self.assertTrue(controller.TryDeletePoints([0]))
        self.assertEqual(controller.index_for_point_id(kept_id), 2)
        self.assertIsNone(controller.index_for_point_id(0))

    @given(delete_index=st.integers(min_value=0, max_value=2))
    @settings(max_examples=15, deadline=None)
    def test_remaining_ids_resolve_after_delete(self, delete_index: int) -> None:
        controller = TransformController(_mesh(4))
        surviving: dict[int, int] = {}
        for i in range(4):
            if i == delete_index:
                continue
            point_id = controller.point_id_for_index(i)
            assert point_id is not None
            surviving[point_id] = i
        self.assertTrue(controller.TryDeletePoints([delete_index]))
        for point_id, old_index in surviving.items():
            new_index = controller.index_for_point_id(point_id)
            self.assertIsNotNone(new_index)
            self.assertEqual(new_index, old_index if old_index < delete_index else old_index - 1)


class TestRegistrationApply(unittest.TestCase):
    def test_enqueue_dedup_while_in_flight(self) -> None:
        controller = TransformController(_mesh(4))
        pool = MagicMock()
        pool.add_task = MagicMock()
        point_id = controller.point_id_for_index(0)
        assert point_id is not None
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
            qapp.instance.return_value = _fake_qapp()
            with patch(
                    "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                    return_value=pool,
            ):
                first = controller.enqueue_point_registrations([0], align_fn=lambda **_: _record())
                second = controller.enqueue_point_registrations([0], align_fn=lambda **_: _record())
        self.assertEqual(first, [point_id])
        self.assertEqual(second, [])
        self.assertEqual(controller.in_flight_registration_id, point_id)
        pool.add_task.assert_called_once()

    def test_apply_moves_target_point(self) -> None:
        controller = TransformController(_mesh(4))
        before = np.asarray(controller.TargetPoints[0], dtype=np.float64)
        controller.enqueue_point_registrations([0], align_fn=lambda **_: _record(2.0, 3.0))
        after = np.asarray(controller.TargetPoints[0], dtype=np.float64)
        np.testing.assert_allclose(after, before + np.array([2.0, 3.0]))
        self.assertTrue(controller._registration_queue.is_idle)

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_enqueue_accepts_cupy_fixed_point(self) -> None:
        """GPU TargetPoints rows cannot be np.asarray'd; queue snapshot/apply use host YX."""
        import cupy as cp

        controller = TransformController(_mesh(4))
        before = _mapped_yx_host(controller.GetFixedPoint(0)).copy()
        original = controller.GetFixedPoint

        def _cupy_row(index: int) -> object:
            return cp.asarray(original(index))

        with patch.object(controller, "GetFixedPoint", side_effect=_cupy_row):
            controller.enqueue_point_registrations(
                [0], align_fn=lambda **_: _record(2.0, 3.0))
        after = _mapped_yx_host(controller.GetFixedPoint(0))
        np.testing.assert_allclose(after, before + np.array([2.0, 3.0]))
        self.assertTrue(controller._registration_queue.is_idle)

    def test_delete_in_flight_discards_result(self) -> None:
        controller = TransformController(_mesh(4))
        targets: dict[int, NDArray[np.floating]] = {}
        for i in range(4):
            point_id = controller.point_id_for_index(i)
            assert point_id is not None
            targets[point_id] = np.asarray(controller.TargetPoints[i], dtype=np.float64).copy()
        pool = MagicMock()
        captured: list = []
        pool.add_task = lambda _name, fn, *args, **kwargs: captured.append(fn)
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
            qapp.instance.return_value = _fake_qapp()
            with patch(
                    "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                    return_value=pool,
            ):
                with patch(
                        "pyre.controllers.transformcontroller.qt_post_to_main",
                        side_effect=lambda fn: fn(),
                ):
                    controller.enqueue_point_registrations([1], align_fn=lambda **_: _record())
                    with patch.object(controller, "FireOnChangeEvent"):
                        self.assertTrue(controller.TryDeletePoints([1]))
                    captured[0]()
        self.assertIsNone(controller.index_for_point_id(1))
        for i in range(controller.NumPoints):
            point_id = controller.point_id_for_index(i)
            assert point_id is not None
            np.testing.assert_allclose(
                np.asarray(controller.TargetPoints[i], dtype=np.float64),
                targets[point_id],
            )

    def test_delete_pending_never_aligns(self) -> None:
        controller = TransformController(_mesh(4))

        def align_fn(**kwargs) -> AlignmentRecord:
            return _record()

        pool = MagicMock()
        captured: list = []
        pool.add_task = lambda _name, fn, *a, **k: captured.append(fn)
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
            qapp.instance.return_value = _fake_qapp()
            # Capacity of 1 keeps the second point pending so deleting it can be
            # observed; with full pool capacity both would already be in flight.
            with patch(
                    "pyre.controllers.transformcontroller.max_concurrent_point_alignments",
                    return_value=1,
            ):
                with patch(
                        "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                        return_value=pool,
                ):
                    id1 = controller.point_id_for_index(1)
                    assert id1 is not None
                    controller.enqueue_point_registrations([0, 1], align_fn=align_fn)
                    with patch.object(controller, "FireOnChangeEvent"):
                        self.assertTrue(controller.TryDeletePoints([1]))
        self.assertEqual(len(captured), 1)
        self.assertNotIn(id1, controller.queued_registration_ids)

    def test_drag_after_snapshot_discards_result(self) -> None:
        controller = TransformController(_mesh(4))
        before = np.asarray(controller.TargetPoints[0], dtype=np.float64).copy()

        def align_fn(**kwargs) -> AlignmentRecord:
            controller.MovePoint(0, 10.0, 4.0, space=Space.Target)
            return _record(2.0, 3.0)

        controller.enqueue_point_registrations([0], align_fn=align_fn)
        after = np.asarray(controller.TargetPoints[0], dtype=np.float64)
        np.testing.assert_allclose(after, before + np.array([4.0, 10.0]))

    def test_shifted_index_still_applies_to_same_id(self) -> None:
        controller = TransformController(_mesh(4))
        point_id = controller.point_id_for_index(3)
        assert point_id is not None
        original = np.asarray(controller.TargetPoints[3], dtype=np.float64).copy()
        self.assertTrue(controller.TryDeletePoints([0]))
        index = controller.index_for_point_id(point_id)
        self.assertEqual(index, 2)
        assert index is not None
        controller.enqueue_point_registrations([index], align_fn=lambda **_: _record(1.5, -0.5))
        moved = np.asarray(controller.TargetPoints[index], dtype=np.float64)
        np.testing.assert_allclose(moved, original + np.array([1.5, -0.5]))

    def test_register_command_enqueues_without_wait(self) -> None:
        import inspect

        from pyre.commands.stos.registercontrolpointcommand import RegisterControlPointCommand

        source = inspect.getsource(RegisterControlPointCommand.execute)
        self.assertIn("enqueue_point_registrations", source)
        self.assertNotIn("wait_return", source)

    def test_process_pool_eligibility_ignores_active_backend(self) -> None:
        """Alignment is host-only, so a CuPy session still uses the process pool."""
        for lib in (ComputationLib.numpy, ComputationLib.cupy):
            with patch(
                    "pyre.controllers.transformcontroller.nornir_imageregistration.GetActiveComputationLib",
                    return_value=lib,
            ):
                self.assertTrue(uses_process_pool_for_point_alignment())

    def test_staging_failure_falls_back_to_thread_pool(self) -> None:
        controller = TransformController(_mesh(4))
        process_pool = MagicMock()
        thread_pool = MagicMock()
        helper = _permutation_helper()
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
            qapp.instance.return_value = _fake_qapp()
            with patch(
                    "pyre.controllers.transformcontroller.stage_image_pair",
                    return_value=None,
            ):
                with patch(
                        "pyre.controllers.transformcontroller.pools.GetGlobalLocalMachinePool",
                        return_value=process_pool,
                ):
                    with patch(
                            "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                            return_value=thread_pool,
                    ):
                        controller.enqueue_point_registrations(
                            [0],
                            source_image=helper,
                            target_image=helper,
                            alignment_area=np.array([32, 32], dtype=np.int32),
                            angles_to_search=np.array([0.0]),
                        )
        process_pool.add_task.assert_not_called()
        thread_pool.add_task.assert_called_once()

    def test_cpu_submits_picklable_process_task(self) -> None:
        controller = TransformController(_mesh(4))
        process_pool = MagicMock()
        thread_pool = MagicMock()
        task = MagicMock()
        task.wait_return.return_value = _record()
        process_pool.add_task.return_value = task
        helper = _permutation_helper()
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
            qapp.instance.return_value = _fake_qapp()
            with patch(
                    "pyre.controllers.transformcontroller.pools.GetGlobalLocalMachinePool",
                    return_value=process_pool,
            ):
                with patch(
                        "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                        return_value=thread_pool,
                ):
                    controller.enqueue_point_registrations(
                        [0],
                        source_image=helper,
                        target_image=helper,
                        alignment_area=np.array([32, 32], dtype=np.int32),
                        angles_to_search=np.array([0.0]),
                    )
        try:
            process_pool.add_task.assert_called_once()
            args = process_pool.add_task.call_args.args
            self.assertIs(args[1], run_shared_control_point_alignment)
            # Only segment names cross the pipe, not the image pair itself.
            self.assertIsInstance(args[3], SharedImagePairRef)
            thread_pool.add_task.assert_called_once()
        finally:
            controller._release_staged_alignment_pair()

    def test_batch_stages_image_pair_once(self) -> None:
        """Every point in a register-all batch reuses one staged pair."""
        controller = TransformController(_mesh(8))
        process_pool = MagicMock()
        process_pool.add_task.return_value = MagicMock()
        thread_pool = MagicMock()
        helper = _permutation_helper()
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
            qapp.instance.return_value = _fake_qapp()
            with patch(
                    "pyre.controllers.transformcontroller.max_concurrent_point_alignments",
                    return_value=8,
            ):
                with patch(
                        "pyre.controllers.transformcontroller.pools.GetGlobalLocalMachinePool",
                        return_value=process_pool,
                ):
                    with patch(
                            "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                            return_value=thread_pool,
                    ):
                        with patch(
                                "pyre.controllers.transformcontroller.stage_image_pair",
                                side_effect=stage_image_pair,
                        ) as stage:
                            controller.enqueue_point_registrations(
                                list(range(8)),
                                source_image=helper,
                                target_image=helper,
                                alignment_area=np.array([32, 32], dtype=np.int32),
                                angles_to_search=np.array([0.0]),
                            )
        try:
            self.assertEqual(process_pool.add_task.call_count, 8)
            stage.assert_called_once()
            refs = {id(call.args[3]) for call in process_pool.add_task.call_args_list}
            self.assertEqual(len(refs), 1)
        finally:
            controller._release_staged_alignment_pair()

    def test_register_all_dispatches_up_to_pool_capacity(self) -> None:
        """Register-all fills pool capacity instead of running one point at a time."""
        controller = TransformController(_mesh(8))
        thread_pool = MagicMock()
        thread_pool.add_task = MagicMock()
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
            qapp.instance.return_value = _fake_qapp()
            with patch(
                    "pyre.controllers.transformcontroller.max_concurrent_point_alignments",
                    return_value=3,
            ):
                with patch(
                        "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                        return_value=thread_pool,
                ):
                    controller.enqueue_point_registrations(
                        list(range(8)), align_fn=lambda **_: _record())
        self.assertEqual(thread_pool.add_task.call_count, 3)
        self.assertEqual(controller._registration_queue.in_flight_count, 3)
        self.assertEqual(controller._registration_queue.pending_count, 5)
        # All 8 stay busy so glyphs and edit locks cover queued points too.
        self.assertEqual(len(controller.busy_point_ids), 8)

    def test_finishing_one_point_starts_the_next(self) -> None:
        controller = TransformController(_mesh(4))
        thread_pool = MagicMock()
        thread_pool.add_task = MagicMock()
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
            qapp.instance.return_value = _fake_qapp()
            with patch(
                    "pyre.controllers.transformcontroller.max_concurrent_point_alignments",
                    return_value=2,
            ):
                with patch(
                        "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                        return_value=thread_pool,
                ):
                    controller.enqueue_point_registrations(
                        list(range(4)), align_fn=lambda **_: _record())
                    self.assertEqual(thread_pool.add_task.call_count, 2)
                    in_flight = sorted(controller._registration_queue.in_flight_ids)
                    controller._on_registration_finished(
                        in_flight[0], np.array([0.0, 0.0]), None)
                    self.assertEqual(thread_pool.add_task.call_count, 3)
                    self.assertEqual(
                        controller._registration_queue.in_flight_count, 2)

    def test_max_concurrent_uses_pool_worker_count(self) -> None:
        from pyre.controllers.transformcontroller import max_concurrent_point_alignments

        pool = MagicMock()
        pool.max_workers = 6
        with patch(
                "pyre.controllers.transformcontroller.uses_process_pool_for_point_alignment",
                return_value=False,
        ):
            with patch(
                    "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                    return_value=pool,
            ):
                self.assertEqual(max_concurrent_point_alignments(), 6)

    def test_max_concurrent_is_at_least_one(self) -> None:
        from pyre.controllers.transformcontroller import max_concurrent_point_alignments

        pool = MagicMock()
        pool.max_workers = 0
        with patch(
                "pyre.controllers.transformcontroller.uses_process_pool_for_point_alignment",
                return_value=False,
        ):
            with patch(
                    "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                    return_value=pool,
            ):
                self.assertEqual(max_concurrent_point_alignments(), 1)

    def test_cupy_submits_thread_pool_worker(self) -> None:
        controller = TransformController(_mesh(4))
        process_pool = MagicMock()
        thread_pool = MagicMock()
        helper = MagicMock()
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
            qapp.instance.return_value = _fake_qapp()
            with patch(
                    "pyre.controllers.transformcontroller.nornir_imageregistration.GetActiveComputationLib",
                    return_value=ComputationLib.cupy,
            ):
                with patch(
                        "pyre.controllers.transformcontroller.pools.GetGlobalLocalMachinePool",
                        return_value=process_pool,
                ):
                    with patch(
                            "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                            return_value=thread_pool,
                    ):
                        controller.enqueue_point_registrations(
                            [0],
                            source_image=helper,
                            target_image=helper,
                            alignment_area=np.array([32, 32], dtype=np.int32),
                            angles_to_search=np.array([0.0]),
                        )
        process_pool.add_task.assert_not_called()
        thread_pool.add_task.assert_called_once()


class TestControlPointAlignmentCpu(unittest.TestCase):
    """Spacebar queue scoring stays on the host even when the process is CuPy."""

    def test_run_control_point_alignment_forces_cpu(self) -> None:
        host = np.ones((8, 8), dtype=np.float32)
        helper = MagicMock()
        helper.ImageWithMaskAsNoise = host
        helper.Stats = MagicMock()
        helper.BlendedMask = None
        with patch("pyre.common.either_roi_is_masked", return_value=False):
            with patch("nornir_imageregistration.SetActiveComputationLib") as set_lib:
                with patch(
                        "nornir_imageregistration.local_distortion_correction.AttemptAlignPoint",
                        return_value=_record(),
                ) as align:
                    run_control_point_alignment(
                        MagicMock(),
                        helper,
                        helper,
                        np.array([32, 32], dtype=np.int32),
                        np.array([0.0]),
                        np.array([10.0, 10.0]),
                    )
        align.assert_called_once()
        self.assertIs(align.call_args.kwargs["use_gpu"], False)
        np.testing.assert_array_equal(align.call_args.kwargs["targetImage"], host)
        np.testing.assert_array_equal(align.call_args.kwargs["sourceImage"], host)
        set_lib.assert_not_called()

    def test_run_control_point_alignment_host_copies_device_images(self) -> None:
        class _Device:
            def __init__(self, host: NDArray[np.floating]) -> None:
                self._host = host

            def get(self) -> NDArray[np.floating]:
                return self._host

        host = np.ones((8, 8), dtype=np.float32)
        helper = MagicMock()
        helper.ImageWithMaskAsNoise = _Device(host)
        helper.Stats = MagicMock()
        helper.BlendedMask = None
        with patch("pyre.common.either_roi_is_masked", return_value=False):
            with patch(
                    "nornir_imageregistration.local_distortion_correction.AttemptAlignPoint",
                    return_value=_record(),
            ) as align:
                run_control_point_alignment(
                    MagicMock(),
                    helper,
                    helper,
                    np.array([32, 32], dtype=np.int32),
                    np.array([0.0]),
                    np.array([10.0, 10.0]),
                )
        np.testing.assert_array_equal(align.call_args.kwargs["targetImage"], host)
        self.assertIs(align.call_args.kwargs["use_gpu"], False)


def _identity_mesh_square() -> MeshWithRBFFallback:
    points = np.array(
        [
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 32.0, 0.0, 32.0],
            [32.0, 0.0, 32.0, 0.0],
            [32.0, 32.0, 32.0, 32.0],
        ],
        dtype=np.float64,
    )
    return MeshWithRBFFallback(points)


class TestRegistrationIdleRbfPrewarm(unittest.TestCase):
    """RBF rebuild is deferred until the registration queue is empty."""

    def test_queue_rbf_prewarm_skipped_while_busy(self) -> None:
        mesh = _identity_mesh_square()
        mesh.InitializeDataStructures()
        with patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool") as get_pool:
            pool = MagicMock()
            get_pool.return_value = pool
            controller = TransformController(mesh)
            gen = controller._rbf_prewarm_generation
            pool.add_task.reset_mock()
            point_id = controller.point_id_for_index(0)
            assert point_id is not None
            controller.mark_busy_points("register", [point_id])
            controller._queue_rbf_prewarm()
            pool.add_task.assert_not_called()
            self.assertEqual(controller._rbf_prewarm_generation, gen)

    def test_rbf_prewarm_ready_when_stale_instance_exists(self) -> None:
        mesh = _identity_mesh_square()
        mesh.InitializeDataStructures()
        with patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool"):
            controller = TransformController(mesh)
            mesh.UpdateTargetPointsByIndex(
                0, np.asarray(mesh.TargetPoints[0], dtype=np.float64) + np.array((2.0, 1.0)))
            controller._rbf_prewarm_ready = False
            self.assertTrue(mesh._continuous_stale)
            self.assertIsNotNone(mesh._ForwardRBFInstance)
            self.assertTrue(controller.rbf_prewarm_ready)

    def test_n_registration_applies_prewarm_once_on_idle(self) -> None:
        mesh = _identity_mesh_square()
        mesh.InitializeDataStructures()
        live_rbf = mesh._ForwardRBFInstance
        with patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool"):
            controller = TransformController(mesh)
        with patch.object(controller, "_queue_rbf_prewarm") as prewarm:
            thread_pool = MagicMock()
            with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
                qapp.instance.return_value = _fake_qapp()
                with patch(
                        "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                        return_value=thread_pool,
                ):
                    added = controller.enqueue_point_registrations(
                        [0, 1, 2], align_fn=lambda **_: _record())
                    self.assertEqual(len(added), 3)
                    while not controller._registration_queue.is_idle:
                        pid = controller.in_flight_registration_id
                        self.assertIsNotNone(pid)
                        index = controller.index_for_point_id(int(pid))
                        self.assertIsNotNone(index)
                        snapshot = _mapped_yx_host(
                            controller.GetFixedPoint(int(index))).copy()
                        controller._on_registration_finished(int(pid), snapshot, _record())
            prewarm.assert_called_once()
        self.assertIs(mesh._ForwardRBFInstance, live_rbf)
        self.assertTrue(mesh._continuous_stale)
