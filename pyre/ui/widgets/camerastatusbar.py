from __future__ import annotations

from collections.abc import Callable

from dependency_injector.wiring import Provide, inject
from PyQt6.QtWidgets import QStatusBar, QWidget, QLabel, QProgressBar, QPushButton, QHBoxLayout

import nornir_imageregistration
from pyre.space import Space
from pyre.interfaces.readonlycamera import IReadOnlyCamera
from pyre.interfaces.managers.mouse_position_history_manager import IMousePositionHistoryManager
from pyre.container import IContainer
from pyre.registration_job import get_registration_job_runner


class CameraStatusBar(QStatusBar):
    _camera_window: QWidget  # Window that the camera is rendering to and we track mouse events on
    _window_height: int
    _window_width: int
    _labels: list[QLabel]  # Labels for each field in the status bar
    _job_title: QLabel
    _job_detail: QLabel
    _job_progress: QProgressBar
    _job_cancel: QPushButton
    _job_container: QWidget
    _cancel_handler: Callable[[], None] | None

    _mouse_position_history_manager: IMousePositionHistoryManager

    @property
    def camera(self) -> IReadOnlyCamera:
        return self._camera

    @camera.setter
    def camera(self, value: IReadOnlyCamera):
        self._camera = value

    @property
    def space(self) -> Space:
        return self._space

    @space.setter
    def space(self, value: Space):
        self._space = value

    @inject
    def __init__(self,
                 parent: QWidget,
                 camera: IReadOnlyCamera,
                 camera_window: QWidget,
                 mouse_position_history_manager: IMousePositionHistoryManager = Provide[
                     IContainer.mouse_position_history],
                 **kwargs):
        self._camera = camera
        self._camera_window = camera_window
        self._cancel_handler = None
        super(CameraStatusBar, self).__init__(parent, **kwargs)

        self._job_container = QWidget(self)
        job_layout = QHBoxLayout(self._job_container)
        job_layout.setContentsMargins(0, 0, 0, 0)
        job_layout.setSpacing(6)
        self._job_title = QLabel("", self._job_container)
        self._job_detail = QLabel("", self._job_container)
        self._job_progress = QProgressBar(self._job_container)
        self._job_progress.setMinimum(0)
        self._job_progress.setMaximum(100)
        self._job_progress.setFixedWidth(160)
        self._job_progress.setTextVisible(True)
        self._job_cancel = QPushButton("Cancel", self._job_container)
        self._job_cancel.clicked.connect(self._on_cancel_clicked)
        job_layout.addWidget(self._job_title)
        job_layout.addWidget(self._job_progress)
        job_layout.addWidget(self._job_detail)
        job_layout.addWidget(self._job_cancel)
        self._job_container.hide()
        self.addPermanentWidget(self._job_container, 0)

        # Create labels for each field
        self._labels = []
        for i in range(3):
            label = QLabel("")
            self._labels.append(label)
            self.addPermanentWidget(label, 1)  # Equal stretch for all labels

        # Connect to parent's resize event
        parent.resizeEvent = self._wrap_resize_event(parent.resizeEvent)  # type: ignore[assignment]

        # Connect to camera change events
        self._camera.AddOnChangeEventListener(self.onCameraChanged)

        self._window_width, self._window_height = camera_window.size().width(), camera_window.size().height()

        # Connect to mouse position history manager
        mouse_position_history_manager.add_mouse_position_update_event_listener(self.on_position_update)  # type: ignore[arg-type]

        get_registration_job_runner().register_status_bar(self)

    def set_cancel_handler(self, handler: Callable[[], None] | None) -> None:
        """Set the callback invoked when Cancel is pressed."""
        self._cancel_handler = handler

    def show_job(self, title: str) -> None:
        """Show the registration job progress strip."""
        self._job_title.setText(title)
        self._job_detail.setText("")
        self._job_progress.setRange(0, 0)  # indeterminate until first update
        self._job_cancel.setEnabled(True)
        self._job_container.show()

    def set_progress(self, current: int, total: int, detail: str) -> None:
        """Update progress values for the active registration job."""
        if total <= 0:
            self._job_progress.setRange(0, 0)
        else:
            self._job_progress.setRange(0, int(total))
            self._job_progress.setValue(max(0, min(int(current), int(total))))
        self._job_detail.setText(detail)

    def set_cancel_enabled(self, enabled: bool) -> None:
        self._job_cancel.setEnabled(enabled)

    def hide_job(self) -> None:
        """Hide the registration job progress strip."""
        self._job_container.hide()
        self._job_title.setText("")
        self._job_detail.setText("")
        self._job_progress.setRange(0, 100)
        self._job_progress.setValue(0)
        self._job_cancel.setEnabled(True)

    def _on_cancel_clicked(self) -> None:
        if self._cancel_handler is not None:
            self._cancel_handler()

    def _wrap_resize_event(self, original_handler):
        """Wrap the parent's resize event to also handle our size updates"""
        def wrapped_handler(event):
            # Call the original handler if it exists
            if original_handler:
                original_handler(event)
            # Then handle our size update
            self.onSize(event)
        return wrapped_handler

    def onCameraChanged(self):
        if self._window_height != 0:
            zoom_percentage = self.camera.scale * 100.0
            self.setStatusText(f'Zoom: {zoom_percentage:4.2f}%', 2)
        else:
            self.setStatusText('Zoom: 100%', 2)

    def on_position_update(self, space: Space, position: tuple[float, float]):
        self.update_status_bar(space, position)

    def onSize(self, event):
        self._window_width = self._camera_window.size().width()
        self._window_height = self._camera_window.size().height()

    def setStatusText(self, text: str, field: int):
        """Set the text for a specific field in the status bar"""
        if 0 <= field < len(self._labels):
            self._labels[field].setText(text)

    def update_status_bar(self, space: Space, point: tuple[float, float]):
        if space == Space.Source:
            src_txt = f'Source space: {point[nornir_imageregistration.iPoint.X]: 0.1f}x {point[nornir_imageregistration.iPoint.Y]: 0.1f}y' if point is not None else ''
            self.setStatusText(src_txt, 0)
        elif space == Space.Target:
            tgt_txt = f'Target space: {point[nornir_imageregistration.iPoint.X]: 0.1f}x {point[nornir_imageregistration.iPoint.Y]: 0.1f}y' if point is not None else ''
            self.setStatusText(tgt_txt, 1)
        else:
            raise ValueError("Invalid space")

        self.update()
