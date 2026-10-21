Pyre in-app Help (mouse and keyboard)
=====================================

Online manual: https://nornir.github.io/guides/pyre_use.html

Mouse Controls
--------------

The bindings below apply to STOS registration views. Triangulation transforms support adding points; refined grid transforms do not (see workflows above).

Left Button:
    * Click to select an existing point
    * Shift+Click to add a new point
    * Alt+Shift+Click to add a new point and auto-align
    * Click+drag to move an existing point
    * Ctrl+Click+drag to translate the mapped (source) image
    * Alt+Click to move currently selected point to mouse position

Right Button:
    * Shift+Click to delete a point (triangulation transforms; not available on refined grid transforms)
    * Click+drag to move the view

Scroll wheel:
    * Zoom
    * Shift+scroll to scale the source image about the cursor (rigid / similarity transforms)
    * Ctrl+scroll to rotate the mapped section (Composite view for rigid)
    * Ctrl+Shift+scroll to slowly rotate the mapped section

Keyboard Controls
-----------------

Navigation:
    * A, W, S, D: Move the view
    * Page Up/Down: Change the magnification

View Controls:
    * M: Match Source, Target, and Composite to the focused window's view center and magnification
    * L: Show transform mesh lines
    * F: Flip the source (mapped) image
    * Tab: Toggle how the source image is drawn (registered vs alternate display) on the shared transform. Applies to Source, Target, and Composite STOS windows.

Alignment:
    * Rigid: Space refines angle (+/-5 degrees at 1 degree steps); Shift+Space also refines scale
    * Mesh / RBF: Space auto-aligns the selected point; Shift+Space auto-aligns all points
    * Grid: Space auto-aligns the selected point; Shift+Space is one refine pass; Refine w/ Grid is the multi-pass job with per-pass preview
    * Esc (or the status-bar Cancel): cancel queued point alignments and any running refine/rotate job. Points already moved stay moved. While creating a point or dragging a selection box, Esc cancels that instead.

Undo/Redo:
    * Ctrl+Z: Undo a step
    * Ctrl+X: Redo a step
