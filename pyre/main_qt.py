#!/usr/bin/python

import sys
from PyQt6.QtWidgets import QApplication

from pyre.ui.windows.mosaicwindow_qt import MosaicWindow
from pyre.ui.windows.stoswindow_qt import StosWindow
from pyre.container import Container, IContainer
from pyre.interfaces.viewtype import ViewType


def main():
    """Main entry point for the QT version of the application"""
    # Create the QT application
    app = QApplication(sys.argv)

    # Create the dependency injection container
    container = Container()
    container.init_resources()
    container.wire(modules=[
        'pyre.ui.widgets.glpanel_qt',
        'pyre.ui.widgets.camerastatusbar_qt',
        'pyre.ui.widgets.imagetransformpanelbase_qt',
        'pyre.ui.windows.pyrewindows_qt',
        'pyre.ui.windows.mosaicwindow_qt',
        'pyre.ui.windows.stoswindow_qt'
    ])

    # Create the windows
    mosaic_window = MosaicWindow(None, 1, "Mosaic Viewer")

    # Create STOS windows for source, target, and composite views
    source_window = StosWindow(None, ViewType.Source, "Fixed Image", ViewType.Source)
    target_window = StosWindow(None, ViewType.Target, "Warped Image", ViewType.Target)
    composite_window = StosWindow(None, ViewType.Composite, "Composite Image", ViewType.Composite)

    # Show the windows
    mosaic_window.show()
    source_window.show()
    target_window.show()
    composite_window.show()

    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
