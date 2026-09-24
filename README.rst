Pyre
====

A Python-based image registration and visualization tool for scientific image processing, developed as part of the Nornir project.

Documentation
~~~~~~~~~~~~~

* **Full manual (umbrella):** https://nornir.github.io/
* **Windows install (end users):** https://nornir.github.io/packages/pyre_install.html
* **Development and packaging:** https://nornir.github.io/development/pyre_development.html
* **Using Pyre (controls):** https://nornir.github.io/guides/pyre_use.html
* **Build a volume:** https://nornir.github.io/guides/build_volume.html
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

Mouse, keyboard, and alignment controls are in the manual:

https://nornir.github.io/guides/pyre_use.html
