"""wheel_scroll_steps: vertical first, then Windows Shift+wheel horizontal remap."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

from pyre.commands.extensions import wheel_scroll_steps


class TestWheelScrollSteps(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    @staticmethod
    def _event(*, angle: QPoint | None = None, pixel: QPoint | None = None) -> MagicMock:
        event = MagicMock()
        event.angleDelta.return_value = angle or QPoint(0, 0)
        event.pixelDelta.return_value = pixel or QPoint(0, 0)
        return event

    def test_vertical_angle_delta(self) -> None:
        self.assertAlmostEqual(
            wheel_scroll_steps(self._event(angle=QPoint(0, 120))), 1.0)
        self.assertAlmostEqual(
            wheel_scroll_steps(self._event(angle=QPoint(0, -240))), -2.0)

    def test_horizontal_angle_delta_when_vertical_is_zero(self) -> None:
        """Windows often reports Shift(+Alt)+wheel only on angleDelta.x."""
        self.assertAlmostEqual(
            wheel_scroll_steps(self._event(angle=QPoint(120, 0))), 1.0)
        self.assertAlmostEqual(
            wheel_scroll_steps(self._event(angle=QPoint(-120, 0))), -1.0)

    def test_vertical_angle_wins_over_horizontal(self) -> None:
        self.assertAlmostEqual(
            wheel_scroll_steps(self._event(angle=QPoint(120, -120))), -1.0)

    def test_pixel_delta_fallback(self) -> None:
        self.assertAlmostEqual(
            wheel_scroll_steps(self._event(pixel=QPoint(0, 15))), 1.0)
        self.assertAlmostEqual(
            wheel_scroll_steps(self._event(pixel=QPoint(-30, 0))), -2.0)

    def test_zero_when_no_delta(self) -> None:
        self.assertEqual(wheel_scroll_steps(self._event()), 0.0)


if __name__ == "__main__":
    unittest.main()
