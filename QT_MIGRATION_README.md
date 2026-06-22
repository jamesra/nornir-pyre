# Nornir-Pyre QT Migration Guide

This document provides an overview of the migration from wxPython to QT for the nornir-pyre package.

## Overview

The nornir-pyre package has been converted from using wxPython to PyQt6 for its UI components. This migration provides
several benefits:

1. Better cross-platform compatibility
2. Modern UI components and styling
3. Better integration with OpenGL
4. Active development and maintenance of the QT framework

## Core Components Migrated

The following core components have been migrated from wxPython to QT:

1. **GLPanel**: Converted from `wx.glcanvas.GLCanvas` to `QOpenGLWidget`
2. **PyreWindowBase**: Converted from `wx.Frame` to `QMainWindow`
3. **CameraStatusBar**: Converted from `wx.StatusBar` to `QStatusBar`
4. **ImageTransformPanelBase**: Converted to use QT widgets and layouts
5. **MosaicWindow**: Example of a complete window conversion

## Migration Mapping

| wxPython Component   | QT Equivalent                     |
|----------------------|-----------------------------------|
| wx.Frame             | QMainWindow                       |
| wx.glcanvas.GLCanvas | QOpenGLWidget                     |
| wx.Dialog            | QDialog                           |
| wx.StatusBar         | QStatusBar                        |
| wx.Menu              | QMenu                             |
| wx.MenuBar           | QMenuBar                          |
| wx.FileDialog        | QFileDialog                       |
| wx.DirDialog         | QFileDialog (with Directory mode) |
| wx.BoxSizer          | QVBoxLayout, QHBoxLayout          |
| wx.EVT_* events      | QT signals and slots              |
| wx.SizeEvent         | QResizeEvent                      |

## Event Handling Changes

The event handling system has been completely changed from wxPython's event binding to QT's signal/slot mechanism:

1. wxPython: `self.Bind(wx.EVT_SIZE, self.OnSize)`
2. QT: `self.resizeEvent = self.on_resize` or `button.clicked.connect(self.on_button_click)`

## Layout Management Changes

Layout management has been changed from wxPython's sizers to QT's layout system:

1. wxPython:
   ```python
   self.sizer = wx.BoxSizer(wx.VERTICAL)
   self.sizer.Add(widget, 1, wx.EXPAND)
   self.SetSizer(self.sizer)
   ```

2. QT:
   ```python
   self.layout = QVBoxLayout(self)
   self.layout.addWidget(widget, 1)
   ```

## Dialog Changes

Dialog usage has been updated to use QT's dialog system:

1. wxPython:
   ```python
   dlg = wx.FileDialog(self, "Choose a file", "", "", "*.mosaic", wx.OPEN)
   if dlg.ShowModal() == wx.ID_OK:
       filename = dlg.GetFilename()
   dlg.Destroy()
   ```

2. QT:
   ```python
   dialog = QFileDialog(self)
   dialog.setWindowTitle("Choose a file")
   dialog.setNameFilter("Mosaic files (*.mosaic)")
   if dialog.exec() == QFileDialog.DialogCode.Accepted:
       filename = dialog.selectedFiles()[0]
   ```

## Dependencies

The requirements have been updated to replace wxPython with PyQt6:

1. Removed: `wxPython==4.2.3`
2. Added:
    - `PyQt6==6.6.1`
    - `PyQt6-Qt6==6.6.1`
    - `PyQt6-sip==13.6.0`

## Running the QT Version

A new main entry point has been created for the QT version of the application:

```python
python -m pyre.main_qt
```

## Migration Steps for Remaining Components

To migrate the remaining components of the application:

1. Create QT equivalents of each wxPython class with the same interface
2. Update event handling to use QT's signal/slot mechanism
3. Update layout management to use QT layouts
4. Update dialog usage to use QT dialogs
5. Test each component to ensure it works correctly

## File Naming Convention

QT implementations are stored in files with a `_qt` suffix to distinguish them from the original wxPython
implementations. For example:

- `glpanel.py` -> `glpanel_qt.py`
- `pyrewindows.py` -> `pyrewindows_qt.py`

This allows both implementations to coexist during the migration process.

## Testing

Each migrated component should be thoroughly tested to ensure it provides the same functionality as the original
wxPython implementation.

## Known Issues

- The QT implementation may have slight differences in appearance compared to the wxPython implementation
- Some advanced wxPython features may require custom implementation in QT
- The migration is not yet complete and some components still need to be converted

## Next Steps

1. Migrate the remaining UI components to QT
2. Update the application to use the QT components by default
3. Remove the wxPython dependencies once the migration is complete
4. Update documentation to reflect the QT implementation