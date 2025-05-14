Pyre
====

A Python-based image registration and visualization tool written by James Anderson and Drew Ferrel

Installation
-----------

To install Pyre and its dependencies, follow these steps:

1. Create a new Python environment (recommended)::

    # Using venv
    python -m venv pyre-env

    # Activate the environment
    # On Windows:
    pyre-env\Scripts\activate
    # On Linux/Mac:
    source pyre-env/bin/activate

2. Install dependencies using the requirements file::

    pip install -r requirements-v1.5.2.txt

You can download the requirements file directly from GitHub:
`requirements-v1.5.2.txt <https://raw.githubusercontent.com/jamesra/nornir-pyre/dev/requirements-v1.5.2.txt>`_

Checking the `repository <https://github.com/jamesra/nornir-pyre/blob/OpenGL>`_ for a later version of the requirements file is also advisable. (Docs updated May 13th 2025)


Alternative Installation Methods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Using pip directly with git repositories**:

If you prefer to install the latest development versions directly, you can use::

    pip install git+https://github.com/jamesra/nornir-shared.git@dev-v1.5.2
    pip install git+https://github.com/jamesra/nornir-pools.git@dev-v1.5.2
    pip install git+https://github.com/jamesra/nornir-imageregistration.git@cupy-v1.6.5
    pip install git+https://github.com/jamesra/nornir-buildmanager.git@dev-v1.6.5
    pip install git+https://github.com/jamesra/nornir-pyre.git@dev-v1.5.2


Usage
-----

Mouse Controls
~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~

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

About
-----

Pyre was written by James Anderson and Drew Ferrell
