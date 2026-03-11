Pyre
====

A Python-based image registration and visualization tool for scientific image processing, developed as part of the Nornir project.

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

Pre-Install Requirements
-----------------------
    **Install git:** `http://git-scm.com/ <https://git-scm.com>`_

    **Open command Prompt or Terminal Window**

    1. Check active Python (version needs to be >= 3.9)::

        python --version

    2. If Python is not >= 3.9, install latest python: https://www.python.org/downloads/
        a. Be sure to check the option to add python to the environment variables.
    3. Close and reopen the prompt/terminal.
    4. Ensure new python is returned when executing --version command above.


Installing Pyre and its dependencies
------------------------------------
1. Create a new Python environment (recommended)::

    **Open a Command Prompt or Terminal Window**

    # Using venv
    python -m venv pyre-env

    # Activate the environment
    # On Windows:
    pyre-env\Scripts\activate
    # On Linux/Mac:
    source pyre-env/bin/activate

2. Install dependencies using the requirements file
    Download the requirements file directly from GitHub
    `requirements-v1.5.2.txt <https://raw.githubusercontent.com/jamesra/nornir-pyre/dev/requirements-v1.5.2.txt>`_

    Run the install command below from the same folder you downloaded the requirements into::

        pip install -r requirements-v1.5.2.txt


Running Pyre
------------
    Ensure python environment is active::

        pyre-env\Scripts\activate

    Start Pyre with the QT interface (recommended)::

        python -m pyre.main_qt

    Or use the legacy interface::

        python -m pyre


Checking the `repository <https://github.com/jamesra/nornir-pyre/blob/OpenGL>`_ for a later version of the requirements file is also advisable. (Docs updated May 2025)


Alternative Installation Methods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Using pip directly with git repositories**:

If you prefer to install the latest development versions directly, you can use::

    pip install git+https://github.com/jamesra/nornir-shared.git@dev-v1.5.2
    pip install git+https://github.com/jamesra/nornir-pools.git@dev-v1.5.2
    pip install git+https://github.com/jamesra/nornir-imageregistration.git@cupy-v1.6.5
    pip install git+https://github.com/jamesra/nornir-buildmanager.git@dev-v1.6.5
    pip install git+https://github.com/jamesra/nornir-pyre.git@dev-v1.5.2


Common Workflows
~~~~~~~~~~~~~~~

Image Registration
-----------------

1. Load a pair of images for registration:

   * Use File > Open STOS to load an existing transformation
   * Or use File > New STOS to create a new transformation between two images

2. Add control points:

   * Use Shift+Click to add corresponding points in both images
   * Use Alt+Shift+Click to add a point and auto-align it

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
   * Use mouse wheel to zoom
   * Use Tab to switch between different view modes

Usage
~~~~~

Mouse Controls
--------------

Left Button:
    * Click to select an existing point
    * Shift+Click to add a new point
    * Alt+Shift+Click to add a new point and auto-align
    * Click+drag to move an existing point
    * Ctrl+Click+drag to translate warped image
    * Alt+Click to move currently selected point to mouse position

Right Button:
    * Shift+Click to delete a point
    * Click+drag to move the view

Scroll wheel:
    * Zoom
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
    * Tab: Change properties of the view. A warped image may be displayed as it appears registered. The composite view will switch to a different view.

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
2. Try running with software rendering: `PYOPENGL_PLATFORM=software python -m pyre.main_qt`
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
