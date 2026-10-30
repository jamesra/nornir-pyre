Pyre in-app Help (mouse and keyboard)
=====================================

Online manual: https://nornir.github.io/guides/pyre_use.html (Help → Online Manual)

The bindings below apply to the Source, Target, and Composite STOS windows.

Mouse Controls
--------------

Left button on a control point:
    * Click to select only that point
    * Shift+Click to add the point to, or remove it from, the selection
    * Drag to move the point
    * Shift+Drag to box-select, adding to or removing from the selection
    * Alt+Shift+Click to auto-align the point

Left button on empty space:
    * Click to clear the selection
    * Drag to box-select; Shift+Drag adds to or removes from the selection
    * Alt+Drag to lasso-select; Alt+Shift+Drag adds to or removes from the selection
    * Shift+Click to add a control point
    * Alt+Shift+Click to add a control point and auto-align it
    * Alt+Click to move the selected point to the cursor (exactly one point selected)
    * Ctrl+Drag to move all control points together, translating the mapped (source) image (one or no point selected)

Middle button:
    * Click to add a control point

Right button:
    * Drag to pan the view
    * Shift+Click on a control point to delete it

Scroll wheel:
    * Scroll to zoom about the cursor
    * Shift+Scroll to scale the transform about the cursor (only while no points are selected or queued for alignment)
    * Ctrl+Scroll to rotate the mapped section about the cursor; Ctrl+Shift+Scroll rotates in finer steps

By transform type:
    * Mesh and RBF: every binding above. Deleting keeps at least three control points.
    * Grid: points can be moved but not added or deleted; adding or deleting offers to convert the transform to a mesh. Source points cannot be moved in the Source window; move them in the Target or Composite window.
    * Rigid: no control points. Drag moves the mapped image in the Source or Composite window, and Ctrl+Scroll rotates only in the Composite window. Adding a point offers to convert the transform to a mesh.

Keyboard Controls
-----------------

Navigation:
    * W, A, S, D: Pan the view
    * Page Up / Page Down: Zoom out / zoom in
    * M: Match the Source, Target, and Composite windows to this window's view center and zoom

Display:
    * L: Show or hide transform mesh lines in this window
    * F: Flip the source (mapped) image (also Transform → Flip Source Image)

Alignment:
    * Mesh / RBF: Space auto-aligns the selected points and the point under the cursor; Shift+Space auto-aligns every point. Holding Space aligns each point once: sweep the cursor over points to align them in turn, and release and press again to re-align one
    * Grid: Space auto-aligns like Mesh. Shift+Space runs one grid-refine pass (settings dialog, then a live preview). Registration → Refine w/ Grid runs the chosen number of passes as one job with a preview after each pass; several Shift+Space presses are not the same as that job.
    * Rigid: Space refines the angle (+/-5 degrees in 1 degree steps); Shift+Space also refines scale (both are also in the Registration menu)
    * Esc (or Registration → Cancel Registration, or the status-bar Cancel): Cancel queued point alignments and any running refine/rotate job. Points already moved stay moved. While creating a point or dragging a selection box, Esc cancels that instead.

Editing:
    * Delete or Backspace: Delete the selected control points (Mesh and RBF)
    * Ctrl+Z: Undo a step
    * Ctrl+X: Redo a step

Files and help:
    * Ctrl+O: Open a STOS file
    * Ctrl+S: Save the STOS file
    * F1: Show this help
