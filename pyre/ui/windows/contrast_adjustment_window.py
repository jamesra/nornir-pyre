"""Non-modal Source/Target contrast adjustment tool window."""

from __future__ import annotations

import logging

from dependency_injector.wiring import Provide, inject
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pyre.container import IContainer
from pyre.image_contrast import (
    GAMMA_MAX,
    GAMMA_MIN,
    LEVEL_MAX,
    LEVEL_MIN,
    approximate_image_histogram,
    contrast_for_space,
    normalize_contrast,
    reset_contrast_for_space,
    set_contrast_for_space,
)
from pyre.interfaces.managers import IImageManager, IWindowManager
from pyre.interfaces.viewtype import ViewType
from pyre.settings.app import AppSettings, ImageDisplayContrast
from pyre.space import Space
from pyre.ui.widgets.image_histogram_widget import ImageHistogramWidget
from pyre.ui.widgets.linked_slider_spin import LinkedSliderSpin

logger = logging.getLogger(__name__)

_AUTO_MIN_PERCENTILE: float = 0.005
_AUTO_MAX_PERCENTILE: float = 0.005
_VIEW_REFRESH_MS: int = 16


class ContrastAdjustmentWindow(QWidget):
    """Live min/max/gamma controls with histogram preview for Source or Target."""

    _instance: ContrastAdjustmentWindow | None = None

    _settings: AppSettings
    _image_manager: IImageManager
    _window_manager: IWindowManager
    _space: Space
    _updating: bool
    _layer_combo: QComboBox
    _histogram: ImageHistogramWidget
    _min_control: LinkedSliderSpin
    _max_control: LinkedSliderSpin
    _gamma_control: LinkedSliderSpin
    _view_refresh_timer: QTimer

    def __init__(
            self,
            *,
            initial_space: Space = Space.Source,
            settings: AppSettings | None = None,
            image_manager: IImageManager | None = None,
            window_manager: IWindowManager | None = None,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._updating = False
        self._space = Space.Target if initial_space == Space.Target else Space.Source
        self._settings = settings if settings is not None else self._resolve_settings()
        self._image_manager = (
            image_manager if image_manager is not None else self._resolve_image_manager()
        )
        self._window_manager = (
            window_manager if window_manager is not None else self._resolve_window_manager()
        )

        self.setWindowTitle("Contrast Adjustment")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowTitleHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumWidth(420)

        self._layer_combo = QComboBox(self)
        self._layer_combo.addItem("Source", Space.Source)
        self._layer_combo.addItem("Target", Space.Target)
        self._histogram = ImageHistogramWidget(self)
        self._min_control = LinkedSliderSpin(
            "Min", minimum=LEVEL_MIN, maximum=LEVEL_MAX, value=LEVEL_MIN,
            decimals=1, single_step=1.0, parent=self)
        self._max_control = LinkedSliderSpin(
            "Max", minimum=LEVEL_MIN, maximum=LEVEL_MAX, value=LEVEL_MAX,
            decimals=1, single_step=1.0, parent=self)
        self._gamma_control = LinkedSliderSpin(
            "Gamma", minimum=GAMMA_MIN, maximum=GAMMA_MAX, value=1.0,
            decimals=3, single_step=0.05, parent=self)

        auto_btn = QPushButton("Auto", self)
        reset_btn = QPushButton("Reset", self)
        close_btn = QPushButton("Close", self)
        button_row = QHBoxLayout()
        button_row.addWidget(auto_btn)
        button_row.addWidget(reset_btn)
        button_row.addStretch(1)
        button_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Layer:", self))
        selector_row.addWidget(self._layer_combo, stretch=1)
        layout.addLayout(selector_row)
        layout.addWidget(self._histogram)
        layout.addWidget(self._min_control)
        layout.addWidget(self._max_control)
        layout.addWidget(self._gamma_control)
        layout.addLayout(button_row)

        self._view_refresh_timer = QTimer(self)
        self._view_refresh_timer.setSingleShot(True)
        self._view_refresh_timer.timeout.connect(self._refresh_stos_views)

        self._layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        self._min_control.valueChanged.connect(self._on_min_changed)
        self._max_control.valueChanged.connect(self._on_max_changed)
        self._gamma_control.valueChanged.connect(self._on_gamma_changed)
        auto_btn.clicked.connect(self._on_auto)
        reset_btn.clicked.connect(self._on_reset)
        close_btn.clicked.connect(self.close)

        self.set_space(self._space)
        self._reload_histogram()

    @staticmethod
    @inject
    def _resolve_settings(settings: AppSettings = Provide[IContainer.settings]) -> AppSettings:
        return settings

    @staticmethod
    @inject
    def _resolve_image_manager(
            image_manager: IImageManager = Provide[IContainer.image_manager],
    ) -> IImageManager:
        return image_manager

    @staticmethod
    @inject
    def _resolve_window_manager(
            window_manager: IWindowManager = Provide[IContainer.window_manager],
    ) -> IWindowManager:
        return window_manager

    @classmethod
    def show_for_space(
            cls,
            space: Space,
            *,
            parent: QWidget | None = None,
            settings: AppSettings | None = None,
    ) -> ContrastAdjustmentWindow:
        """Raise the singleton window and switch to *space*."""
        existing = cls._instance
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.set_space(space)
                    existing.raise_()
                    existing.activateWindow()
                    return existing
            except RuntimeError:
                cls._instance = None
        window = cls(initial_space=space, settings=settings, parent=parent)
        cls._instance = window
        window.show()
        window.raise_()
        window.activateWindow()
        return window

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._view_refresh_timer.stop()
        if ContrastAdjustmentWindow._instance is self:
            ContrastAdjustmentWindow._instance = None
        super().closeEvent(event)

    def set_space(self, space: Space) -> None:
        """Select Source or Target and refresh controls from settings."""
        space = Space.Target if space == Space.Target else Space.Source
        self._space = space
        self._updating = True
        try:
            index = self._layer_combo.findData(space)
            if index >= 0:
                self._layer_combo.setCurrentIndex(index)
            self._load_controls_from_settings()
        finally:
            self._updating = False
        self._reload_histogram()

    def _current_contrast(self) -> ImageDisplayContrast:
        return contrast_for_space(self._space, settings=self._settings)

    def _load_controls_from_settings(self) -> None:
        contrast = self._current_contrast()
        self._min_control.set_value(float(contrast.min))
        self._max_control.set_value(float(contrast.max))
        self._gamma_control.set_value(float(contrast.gamma))
        self._histogram.set_markers(float(contrast.min), float(contrast.max))

    def _write_contrast(self, *, prefer_max: bool = True) -> None:
        """Persist contrast from controls and schedule a non-blocking view refresh."""
        before_min = self._min_control.value()
        before_max = self._max_control.value()
        before_gamma = self._gamma_control.value()
        contrast = normalize_contrast(
            ImageDisplayContrast(
                min=before_min,
                max=before_max,
                gamma=before_gamma,
            ),
            prefer_max=prefer_max,
        )
        set_contrast_for_space(self._space, contrast, self._settings)
        # Only push back into widgets when normalize nudged values; rewriting the
        # active slider mid-drag fights Qt and can freeze the tool window.
        if (
            abs(float(contrast.min) - before_min) > 1e-6
            or abs(float(contrast.max) - before_max) > 1e-6
            or abs(float(contrast.gamma) - before_gamma) > 1e-6
        ):
            self._updating = True
            try:
                self._min_control.set_value(float(contrast.min))
                self._max_control.set_value(float(contrast.max))
                self._gamma_control.set_value(float(contrast.gamma))
            finally:
                self._updating = False
        self._histogram.set_markers(float(contrast.min), float(contrast.max))
        self._schedule_view_refresh()

    def _schedule_view_refresh(self) -> None:
        """Coalesce GL updates to ~60 Hz without nested processEvents."""
        self._view_refresh_timer.start(_VIEW_REFRESH_MS)

    def _refresh_stos_views(self) -> None:
        """Ask visible STOS GL panels to redraw asynchronously."""
        from pyre.ui.windows.stoswindow import StosWindow

        for vt in (ViewType.Composite, ViewType.Source, ViewType.Target):
            if vt not in self._window_manager:
                continue
            win = self._window_manager[vt]
            if not isinstance(win, StosWindow) or not win.isVisible():
                continue
            panel = win.imagepanel
            mark_dirty = getattr(panel, "mark_image_layer_dirty", None)
            if callable(mark_dirty):
                mark_dirty()
            panel.glcanvas.update()

    def _on_layer_changed(self, _index: int) -> None:
        if self._updating:
            return
        data = self._layer_combo.currentData()
        space = Space.Target if data == Space.Target else Space.Source
        self._space = space
        self._updating = True
        try:
            self._load_controls_from_settings()
        finally:
            self._updating = False
        self._reload_histogram()

    def _on_min_changed(self, _value: float) -> None:
        if self._updating:
            return
        self._write_contrast(prefer_max=True)

    def _on_max_changed(self, _value: float) -> None:
        if self._updating:
            return
        self._write_contrast(prefer_max=False)

    def _on_gamma_changed(self, _value: float) -> None:
        if self._updating:
            return
        self._write_contrast()

    def _on_auto(self) -> None:
        """Set min/max from histogram percentiles; leave gamma unchanged."""
        hist = self._histogram_for_current_layer()
        if hist is None or hist.NumSamples <= 0:
            return
        lo, hi = hist.AutoLevel(_AUTO_MIN_PERCENTILE, _AUTO_MAX_PERCENTILE)
        gamma = self._gamma_control.value()
        set_contrast_for_space(
            self._space,
            ImageDisplayContrast(min=float(lo), max=float(hi), gamma=float(gamma)),
            self._settings,
        )
        self._updating = True
        try:
            self._load_controls_from_settings()
        finally:
            self._updating = False
        self._schedule_view_refresh()

    def _on_reset(self) -> None:
        """Restore identity contrast for the selected layer."""
        reset_contrast_for_space(self._space, self._settings)
        self._updating = True
        try:
            self._load_controls_from_settings()
        finally:
            self._updating = False
        self._schedule_view_refresh()

    def _view_key(self) -> ViewType:
        return ViewType.Target if self._space == Space.Target else ViewType.Source

    def _histogram_for_current_layer(self):
        key = self._view_key()
        try:
            helper = self._image_manager[key]
        except KeyError:
            return None
        try:
            return approximate_image_histogram(helper.Image)
        except Exception:
            logger.exception("Failed to build contrast histogram")
            return None

    def _reload_histogram(self) -> None:
        contrast = self._current_contrast()
        hist = self._histogram_for_current_layer()
        self._histogram.set_histogram(
            hist,
            min_marker=float(contrast.min),
            max_marker=float(contrast.max),
        )
