"""Tests for STOS control-point visibility against panel cameras."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import numpy as np

import nornir_imageregistration
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.ui.control_point_visibility import (
    control_point_visible_in_stos_views,
    point_yx_in_camera_view,
)


def _mesh(n_points: int = 4) -> MeshWithRBFFallback:
    points = np.array(
        [
            [float(i * 10), float(i * 20), float(i * 100), float(i * 200)]
            for i in range(n_points)
        ],
        dtype=np.float64,
    )
    return MeshWithRBFFallback(points)


class TestPointYxInCameraView(unittest.TestCase):
    def test_inside_and_outside_bbox(self) -> None:
        camera = MagicMock()
        camera.VisibleImageBoundingBox = nornir_imageregistration.Rectangle.CreateFromBounds(
            (0.0, 0.0, 100.0, 200.0))
        self.assertTrue(point_yx_in_camera_view(np.array([50.0, 100.0]), camera))
        self.assertFalse(point_yx_in_camera_view(np.array([150.0, 50.0]), camera))
        self.assertFalse(point_yx_in_camera_view(np.array([np.nan, 10.0]), camera))


class TestControlPointVisibleInStosViews(unittest.TestCase):
    def test_headless_without_windows_is_visible(self) -> None:
        controller = TransformController(_mesh(4))
        self.assertTrue(control_point_visible_in_stos_views(controller, 0, window_manager=None))

    def test_visible_source_panel_contains_source_point(self) -> None:
        controller = TransformController(_mesh(4))
        source_yx = np.asarray(controller.SourcePoints[1], dtype=np.float64)
        camera = MagicMock()
        camera.VisibleImageBoundingBox = nornir_imageregistration.Rectangle.CreateFromBounds(
            (source_yx[0] - 5.0, source_yx[1] - 5.0, source_yx[0] + 5.0, source_yx[1] + 5.0))
        panel = MagicMock()
        panel.camera = camera
        panel.space = Space.Source
        window = MagicMock()
        window.isVisible.return_value = True
        window.imagepanel = panel
        manager = {ViewType.Source: window}
        self.assertTrue(control_point_visible_in_stos_views(controller, 1, window_manager=manager))
        self.assertFalse(control_point_visible_in_stos_views(controller, 3, window_manager=manager))

    def test_hidden_windows_treat_point_as_visible(self) -> None:
        controller = TransformController(_mesh(4))
        window = MagicMock()
        window.isVisible.return_value = False
        manager = {ViewType.Source: window}
        self.assertTrue(control_point_visible_in_stos_views(controller, 0, window_manager=manager))
