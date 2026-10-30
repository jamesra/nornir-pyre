"""Tests for load-time publication of alignment images to shared memory."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from PyQt6.QtCore import QThread

from nornir_imageregistration.alignment_record import AlignmentRecord
from nornir_imageregistration.image_permutation_helper import ImagePermutationHelper
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback

from pyre.contrast_settle import ContrastSettleNotifier
from pyre.controllers.alignment_payload import (
    SharedImagePairRef,
    host_image_payload,
    stage_host_image,
)
from pyre.controllers.registration_image_store import RegistrationImageStore
from pyre.controllers.transformcontroller import (
    TransformController,
    host_transform_snapshot,
    run_shared_control_point_alignment,
)
from pyre.space import Space


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


def _helper(size: int = 32, seed: int = 0) -> ImagePermutationHelper:
    rng = np.random.default_rng(seed)
    return ImagePermutationHelper(
        rng.random((size, size), dtype=np.float32),
        np.ones((size, size), dtype=bool),
    )


def _record(dy: float = 2.0, dx: float = 3.0) -> AlignmentRecord:
    return AlignmentRecord(peak=(dy, dx), weight=1.0, angle=0.0)


class _RecordingPool:
    """Thread pool stand-in that captures submitted callables."""

    def __init__(self) -> None:
        self.tasks: list = []

    def add_task(self, _name: str, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))
        return MagicMock()

    def run_all(self) -> None:
        """Run and clear every captured task, in submission order."""
        pending, self.tasks = self.tasks, []
        for fn, args, kwargs in pending:
            fn(*args, **kwargs)


class TestRegistrationImageStore(unittest.TestCase):
    """Generation and refcount rules for published alignment images."""

    def test_stale_publication_is_discarded_and_unlinked(self) -> None:
        store = RegistrationImageStore()
        helper = _helper()
        first = store.begin(Space.Source, helper)
        second = store.begin(Space.Source, helper)
        stale = stage_host_image(host_image_payload(helper))
        assert stale is not None
        try:
            self.assertFalse(store.complete(Space.Source, first, stale))
            self.assertTrue(stale.released)
            self.assertFalse(store.is_ready(Space.Source))
            current = stage_host_image(host_image_payload(helper))
            assert current is not None
            self.assertTrue(store.complete(Space.Source, second, current))
            self.assertTrue(store.is_ready(Space.Source))
        finally:
            store.invalidate()

    def test_failed_publication_clears_pending(self) -> None:
        store = RegistrationImageStore()
        generation = store.begin(Space.Source, _helper())
        self.assertTrue(store.publish_pending())
        store.complete(Space.Source, generation, None)
        self.assertFalse(store.publish_pending())
        self.assertFalse(store.is_ready(Space.Source))

    def test_lease_defers_unlink_until_job_finishes(self) -> None:
        store = RegistrationImageStore()
        source = _helper(seed=1)
        target = _helper(seed=2)
        for space, helper in ((Space.Source, source), (Space.Target, target)):
            generation = store.begin(space, helper)
            staged = stage_host_image(host_image_payload(helper))
            assert staged is not None
            store.complete(space, generation, staged)
        lease = store.lease(source, target)
        assert lease is not None
        self.assertEqual(store.in_flight_holds(), 2)
        store.invalidate()
        # Segments stay mapped: a worker may still be attached to them.
        with lease.ref.source.image.attach() as view:
            self.assertEqual(view.shape, source.ImageWithMaskAsNoise.shape)
        lease.release()
        lease.release()

    def test_lease_requires_matching_helpers(self) -> None:
        store = RegistrationImageStore()
        source = _helper(seed=1)
        target = _helper(seed=2)
        for space, helper in ((Space.Source, source), (Space.Target, target)):
            generation = store.begin(space, helper)
            staged = stage_host_image(host_image_payload(helper))
            assert staged is not None
            store.complete(space, generation, staged)
        try:
            self.assertIsNone(store.lease(_helper(seed=3), target))
            self.assertIsNotNone(store.lease(source, target))
        finally:
            store.invalidate()

    @given(publish_count=st.integers(min_value=1, max_value=6),
           complete_order=st.permutations(list(range(6))))
    @settings(max_examples=25, deadline=None)
    def test_only_the_newest_generation_becomes_ready(
            self, publish_count: int, complete_order: list[int]) -> None:
        """Whatever order copies finish in, only the last publish can be ready."""
        store = RegistrationImageStore()
        helper = _helper(size=8)
        generations = [store.begin(Space.Source, helper) for _ in range(publish_count)]
        newest = generations[-1]
        installed: list[int] = []
        try:
            for slot in complete_order:
                if slot >= publish_count:
                    continue
                staged = stage_host_image(host_image_payload(helper))
                assert staged is not None
                if store.complete(Space.Source, generations[slot], staged):
                    installed.append(generations[slot])
            self.assertEqual(installed, [newest])
            self.assertTrue(store.is_ready(Space.Source))
        finally:
            store.invalidate()


class TestControllerPublish(unittest.TestCase):
    """Publish gating, staleness, and pool payloads on TransformController."""

    def test_headless_publish_is_synchronous(self) -> None:
        controller = TransformController(_mesh(4))
        try:
            with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
                qapp.instance.return_value = None
                controller.publish_registration_image(Space.Source, _helper())
            self.assertFalse(controller.registration_publish_pending)
            self.assertTrue(
                controller._registration_image_store.is_ready(Space.Source))
        finally:
            controller.invalidate_registration_images()

    def test_pump_waits_for_publication_then_submits_metadata(self) -> None:
        controller = TransformController(_mesh(4))
        source = _helper(seed=1)
        target = _helper(seed=2)
        thread_pool = _RecordingPool()
        process_pool = MagicMock()
        process_pool.add_task.return_value = MagicMock()
        try:
            with (
                patch("pyre.controllers.transformcontroller.QApplication") as qapp,
                patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool"),
                patch(
                    "pyre.controllers.transformcontroller.qt_post_to_main",
                    side_effect=lambda fn, *a: fn(*a),
                ),
                patch(
                    "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                    return_value=thread_pool,
                ),
                patch(
                    "pyre.controllers.transformcontroller.pools.GetGlobalLocalMachinePool",
                    return_value=process_pool,
                ),
                patch(
                    "pyre.controllers.transformcontroller.stage_image_pair",
                ) as stage_pair,
            ):
                qapp.instance.return_value = _fake_qapp()
                controller.publish_registration_image(Space.Source, source)
                controller.publish_registration_image(Space.Target, target)
                self.assertTrue(controller.registration_publish_pending)

                controller.enqueue_point_registrations(
                    [0],
                    alignment_area=np.array([16, 16], dtype=np.int32),
                    angles_to_search=np.array([0.0]),
                )
                # Gated: the point is queued and busy but nothing was dispatched.
                self.assertEqual(len(controller.queued_registration_ids), 1)
                process_pool.add_task.assert_not_called()

                thread_pool.run_all()
                self.assertTrue(controller.registration_images_published)
                process_pool.add_task.assert_called_once()
                args = process_pool.add_task.call_args.args
                self.assertIs(args[1], run_shared_control_point_alignment)
                self.assertIsInstance(args[3], SharedImagePairRef)
                stage_pair.assert_not_called()
        finally:
            controller.invalidate_registration_images()

    def test_reloaded_image_discards_in_flight_result(self) -> None:
        controller = TransformController(_mesh(4))
        source = _helper(seed=1)
        target = _helper(seed=2)
        thread_pool = _RecordingPool()
        process_pool = MagicMock()
        task = MagicMock()
        task.wait_return.return_value = _record()
        process_pool.add_task.return_value = task
        try:
            with (
                patch("pyre.controllers.transformcontroller.QApplication") as qapp,
                patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool"),
                patch(
                    "pyre.controllers.transformcontroller.qt_post_to_main",
                    side_effect=lambda fn, *a: fn(*a),
                ),
                patch(
                    "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                    return_value=thread_pool,
                ),
                patch(
                    "pyre.controllers.transformcontroller.pools.GetGlobalLocalMachinePool",
                    return_value=process_pool,
                ),
            ):
                qapp.instance.return_value = _fake_qapp()
                controller.publish_registration_image(Space.Source, source)
                controller.publish_registration_image(Space.Target, target)
                thread_pool.run_all()
                point_id = controller.point_id_for_index(0)
                assert point_id is not None
                snapshot = np.asarray(controller.TargetPoints[0], dtype=np.float64).copy()
                controller.enqueue_point_registrations(
                    [0],
                    alignment_area=np.array([16, 16], dtype=np.int32),
                    angles_to_search=np.array([0.0]),
                )
                self.assertEqual(controller._registration_image_store.in_flight_holds(), 2)

                # The user loads a different source image before the peak arrives.
                controller.publish_registration_image(Space.Source, _helper(seed=9))
                thread_pool.run_all()
                np.testing.assert_allclose(
                    np.asarray(controller.TargetPoints[0], dtype=np.float64), snapshot)
                self.assertEqual(controller._registration_image_store.in_flight_holds(), 0)
        finally:
            controller.invalidate_registration_images()

    def test_invalidate_cancels_queued_registrations(self) -> None:
        controller = TransformController(_mesh(4))
        thread_pool = _RecordingPool()
        with (
            patch("pyre.controllers.transformcontroller.QApplication") as qapp,
            patch(
                "pyre.controllers.transformcontroller.max_concurrent_point_alignments",
                return_value=1,
            ),
            patch(
                "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                return_value=thread_pool,
            ),
        ):
            qapp.instance.return_value = _fake_qapp()
            controller.enqueue_point_registrations(
                [0, 1, 2], align_fn=lambda **_: _record())
            self.assertEqual(controller._registration_queue.pending_count, 2)
            controller.invalidate_registration_images()
        self.assertEqual(controller._registration_queue.pending_count, 0)


class TestHostTransformSnapshot(unittest.TestCase):
    def test_host_transform_is_passed_through(self) -> None:
        mesh = _mesh(4)
        self.assertIs(host_transform_snapshot(mesh), mesh)

    def test_device_points_are_host_copied(self) -> None:
        class _DevicePoints:
            """Minimal CuPy-like array: not an ndarray, but has .get()."""

            def __init__(self, host: np.ndarray) -> None:
                self._host = host
                self.shape = host.shape
                self.dtype = host.dtype

            def get(self) -> np.ndarray:
                return self._host

        mesh = _mesh(4)
        host_points = np.asarray(mesh.points, dtype=np.float64)
        with patch.object(
                type(mesh), "__getstate__",
                lambda _self: {"_points": _DevicePoints(host_points)}):
            snapshot = host_transform_snapshot(mesh)
        self.assertIsNot(snapshot, mesh)
        self.assertIsInstance(snapshot.points, np.ndarray)  # type: ignore[attr-defined]


class TestContrastSettleNotifier(unittest.TestCase):
    """Rapid slider writes must republish once, per side."""

    def test_only_the_last_write_fires(self) -> None:
        scheduled: list = []
        fired: list[Space] = []
        notifier = ContrastSettleNotifier(
            fired.append,
            schedule=lambda _delay, fn: scheduled.append(fn),
        )
        for _ in range(5):
            notifier.note_contrast_write(Space.Source)
        for fn in scheduled:
            fn()
        self.assertEqual(fired, [Space.Source])

    def test_each_space_settles_independently(self) -> None:
        scheduled: list = []
        fired: list[Space] = []
        notifier = ContrastSettleNotifier(
            fired.append,
            schedule=lambda _delay, fn: scheduled.append(fn),
        )
        notifier.note_contrast_write(Space.Source)
        notifier.note_contrast_write(Space.Target)
        notifier.note_contrast_write(Space.Target)
        for fn in scheduled:
            fn()
        self.assertEqual(sorted(fired, key=int), [Space.Source, Space.Target])

    def test_cancel_drops_pending_callbacks(self) -> None:
        scheduled: list = []
        fired: list[Space] = []
        notifier = ContrastSettleNotifier(
            fired.append,
            schedule=lambda _delay, fn: scheduled.append(fn),
        )
        notifier.note_contrast_write(Space.Target)
        notifier.cancel()
        for fn in scheduled:
            fn()
        self.assertEqual(fired, [])


class TestStosStatePublishesOnLoad(unittest.TestCase):
    def _stos_state(self, controller: MagicMock):
        from pyre.state.stos import StosState

        return StosState(
            transform_controller=controller,
            image_manager=MagicMock(),
            image_viewmodel_manager=MagicMock(),
            image_loader=MagicMock(),
            window_manager=MagicMock(),
        )

    def test_publish_alignment_images_covers_both_sides(self) -> None:
        controller = MagicMock()
        state = self._stos_state(controller)
        source = _helper(seed=1)
        target = _helper(seed=2)
        state._fixed_image_permutations = source
        state._warped_image_permutations = target
        state.publish_alignment_images()
        spaces = [call.args[0] for call in controller.publish_registration_image.call_args_list]
        self.assertEqual(spaces, [Space.Source, Space.Target])

    def test_unloaded_side_publishes_none(self) -> None:
        controller = MagicMock()
        state = self._stos_state(controller)
        state.publish_alignment_images(Space.Source)
        controller.publish_registration_image.assert_called_once_with(Space.Source, None)

    def test_sync_registration_roles_republishes(self) -> None:
        from pyre.stos_registration import sync_stos_registration_roles

        controller = MagicMock()
        state = self._stos_state(controller)
        sync_stos_registration_roles(state, _helper(seed=1), _helper(seed=2))
        self.assertEqual(controller.publish_registration_image.call_count, 2)


if __name__ == "__main__":
    unittest.main()
