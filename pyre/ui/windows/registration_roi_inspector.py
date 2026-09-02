"""Non-modal window showing the source/target ROI pair used for single-point registration.

The window is kept as a singleton tool-window.  It refreshes itself each time
a control-point alignment result arrives via
:meth:`TransformController.AddAlignmentResultListener`.
"""

from __future__ import annotations

import logging

import numpy as np
import pyre
from numpy.typing import NDArray

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_DISPLAY_PX: int = 380


def _array_to_pixmap(arr: NDArray, size: int = _DISPLAY_PX) -> QPixmap:
    """Normalise a 2D float array and return a scaled grayscale QPixmap."""
    a = np.nan_to_num(np.asarray(arr, dtype=np.float64), nan=0.0)
    lo, hi = float(a.min()), float(a.max())
    a = (a - lo) / (hi - lo) if hi > lo else np.zeros_like(a)
    a8 = np.clip(a * 255, 0, 255).astype(np.uint8)
    h, w = a8.shape[:2]
    qimg = QImage(a8.data.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
    pxm = QPixmap.fromImage(qimg)
    return pxm.scaled(size, size,
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


def _composite_pixmap(target: NDArray, source: NDArray, size: int = _DISPLAY_PX) -> QPixmap:
    """Green = target, magenta = source overlay, scaled to *size* pixels."""
    def _norm(x: NDArray) -> NDArray:
        x = np.nan_to_num(np.asarray(x, dtype=np.float64), nan=0.0)
        lo, hi = float(x.min()), float(x.max())
        return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)

    g = _norm(target)
    m = _norm(source)
    rgb = np.clip(np.stack([m, g, m], axis=-1) * 255, 0, 255).astype(np.uint8)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888)
    pxm = QPixmap.fromImage(qimg)
    return pxm.scaled(size, size,
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


class _ImagePanel(QWidget):
    """One titled image panel with a statistics footer."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setFixedSize(_DISPLAY_PX, _DISPLAY_PX)
        self._image_label.setStyleSheet("background-color: #1a1a1a; color: #888;")
        self._image_label.setText(f"({title})")

        self._stats_label = QLabel("", self)
        self._stats_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._stats_label.setWordWrap(True)
        self._stats_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        header = QLabel(f"<b>{title}</b>", self)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)
        layout.addWidget(header)
        layout.addWidget(self._image_label)
        layout.addWidget(self._stats_label)

    def set_pixmap(self, pxm: QPixmap, stats: str = "") -> None:
        self._image_label.setPixmap(pxm)
        self._image_label.setText("")
        self._stats_label.setText(stats)

    def set_no_data(self, msg: str = "") -> None:
        self._image_label.setPixmap(QPixmap())
        self._image_label.setText(msg or "—")
        self._stats_label.setText("")


def _roi_stats(a: NDArray) -> str:
    return (f"shape {a.shape}  "
            f"mean {float(np.nanmean(a)):.3f}  "
            f"std {float(np.nanstd(a)):.3f}")


class RegistrationROIInspector(QWidget):
    """Non-modal tool window showing what was passed into the last point registration.

    Updated automatically via :meth:`update_from_record` which is called by the
    ``AlignmentResultListener`` hook on :class:`TransformController`.

    Six panels in a 2×3 grid:

    Row 1 — warped view (what registration sees):
      Col 1 : Source ROI  (source warped into target space via local rigid approx)
      Col 2 : Target ROI  (direct crop at the target control-point)
      Col 3 : Composite   (green = target, magenta = source)

    Row 2 — raw context (diagnosis):
      Col 1 : Raw source crop  (un-warped direct crop of source at the mapped coordinate)
      Col 2 : Source shifted by peak  (what aligned source looks like)
      Col 3 : Coordinates / metadata
    """

    _instance: RegistrationROIInspector | None = None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Registration ROI Inspector [{pyre.build_tag()}]")
        # Qt.WindowType.Window (rather than Tool) so this appears as its own entry on
        # the taskbar and can be selected/switched to independently of the main window.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._info_label = QLabel("No registration recorded yet.", self)
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("font-weight: bold;")

        # Row 1 — warped (what the correlator sees)
        self._source_panel = _ImagePanel("Source ROI  (rigid-warp into target space)", self)
        self._target_panel = _ImagePanel("Target ROI  (direct crop)", self)
        self._composite_panel = _ImagePanel("Composite  (green=target  magenta=source)", self)

        # Row 2 — raw context
        self._raw_source_panel = _ImagePanel("Raw source crop  (no rotation, same centre)", self)
        self._shifted_panel = _ImagePanel("Source shifted by peak", self)
        self._coord_panel = _CoordPanel(self)

        top_row = QHBoxLayout()
        top_row.addWidget(self._source_panel)
        top_row.addWidget(self._target_panel)
        top_row.addWidget(self._composite_panel)

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self._raw_source_panel)
        bottom_row.addWidget(self._shifted_panel)
        bottom_row.addWidget(self._coord_panel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self._info_label)
        layout.addLayout(top_row)
        layout.addLayout(bottom_row)
        self.adjustSize()

    @classmethod
    def show_instance(cls, parent: QWidget | None = None) -> RegistrationROIInspector:
        """Return the singleton, creating it if necessary, and bring it to front."""
        if cls._instance is None:
            cls._instance = cls(parent)
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()
        return cls._instance

    @classmethod
    def instance(cls) -> RegistrationROIInspector | None:
        return cls._instance

    def closeEvent(self, event) -> None:  # type: ignore[override]
        RegistrationROIInspector._instance = None
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Update from registration result

    def update_apply_status(self, point_id: int, applied: bool, reason: str) -> None:
        """Update the header bar to reflect whether the registration was actually applied."""
        current = self._info_label.text()
        if applied:
            status = f"  ✓ APPLIED"
            color = "#4fc35a"
        else:
            status = f"  ✗ DISCARDED  ({reason})"
            color = "#e05050"
        self._info_label.setStyleSheet(f"font-weight: bold; color: {color};")
        # Avoid duplicating a previous status suffix; strip any old one first.
        for marker in ("  ✓ APPLIED", "  ✗ DISCARDED"):
            idx = current.find(marker)
            if idx >= 0:
                current = current[:idx]
                break
        self._info_label.setText(current + status)

    def update_from_record(self, point_id: int, record: object) -> None:
        """Refresh all panels from a finished AlignmentRecord."""
        # Records every call (not just the last one that ends up on screen) so a stale
        # point id lingering in the shared selection set shows up as an unexpected extra
        # call here, distinct from whatever point the user just clicked.
        logger.info(
            "RegistrationROIInspector.update_from_record called for point_id=%s weight=%s",
            point_id, getattr(record, "weight", None))
        target_roi = getattr(record, "TargetROI", None)
        source_roi = getattr(record, "SourceROI", None)
        peak = getattr(record, "peak", None)
        weight = getattr(record, "weight", None)
        angle = getattr(record, "angle", None)
        raw_source = getattr(record, "RawSourceROI", None)
        target_pt = getattr(record, "TargetControlPoint", None)
        source_pt = getattr(record, "SourceControlPoint", None)
        rigid_angle_deg = getattr(record, "RigidAngleDeg", None)

        if target_roi is None or source_roi is None:
            self._info_label.setStyleSheet("font-weight: bold;")
            self._info_label.setText(
                f"Point {point_id}: registration result has no ROI data "
                "(single-point registrations only).")
            return

        try:
            target_np = np.asarray(target_roi, dtype=np.float64)
            source_np = np.asarray(source_roi, dtype=np.float64)
            peak_np = (np.asarray(peak, dtype=np.float64).ravel()
                       if peak is not None else None)

            peak_str = (f"({float(peak_np[0]):+.2f}, {float(peak_np[1]):+.2f})"
                        if peak_np is not None and peak_np.size >= 2 else "n/a")
            weight_str = f"{float(weight):.4f}" if weight is not None else "n/a"
            reg_angle_str = (f"{float(np.degrees(float(angle))):.2f}°"
                             if angle is not None else "n/a")

            self._info_label.setStyleSheet("font-weight: bold;")
            self._info_label.setText(
                f"Point {point_id}   |   "
                f"Peak (dy, dx): {peak_str}   |   "
                f"Weight: {weight_str}   |   "
                f"Reg angle: {reg_angle_str}"
            )

            # --- row 1 ---
            self._source_panel.set_pixmap(
                _array_to_pixmap(source_np), _roi_stats(source_np))
            self._target_panel.set_pixmap(
                _array_to_pixmap(target_np), _roi_stats(target_np))
            self._composite_panel.set_pixmap(
                _composite_pixmap(target_np, source_np))

            # --- row 2 ---
            if raw_source is not None:
                raw_np = np.nan_to_num(np.asarray(raw_source, dtype=np.float64), nan=0.0)
                self._raw_source_panel.set_pixmap(
                    _array_to_pixmap(raw_np), _roi_stats(raw_np))
            else:
                self._raw_source_panel.set_no_data("(not available)")

            if peak_np is not None and peak_np.size >= 2:
                dy = int(round(float(peak_np[0])))
                dx = int(round(float(peak_np[1])))
                shifted = np.roll(np.roll(source_np, dy, axis=0), dx, axis=1)
                self._shifted_panel.set_pixmap(
                    _array_to_pixmap(shifted),
                    f"Source rolled by dy={dy}, dx={dx}")
            else:
                self._shifted_panel.set_no_data("Peak not available")

            self._coord_panel.update_coords(
                point_id=point_id,
                target_pt=target_pt,
                source_pt=source_pt,
                rigid_angle_deg=rigid_angle_deg,
                peak=peak_np,
                weight=float(weight) if weight is not None else None,
                reg_angle=float(angle) if angle is not None else None,
            )

        except Exception:
            logger.warning(
                "RegistrationROIInspector: failed to render ROIs for point %s",
                point_id, exc_info=True)
            self._info_label.setText(
                f"Point {point_id}: error rendering ROIs — see log.")

        self.show()
        self.raise_()


class _CoordPanel(QWidget):
    """Text panel showing coordinates and diagnostic info."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_DISPLAY_PX, _DISPLAY_PX)
        self.setStyleSheet("background-color: #1a1a1a; color: #ddd; font-family: monospace;")

        self._label = QLabel("—", self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(
            "color: #ddd; font-family: monospace; font-size: 11px; padding: 8px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QLabel("<b>Coordinates / Diagnostics</b>", self)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("color: #fff; background-color: #1a1a1a; padding: 4px;")
        layout.addWidget(header)
        layout.addWidget(self._label)

    def update_coords(
            self,
            point_id: int,
            target_pt: NDArray | None,
            source_pt: NDArray | None,
            rigid_angle_deg: float | None,
            peak: NDArray | None,
            weight: float | None,
            reg_angle: float | None,
    ) -> None:
        lines = [f"Point ID : {point_id}"]

        if target_pt is not None:
            t = np.asarray(target_pt, dtype=np.float64).ravel()
            lines.append(f"Target   : y={t[0]:.1f}  x={t[1]:.1f}")
        if source_pt is not None:
            s = np.asarray(source_pt, dtype=np.float64).ravel()
            lines.append(f"Source   : y={float(s[0]):.1f}  x={float(s[1]):.1f}")
            if target_pt is not None:
                t = np.asarray(target_pt, dtype=np.float64).ravel()
                offset_y = float(t[0]) - float(s[0])
                offset_x = float(t[1]) - float(s[1])
                lines.append(f"t-s offset : dy={offset_y:.0f}  dx={offset_x:.0f}")

        if rigid_angle_deg is not None:
            lines.append(f"Rigid angle: {rigid_angle_deg:.2f}°")

        lines.append("")
        if peak is not None and peak.size >= 2:
            lines.append(f"Peak (dy,dx): ({float(peak[0]):+.2f}, {float(peak[1]):+.2f})")
        if weight is not None:
            lines.append(f"Weight     : {float(weight):.4f}")
        if reg_angle is not None:
            lines.append(f"Reg angle  : {float(np.degrees(float(reg_angle))):.2f}°")

        lines.append("")
        lines.append("If raw source ≈ target → warp bug")
        lines.append("If raw source ≠ target → mesh wrong")

        self._label.setText("\n".join(lines))
