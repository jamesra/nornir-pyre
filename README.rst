Pyre
====

A Python-based image registration and visualization tool for scientific image processing, developed as part of the Nornir project.

Documentation
~~~~~~~~~~~~~

* **Full manual (umbrella):** https://nornir.github.io/
* **Windows install (end users):** https://nornir.github.io/packages/pyre_install.html
* **Development and packaging:** https://nornir.github.io/development/pyre_development.html
* **Related overview:** https://nornir.github.io/packages/other_packages.html

Overview
~~~~~~~~

Pyre (Python Registration Environment) is a powerful tool for visualizing, aligning, and registering large scientific image datasets. It provides an interactive interface for:

* Manual and automatic image alignment
* Visualization of image transformations
* Creation and editing of spatial transformations between images
* Management of image mosaics and volumes
* Integration with the broader Nornir image processing ecosystem

Pyre is particularly useful for neuroscience applications, including the alignment of serial section microscopy images, but can be applied to any domain requiring precise image registration.

Project Structure
~~~~~~~~~~~~~~~~

The nornir-pyre package is organized into several key modules:

* **pyre.gl_engine**: OpenGL rendering engine for high-performance image visualization
* **pyre.ui**: User interface components built with PyQt6
* **pyre.views**: View implementations for different visualization modes
* **pyre.state**: State management and manager implementations
* **pyre.controllers**: Active transform (and similar) state/behavior used by the UI and commands (e.g. TransformController)
* **pyre.commands**: Command pattern implementations for operations
* **pyre.interfaces**: Interface definitions for dependency injection

Installation
~~~~~~~~~~~~

Windows (recommended for lab users)
-----------------------------------

Download and run ``Pyre-<version>-Setup.exe`` from GitHub Releases. No Python, Git,
or virtual environment is required. See the install guide:

https://nornir.github.io/packages/pyre_install.html

Development install (monorepo)
------------------------------

Requires Python **3.13+** and an umbrella Nornir checkout with sibling packages.
Full setup, editable installs, and debugging are documented at:

https://nornir.github.io/development/pyre_development.html

Quick start after editable installs::

    pyre
    python -m pyre

Running Pyre
------------

With the environment active::

    pyre
    python -m pyre
    python -m pyre -stos path\to\section.stos

Software OpenGL fallback (development troubleshooting)::

    set PYOPENGL_PLATFORM=software
    pyre


Common Workflows
~~~~~~~~~~~~~~~

Image Registration
-----------------

1. Load a pair of images for registration:

   * Use File > Open STOS to load an existing transformation
   * Or use File > New STOS to create a new transformation between two images

2. Add control points (triangulation / standard STOS transforms with movable control points):

   * Use Shift+Click to add corresponding points in both images
   * Use Alt+Shift+Click to add a point and auto-align it

   Refined grid transforms do not support adding or removing control points via the UI (use triangulation or convert workflow if you need to edit the mesh).

3. Align the images:

   * Use Space to auto-align the selected point
   * Use Shift+Space to auto-align all points
   * Manually adjust points by dragging them

4. Save the transformation:

   * Use File > Save STOS to save the transformation

Mosaic Viewing
-------------

1. Load a mosaic:

   * Use File > Open Mosaic to load an existing mosaic file

2. Navigate the mosaic:

   * Use WASD keys or right-click drag to pan
   * Use mouse wheel to zoom; Shift+scroll scales the transform about the cursor when supported; Ctrl+scroll (and Ctrl+Shift+scroll for finer steps) rotates the transform when supported
   * Use Page Up / Page Down to change magnification

Usage
~~~~~

Mouse Controls
--------------

The bindings below apply to STOS registration views. Triangulation transforms support adding points; refined grid transforms do not (see workflows above).

Left Button:
    * Click to select an existing point
    * Shift+Click to add a new point
    * Alt+Shift+Click to add a new point and auto-align
    * Click+drag to move an existing point
    * Ctrl+Click+drag to translate warped image
    * Alt+Click to move currently selected point to mouse position

Right Button:
    * Shift+Click to delete a point (triangulation transforms; not available on refined grid transforms)
    * Click+drag to move the view

Scroll wheel:
    * Zoom
    * Shift+scroll to scale warped image about the cursor (rigid / similarity transforms)
    * Ctrl+scroll to rotate warped image
    * Ctrl+Shift+scroll to slowly rotate warped image

Keyboard Controls
-----------------

Navigation:
    * A, W, S, D: Move the view
    * Page Up/Down: Change the magnification

View Controls:
    * M: Match the view on all windows to look at the same point as the current window (Not Functional for Warped Image)
    * L: Show transform mesh lines
    * F: Flip the warped image
    * Tab: Toggle how the warped image is drawn (registered vs alternate display) on the shared transform. Applies to Source, Target, and Composite STOS windows.

Alignment:
    * Space: Auto-align the selected point
    * Shift+Space: Auto-align all points

Undo/Redo:
    * Ctrl+Z: Undo a step
    * Ctrl+X: Redo a step

Troubleshooting
~~~~~~~~~~~~~~

OpenGL Issues
------------
If you encounter OpenGL-related errors:

1. Ensure your graphics drivers are up to date
2. Try running with software rendering::

    set PYOPENGL_PLATFORM=software
    pyre
3. Check the console output for specific OpenGL context errors

Image Loading Issues
------------------
If images fail to load:

1. Verify the file paths are correct and accessible
2. Check that the image format is supported (TIFF, PNG, JPEG, etc.)
3. For large images, ensure you have sufficient RAM available

Performance Issues
----------------
If the application is running slowly:

1. Close other memory-intensive applications
2. For large images, consider using lower-resolution versions for alignment
3. Disable mesh line display (L key) when not needed

About
~~~~~

Pyre was developed by James Anderson and Drew Ferrell as part of the Nornir project, a suite of tools for scientific image processing and analysis. The project is particularly focused on neuroscience applications but is applicable to any domain requiring precise image registration and analysis.

For more information about the QT migration, see the QT_MIGRATION_README.md file.
