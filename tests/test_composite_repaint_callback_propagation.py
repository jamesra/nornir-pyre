"""Tests that a composite view's repaint callback reaches its sub-views.

CompositeTransformView creates its sub-views from already-registered viewmodels inside
__init__, while its own _repaint_callback is still None, and used to copy that None by
value. The owning panel repaired it immediately afterwards by assigning the sub-views'
private attributes, which closed the window in practice but left correctness dependent on
that call happening, in that order, from outside the class.

The callback is now a property that fans out, and a continuation that comes due with no
callback wired is remembered rather than silently dropped.
"""

from __future__ import annotations

import inspect
import unittest

from pyre.ui.widgets.imagetransformviewpanel import ImageTransformViewPanel
from pyre.views.compositetransformview import CompositeTransformView
from pyre.views.imagetransformview import ImageTransformView


def _bare_sub_view() -> ImageTransformView:
    """An ImageTransformView with only the attributes these paths touch."""
    view = object.__new__(ImageTransformView)
    view._repaint_callback = None
    view._lazy_mesh_pending_repaint = False
    view._lazy_mesh_continuation_dropped = False
    view._activate_context = lambda: None
    return view


class _ViewModelManager:
    """Only what CompositeTransformView.__del__ unsubscribes from."""

    @staticmethod
    def remove_change_event_listener(listener) -> None:
        del listener


def _bare_composite(source=None, target=None) -> CompositeTransformView:
    composite = object.__new__(CompositeTransformView)
    composite._repaint_callback = None
    composite._source_image_view = source
    composite._target_image_view = target
    # __del__ unsubscribes unconditionally, so a bare instance needs this present.
    composite._imageviewmodel_manager = _ViewModelManager()
    return composite


class TestTheCallbackFansOutToSubViews(unittest.TestCase):

    def test_assigning_reaches_both_sub_views(self) -> None:
        source, target = _bare_sub_view(), _bare_sub_view()
        composite = _bare_composite(source, target)

        def repaint() -> None:
            pass

        composite.repaint_callback = repaint

        self.assertIs(repaint, composite.repaint_callback)
        self.assertIs(repaint, source.repaint_callback)
        self.assertIs(repaint, target.repaint_callback)

    def test_a_missing_sub_view_is_skipped(self) -> None:
        source = _bare_sub_view()
        composite = _bare_composite(source, None)
        composite.repaint_callback = lambda: None  # must not raise
        self.assertIsNotNone(source.repaint_callback)

    def test_clearing_propagates_too(self) -> None:
        source, target = _bare_sub_view(), _bare_sub_view()
        composite = _bare_composite(source, target)
        composite.repaint_callback = lambda: None
        composite.repaint_callback = None
        self.assertIsNone(source.repaint_callback)
        self.assertIsNone(target.repaint_callback)

    def test_a_later_sub_view_inherits_the_current_value(self) -> None:
        """The path that already worked: creation after the panel wired the composite."""
        source = inspect.getsource(
            CompositeTransformView._handle_add_imageviewmodel_event)
        self.assertIn('view.repaint_callback = self._repaint_callback', source)


class TestADroppedContinuationIsRemembered(unittest.TestCase):
    """Losing the request ends the chain: the pending flag is cleared before the check."""

    def test_no_callback_records_the_drop(self) -> None:
        view = _bare_sub_view()
        view._lazy_mesh_pending_repaint = True
        view._request_lazy_mesh_repaint()
        self.assertFalse(view._lazy_mesh_pending_repaint)
        self.assertTrue(view._lazy_mesh_continuation_dropped,
                        'a request with nobody to service it must not vanish')

    def test_wiring_a_callback_resumes_the_build(self) -> None:
        view = _bare_sub_view()
        view._request_lazy_mesh_repaint()
        self.assertTrue(view._lazy_mesh_continuation_dropped)

        scheduled: list[bool] = []
        view._schedule_lazy_mesh_repaint = lambda: scheduled.append(True)
        view.repaint_callback = lambda: None

        self.assertEqual([True], scheduled, 'the dropped continuation should resume')
        self.assertFalse(view._lazy_mesh_continuation_dropped)

    def test_wiring_without_a_drop_schedules_nothing(self) -> None:
        view = _bare_sub_view()
        scheduled: list[bool] = []
        view._schedule_lazy_mesh_repaint = lambda: scheduled.append(True)
        view.repaint_callback = lambda: None
        self.assertEqual([], scheduled)

    def test_clearing_the_callback_never_schedules(self) -> None:
        view = _bare_sub_view()
        view._lazy_mesh_continuation_dropped = True
        scheduled: list[bool] = []
        view._schedule_lazy_mesh_repaint = lambda: scheduled.append(True)
        view.repaint_callback = None
        self.assertEqual([], scheduled, 'None cannot service a frame')

    def test_a_present_callback_is_invoked(self) -> None:
        view = _bare_sub_view()
        calls: list[bool] = []
        view._repaint_callback = lambda: calls.append(True)
        view._lazy_mesh_pending_repaint = True
        view._request_lazy_mesh_repaint()
        self.assertEqual([True], calls)
        self.assertFalse(view._lazy_mesh_continuation_dropped)


class TestThePanelUsesThePublicProperty(unittest.TestCase):

    def test_the_panel_no_longer_pokes_private_attributes(self) -> None:
        source = inspect.getsource(ImageTransformViewPanel._wire_tile_mesh_repaint)
        self.assertNotIn('_repaint_callback', source,
                         'propagation belongs to the composite, not the panel')
        self.assertIn('repaint_callback', source)

    def test_the_panel_does_not_walk_sub_views(self) -> None:
        source = inspect.getsource(ImageTransformViewPanel._wire_tile_mesh_repaint)
        for private in ('_source_image_view', '_target_image_view'):
            with self.subTest(attribute=private):
                self.assertNotIn(private, source)

    def test_only_the_setters_touch_the_backing_field(self) -> None:
        for cls in (ImageTransformView, CompositeTransformView):
            with self.subTest(cls=cls.__name__):
                assignments = [
                    line.strip() for line in inspect.getsource(cls).splitlines()
                    if '_repaint_callback =' in line and 'self._repaint_callback' in line]
                for line in assignments:
                    self.assertTrue(
                        line.startswith('self._repaint_callback ='),
                        f'unexpected write to the backing field: {line}')


if __name__ == '__main__':
    unittest.main()
