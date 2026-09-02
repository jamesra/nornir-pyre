"""
Created on Oct 19, 2012

@author: u0490822
"""

from typing import Callable
import warnings

import OpenGL.GL as gl
import numpy as np
# from imageop import scale
from numpy.typing import NDArray

from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions

from pyre.qt_eventmanager import qt_post_to_main

import nornir_imageregistration
from nornir_imageregistration import cp
import nornir_imageregistration.transforms.base
import nornir_imageregistration.transforms.triangulation
import pyre
from pyre.gl_engine import DynamicVAO, GLBuffer, GLIndexBuffer
import pyre.gl_engine.shaders as shaders
from pyre.space import Space
from pyre.views.gltiles import RenderCache, RenderDataMap, TileGLObjects
import pyre.views.gltiles as gltiles
from pyre.views.interfaces import IImageTransformView
from pyre.controllers.transformcontroller import TransformController
from pyre.controllers.transform_display import TileRefreshHint
from pyre.interfaces.viewtype import ViewType
from pyre.perf_debug import timed
import pyre.image_contrast as image_contrast

_LAZY_TILE_MESH_BUDGET = 8


def mesh_overlay_verts_xy(points: NDArray[np.floating]) -> NDArray[np.floating]:
    """Flip YX control points to XY for mesh-line overlay; host array for DrawTriangles."""
    xp = cp.get_array_module(points)
    return nornir_imageregistration.EnsureNumpyArray(xp.fliplr(points))


class ImageTransformView(IImageTransformView):
    """
    Combines an image and a transform to render an image.
    Images are divided into a grid of tiles.  Tiles are sized
    to fit within texture memory limits of the GPU.
    Read-only operations used for rendering the graphics.
    """

    _rendercache: RenderCache | None  # The cache of rendered data
    _z: float
    _image_viewmodel: pyre.viewmodels.ImageViewModel
    _image_mask_viewmodel: pyre.viewmodels.ImageViewModel | None
    _transform_controller: TransformController | None = None
    Debug: bool
    _gl_initialized: bool = False
    _tile_render_data: RenderDataMap
    _built_mesh_tiles: set[tuple[int, int]]
    _lazy_mesh_pending_repaint: bool
    _eager_tile_meshes: bool
    _image_space: Space  # The space the image is in
    _activate_context: Callable[
        [], None]  # A function we can call to ensure the view's GL context is current, must be used before creating GL Objects

    _gl_funcs: QOpenGLFunctions
    _repaint_callback: Callable[[], None] | None = None
    # A continuation came due while no callback was wired, so the budgeted mesh is
    # unfinished with nothing scheduled to resume it. Cleared by wiring a callback.
    _lazy_mesh_continuation_dropped: bool = False

    @property
    def repaint_callback(self) -> Callable[[], None] | None:
        """Function that asks this view's panel for another frame."""
        return self._repaint_callback

    @repaint_callback.setter
    def repaint_callback(self, value: Callable[[], None] | None) -> None:
        self._repaint_callback = value
        if value is not None and self._lazy_mesh_continuation_dropped:
            # Resume a chain that broke before wiring; without this the remaining tiles
            # wait for an unrelated repaint, which is how a composite FBO renders empty.
            self._lazy_mesh_continuation_dropped = False
            self._schedule_lazy_mesh_repaint()

    @property
    def gl(self) -> QOpenGLFunctions:
        """Set of OpenGL functions for the context this view operates within"""
        return self._gl_funcs

    @property
    def width(self) -> int:
        if self._image_viewmodel is None:
            return 1

        return self._image_viewmodel.width

    @property
    def height(self) -> int:
        if self._image_viewmodel is None:
            return 1

        return self._image_viewmodel.height

    @property
    def image_view_model(self) -> pyre.viewmodels.ImageViewModel:
        return self._image_viewmodel

    @image_view_model.setter
    def image_view_model(self, value: pyre.viewmodels.ImageViewModel):
        self._image_viewmodel = value
        if value is not None:
            self.create_objects()

    @property
    def image_mask_view_model(self) -> pyre.viewmodels.ImageViewModel | None:
        return self._image_mask_viewmodel

    @property
    def transform(self) -> nornir_imageregistration.ITransform:
        return self._transform_controller.TransformModel  # type: ignore[union-attr]

    @property
    def transform_controller(self) -> TransformController | None:
        return self._transform_controller

    @transform_controller.setter
    def transform_controller(self, value: TransformController):
        if self._transform_controller is not None:
            self._transform_controller.RemoveOnChangeEventListener(self.OnTransformChanged)
            self._transform_controller.RemoveOnPointMovedEventListener(self.OnPointMoved)

        self._transform_controller = value

        if value is not None:
            if not isinstance(value, TransformController):
                raise ValueError(f"Expected _transform_controller type, got {value}")
            self._transform_controller.AddOnChangeEventListener(self.OnTransformChanged)
            self._transform_controller.AddOnPointMovedEventListener(self.OnPointMoved)

        self.OnTransformChanged(value)

    @property
    def z(self) -> float:
        return self._z

    @z.setter
    def z(self, value: float):
        self._z = value

    def __init__(self,
                 space: Space,
                 activate_context: Callable[[], None],
                 gl_funcs: QOpenGLFunctions,
                 image_view_model: pyre.viewmodels.ImageViewModel | None = None,
                 image_mask_view_model: pyre.viewmodels.ImageViewModel | None = None,
                 transform_controller: TransformController | None = None,
                 *,
                 eager_tile_meshes: bool = False,
                 warp_into_target_display: bool = False,
                 ):
        """
        Constructor
        :param imageviewmodel image_view_model: Textures for image
        :param transform transform_controller: nornir_imageregistration transform
        :param warp_into_target_display: When True (composite source FBO), build a
            deformable mesh so the source image is drawn in target display space.
            Target images and standalone Source panels use static tile quads.
        """
        self._gl_funcs = gl_funcs
        self._activate_context = activate_context
        self._tile_render_data = {}
        self._built_mesh_tiles = set()
        self._lazy_mesh_pending_repaint = False
        self._eager_tile_meshes = eager_tile_meshes
        self._warp_into_target_display = warp_into_target_display
        self._image_space = space
        self._rendercache = RenderCache()
        self._image_viewmodel = image_view_model  # type: ignore[assignment]
        self._image_mask_viewmodel = image_mask_view_model
        self._transform_controller = transform_controller  # type: ignore[assignment]
        self._z = 0.5
        self._gl_initialized = False

        if self._transform_controller is not None:
            self._transform_controller.AddOnChangeEventListener(self.OnTransformChanged)
            self._transform_controller.AddOnPointMovedEventListener(self.OnPointMoved)

        self.Debug = False

        qt_post_to_main(self.create_objects, activate_context=self._activate_context)

    def create_objects(self):
        """Initialize GL objects"""
        # Ensure we have a valid context before proceeding
        self._activate_context()
        
        if not self._gl_initialized:
            self._gl_initialized = True

        if self._uses_lazy_mesh_build():
            return
        tc = self._transform_controller
        if tc is not None and tc.interactive_edit_in_progress:
            return
        self.update_all_tile_buffers()

    def _use_static_tile_quads(self) -> bool:
        """True when this view draws the image in native space (no control-point warp mesh)."""
        if self.transform is not None and gltiles.is_rigid_transform(self.transform):
            return True
        tc = self._transform_controller
        if tc is not None and tc.display_strategy.uses_static_tile_quads():
            return True
        # Target image is always native target coordinates.
        if self._image_space == Space.Target:
            return True
        # Source image warps into target only for the composite source FBO.
        if self._image_space == Space.Source and not self._warp_into_target_display:
            return True
        return False

    def _uses_lazy_mesh_build(self) -> bool:
        """True when tile meshes should be built incrementally for the visible viewport."""
        if self._eager_tile_meshes:
            return False
        if self._use_static_tile_quads():
            return False
        return True

    def _invalidate_tile_meshes(self) -> None:
        """Drop tile mesh data so the next draw rebuilds visible tiles only."""
        self._tile_render_data.clear()
        self._built_mesh_tiles.clear()

    def _tile_mesh_is_ready(self, grid_coords: tuple[int, int]) -> bool:
        render_data = self._tile_render_data.get(grid_coords)
        return render_data is not None and render_data.mesh_populated

    def _rbf_extrapolate_enabled(self) -> bool:
        """False until TransformController finishes off-UI RBF weight precompute.

        Also False during interactive drag so a failed tile patch cannot rebuild
        RBF weights on the UI thread.
        """
        tc = self._transform_controller
        if tc is None:
            return True
        if tc.interactive_edit_in_progress:
            return False
        return tc.rbf_prewarm_ready

    def _build_tile_mesh(self, grid_coords: tuple[int, int]) -> None:
        """Build CPU and GL mesh data for one tile coordinate."""
        if self._image_viewmodel is None or self.transform is None:
            return
        cpu_entry = self._get_or_build_cpu_entry(grid_coords)
        gltiles._update_tile_buffers(
            self.transform,
            grid_coords,
            self._image_viewmodel.TextureSize,  # type: ignore[arg-type]
            self._image_space,
            get_or_create_tile_globjects=self.get_or_create_tile_globjects,
            shared_cpu_entry=cpu_entry,
            force_static_quads=self._use_static_tile_quads(),
            extrapolate=self._rbf_extrapolate_enabled())
        if self._tile_mesh_is_ready(grid_coords):
            self._built_mesh_tiles.add(grid_coords)

    def _ensure_visible_tile_meshes(
            self,
            visible_coords: set[tuple[int, int]] | None,
            *,
            max_tiles: int | None = _LAZY_TILE_MESH_BUDGET) -> None:
        """Build meshes for visible tiles, optionally capped per call for responsiveness."""
        if visible_coords is None or self._image_viewmodel is None or self.transform is None:
            return
        if not self._uses_lazy_mesh_build():
            return
        tc = self._transform_controller
        if tc is not None and tc.interactive_edit_in_progress:
            return

        self._activate_context()
        built = 0
        remaining = False
        for grid_coords in sorted(visible_coords):
            if self._tile_mesh_is_ready(grid_coords):
                continue
            if max_tiles is not None and built >= max_tiles:
                remaining = True
                break
            self._build_tile_mesh(grid_coords)
            built += 1
        if remaining:
            self._schedule_lazy_mesh_repaint()

    def _schedule_lazy_mesh_repaint(self) -> None:
        """Request another frame so budgeted mesh builds can continue."""
        if self._lazy_mesh_pending_repaint:
            return
        self._lazy_mesh_pending_repaint = True
        qt_post_to_main(self._request_lazy_mesh_repaint,
                        activate_context=self._activate_context)

    def _request_lazy_mesh_repaint(self) -> None:
        self._lazy_mesh_pending_repaint = False
        if self._repaint_callback is None:
            # Dropping this silently ends the continuation chain: the pending flag is
            # already cleared, so nothing reschedules and the remaining tiles never build.
            # Record it so wiring a callback resumes the build. (#167)
            self._lazy_mesh_continuation_dropped = True
            return
        self._repaint_callback()

    def update_visible_tile_meshes(
            self,
            visible_rect: nornir_imageregistration.Rectangle | None,
            *,
            margin_tiles: int = 1,
            max_tiles: int | None = _LAZY_TILE_MESH_BUDGET) -> None:
        """Incrementally build meshes for tiles intersecting the viewport.

        When ``visible_rect`` is None, budget-build the full tile grid (used by
        composite FBO layers where display-space culls are unreliable).
        """
        if not self._gl_initialized:
            return
        if self._image_viewmodel is None or self.transform is None:
            return
        if not self._uses_lazy_mesh_build():
            # Static quads are rebuilt during paintGL. Uploading from camera-changed
            # (outside paintGL) makeCurrent() can raise GL_INVALID_OPERATION and blank the view.
            return

        if visible_rect is None:
            visible = set(self._image_viewmodel.generate_grid_indicies())
        else:
            expanded = gltiles.expand_visible_rectangle_by_tiles(
                visible_rect,
                tuple(int(v) for v in self._image_viewmodel.TextureSize),  # type: ignore[arg-type]
                margin_tiles=margin_tiles)
            visible = gltiles.tile_coords_for_visible_bounds(
                self.height, self.width,
                self._image_viewmodel.TextureSize,  # type: ignore[arg-type]
                expanded)
            if visible is None:
                visible = set(self._image_viewmodel.generate_grid_indicies())
        self._ensure_visible_tile_meshes(visible, max_tiles=max_tiles)

    def OnTransformChanged(self, transform_controller: TransformController | None = None):
        """Full tile mesh rebuild after transform changes (skipped during interactive drag)."""
        if not self._gl_initialized:
            return
        tc = transform_controller if transform_controller is not None else self._transform_controller
        if tc is not None and tc.interactive_edit_in_progress:
            hint = tc.display_strategy.on_model_changed(interactive=True)
            if hint == TileRefreshHint.NONE:
                return
        uses_quads = self._use_static_tile_quads()
        has_tiles = bool(self._tile_render_data)
        tiles_are_rigid = has_tiles and all(
            getattr(t, "is_rigid_quad", False) for t in self._tile_render_data.values())
        if uses_quads:
            # Rebuild when empty or when leftover mesh tiles remain after rigid←mesh.
            needs_rigid_init = (not has_tiles) or (not tiles_are_rigid)
            if needs_rigid_init:
                self.update_all_tile_buffers()
            return
        # Mesh path: drop stale rigid quads after rigid→mesh replace.
        self._invalidate_tile_meshes()
        if not self._uses_lazy_mesh_build():
            self.update_all_tile_buffers()

    def OnPointMoved(self, transform_controller: TransformController, indices: NDArray[np.integer]):
        """Incremental tile patch update for control point drag."""
        if not self._gl_initialized:
            return
        if self._use_static_tile_quads():
            return
        hint = transform_controller.display_strategy.on_point_moved(indices)
        if hint != TileRefreshHint.INCREMENTAL:
            return
        self.update_tiles_for_point_indices(indices)
        if self._repaint_callback is not None:
            self._repaint_callback()

    def _view_model_cache_id(self) -> int:
        return id(self._image_viewmodel)

    def _get_or_build_cpu_entry(self, grid_coords: tuple[int, int]) -> 'pyre.controllers.tile_mesh_cache.TileMeshCpuEntry':
        from pyre.controllers.tile_mesh_cache import TileMeshCpuEntry

        assert self._transform_controller is not None
        assert self._image_viewmodel is not None
        cache = self._transform_controller.tile_mesh_cache
        vm_id = self._view_model_cache_id()
        entry = cache.get(vm_id, self._image_space, grid_coords)
        want_static = self._use_static_tile_quads()
        if entry is not None and entry.is_rigid_quad == want_static:
            return entry
        render_data = self.get_or_create_tile_globjects(grid_coords[0], grid_coords[1])
        entry = gltiles.build_tile_mesh_cpu(
            self.transform,
            grid_coords,
            self._image_viewmodel.TextureSize,  # type: ignore[arg-type]
            self._image_space,
            cached_entry=render_data,
            force_static_quads=want_static,
            extrapolate=self._rbf_extrapolate_enabled())
        cache.put(vm_id, self._image_space, grid_coords, entry)
        return entry

    def update_tiles_for_point_indices(self, indices: NDArray[np.integer],
                                       visible_rect: nornir_imageregistration.Rectangle | None = None):
        """Update only tiles affected by moved control points.

        During interactive drag, existing deformable meshes are patched in place
        from live control points instead of remeshing via Transform().
        """
        if self._image_viewmodel is None or self.transform is None or self._transform_controller is None:
            return
        self._activate_context()
        if not isinstance(self.transform, nornir_imageregistration.IControlPoints):
            self.update_all_tile_buffers(visible_rect=visible_rect)
            return

        tile_coords = gltiles.tile_coords_for_control_points(
            self.height, self.width,
            self._image_viewmodel.TextureSize,  # type: ignore[arg-type]
            indices,
            self.transform)
        visible = gltiles.tile_coords_for_visible_bounds(
            self.height, self.width,
            self._image_viewmodel.TextureSize,  # type: ignore[arg-type]
            visible_rect)
        if visible is not None:
            tile_coords &= visible

        if self._transform_controller.patch_live_tile_vertices and tile_coords:
            if isinstance(self.transform, nornir_imageregistration.transforms.IGridTransform):
                mapper = gltiles.source_to_target_mapper_for_interactive_drag(self.transform)
                if mapper is not None:
                    for grid_coords in tile_coords:
                        render_data = self._tile_render_data.get(grid_coords)
                        if render_data is None:
                            continue
                        gltiles.try_patch_tile_vertices_from_control_points(render_data, mapper)
            else:
                edit_space = self._transform_controller.interactive_edit_space
                if edit_space is None:
                    edit_space = Space.Target
                target_points = nornir_imageregistration.EnsureNumpyArray(self.transform.TargetPoints)
                source_points = nornir_imageregistration.EnsureNumpyArray(self.transform.SourcePoints)
                for grid_coords in tile_coords:
                    render_data = self._tile_render_data.get(grid_coords)
                    if render_data is None:
                        continue
                    gltiles.try_patch_tile_vertices_from_stencil(
                        render_data, target_points, source_points, indices, edit_space)
            return

        self._transform_controller.tile_mesh_cache.invalidate_tiles(tile_coords)

        with timed(f'update_tiles_for_points n={len(tile_coords)}'):
            for grid_coords in tile_coords:
                gltiles._update_tile_buffers(
                    self.transform,
                    grid_coords,
                    self._image_viewmodel.TextureSize,  # type: ignore[arg-type]
                    self._image_space,
                    get_or_create_tile_globjects=self.get_or_create_tile_globjects,
                    shared_cpu_entry=None,
                    force_static_quads=self._use_static_tile_quads(),
                    extrapolate=self._rbf_extrapolate_enabled())

    def update_all_tile_buffers(self, visible_rect: nornir_imageregistration.Rectangle | None = None):
        """Update the buffers for all tiles in the image viewmodel (or visible subset)."""
        unused_grid_coords = set(self._tile_render_data.keys())

        # Ensure we have a valid context before proceeding
        self._activate_context()

        # Make sure we have a valid transform and image viewmodel
        if self._image_viewmodel is None or self.transform is None:
            return

        try:
            # Check if OpenGL is initialized properly
            # if not gl.glGetIntegerv(gl.GL_ARRAY_BUFFER_BINDING):
            #     # If not initialized, it's likely we don't have a valid context yet
            #     # Schedule a retry after a brief delay
            #     qt_post_to_main(self.update_all_tile_buffers)
            #     return

            visible = gltiles.tile_coords_for_visible_bounds(
                self.height, self.width,
                self._image_viewmodel.TextureSize,  # type: ignore[arg-type]
                visible_rect)

            with timed(f'update_all_tile_buffers cols={self._image_viewmodel.NumCols} rows={self._image_viewmodel.NumRows}'):
                for grid_coords in self._image_viewmodel.generate_grid_indicies():
                    if visible is not None and grid_coords not in visible:
                        continue
                    cpu_entry = self._get_or_build_cpu_entry(grid_coords)
                    gltiles._update_tile_buffers(self.transform,
                                                 grid_coords,
                                                 self._image_viewmodel.TextureSize,  # type: ignore[arg-type]
                                                 self._image_space,
                                                 get_or_create_tile_globjects=self.get_or_create_tile_globjects,
                                                 shared_cpu_entry=cpu_entry,
                                                 force_static_quads=self._use_static_tile_quads(),
                                                 extrapolate=self._rbf_extrapolate_enabled())
                    self._built_mesh_tiles.add(grid_coords)
                    if grid_coords in unused_grid_coords:
                        unused_grid_coords.remove(grid_coords)

            for grid_coord in unused_grid_coords:
                del self._tile_render_data[grid_coord]

        except gl.GLError as e:
            print(f"GL error updating tile buffers (will rebuild on next paint): {e}")
            if self._repaint_callback is not None:
                qt_post_to_main(self._repaint_callback)

    def draw_lines(self, draw_in_fixed_space: bool):
        """
        :param bool draw_in_fixed_space: True if lines should be drawn in fixed space.  Otherwise draw in warped space
        """
        if self.transform is None:
            return

        triangles = []
        if not draw_in_fixed_space:
            if not isinstance(self.transform, nornir_imageregistration.transforms.ITriangulatedSourceSpace):
                return

            # Triangles = self.__Transform.WarpedTriangles
            verts = mesh_overlay_verts_xy(self.transform.SourcePoints)  # type: ignore[attr-defined]
            triangles = self.transform.source_space_trianglulation
        else:
            if not isinstance(self.transform, nornir_imageregistration.transforms.ITriangulatedTargetSpace):
                return

            verts = mesh_overlay_verts_xy(self.transform.TargetPoints)  # type: ignore[attr-defined]
            triangles = self.transform.target_space_trianglulation

        if verts is not None and triangles is not None:
            pyre.views.DrawTriangles(verts, triangles)

    @classmethod
    def _create_tile_globjects(cls) -> TileGLObjects:
        """Create buffers and populate them with the vertex and index data.
        Assumes shaders are already initialized (caller should check)."""

        # Generate the buffers for the VAO
        vertex_buffer = GLBuffer(layout=shaders.texture_shader.vertex_layout,  # type: ignore[union-attr]
                                 usage=gl.GL_DYNAMIC_DRAW)

        index_buffer = GLIndexBuffer(usage=gl.GL_DYNAMIC_DRAW)

        vertex_array_object = DynamicVAO()
        vertex_array_object.begin_init()
        vertex_array_object.add_buffer(vertex_buffer)
        vertex_array_object.add_index_buffer(index_buffer)
        vertex_array_object.end_init()

        return TileGLObjects(vertex_buffer=vertex_buffer, index_buffer=index_buffer, vao=vertex_array_object)

    def get_or_create_tile_globjects(self, ix: int, iy: int) -> TileGLObjects | None:
        """Return the tile buffers for a grid coordinate, creating them if they do not exist.
        Returns None if shaders are not initialized yet."""
        if (ix, iy) not in self._tile_render_data:
            # Check if shaders are initialized before creating GL objects
            if not shaders.texture_shader.initialized:  # type: ignore[union-attr]
                # Shaders not ready yet, return None to skip this tile
                return None
            self._tile_render_data[(ix, iy)] = self._create_tile_globjects()

        return self._tile_render_data[(ix, iy)]

    def draw(self,
             view_proj: NDArray[np.floating],
             space: pyre.Space,
             client_size: tuple[int, int],
             bounding_box: nornir_imageregistration.Rectangle | None = None,
             default_fbo: int | None = None,
             overlay_viewport_size: tuple[int, int] | None = None,
             show_mesh_lines: bool = False,
             rigid_composite_source_align: bool = False,
             view_type: ViewType | None = None):
        """
        Draw the image in either source (fixed) or target (warped) space
        :param view_proj:
        :param space:
        :param client_size:
        :param bounding_box: Size of the client area in pixels. (height, width)
        :param default_fbo: Ignored for single-image views; used by composite view for overlay target.
        :return:
        """

        if self._image_viewmodel is None:
            warnings.warn("No image viewmodel to draw")

        self._draw_imageviewmodel(view_proj=view_proj,
                                  image_viewmodel=self._image_viewmodel,
                                  space=space,
                                  bounding_box=bounding_box,
                                  show_mesh_lines=show_mesh_lines,
                                  rigid_composite_source_align=rigid_composite_source_align,
                                  view_type=view_type)

    def _draw_imageviewmodel(self,
                             view_proj: NDArray[np.floating],
                             image_viewmodel: pyre.viewmodels.ImageViewModel | None,
                             space: pyre.Space,
                             bounding_box: nornir_imageregistration.Rectangle | None = None,
                             show_mesh_lines: bool = False,
                             rigid_composite_source_align: bool = False,
                             view_type: ViewType | None = None):

        if image_viewmodel is None:
            return

        # Ensure ImageArray is created (this will create textures if needed)
        # If textures can't be created yet (no context), ImageArray will be empty
        try:
            image_array = image_viewmodel.ImageArray
        except Exception as e:
            # If texture creation fails, skip drawing this frame
            if "No valid OpenGL context" in str(e):
                return
            raise

        # If ImageArray is empty, textures haven't been created yet - skip drawing
        if not image_array or len(image_array) == 0:
            return

        # Space is IntFlag; coerce so GLSL tween uniform always gets 0.0 or 1.0 (not enum object).
        tween = float(int(space))
        tc = self._transform_controller
        if tc is None:
            return

        draw_state = tc.resolve_draw_state(
            image_space=self._image_space,
            view_type=view_type,
            composite_source_align=rigid_composite_source_align,
            tween=tween,
        )
        use_rigid_path = draw_state.use_rigid_path
        rigid_forward = draw_state.source_to_target
        rigid_inverse = draw_state.target_to_source
        rigid_native_is_target = draw_state.rigid_native_is_target
        rigid_source_in_target_display = draw_state.rigid_source_in_target_display
        overlay = draw_state.rigid_overlay
        if overlay is not None:
            rigid_interactive_native_shift = overlay.interactive_native_shift
            rigid_source_display_matrix = overlay.source_display_matrix
            rigid_target_display_matrix = overlay.target_display_matrix
        else:
            rigid_interactive_native_shift = np.zeros(2, dtype=np.float32)
            rigid_source_display_matrix = np.eye(3, dtype=np.float32)
            rigid_target_display_matrix = np.eye(3, dtype=np.float32)

        cull_rect = bounding_box
        if view_type == ViewType.Composite:
            # Composite FBO layers must rasterize the full image tile grids. Corner-based
            # inverse AABB from display bounds underestimates warped coverage for mesh/grid STOS
            # (missing magenta source + window-width cropping of green target).
            cull_rect = None
        elif (
                rigid_composite_source_align
                and self._image_space == Space.Source
                and bounding_box is not None
                and use_rigid_path
        ):
            from pyre.views.composite_display import transform_visible_rectangle
            cull_rect = transform_visible_rectangle(bounding_box, rigid_inverse)

        visible = gltiles.tile_coords_for_visible_bounds(
            image_viewmodel.height, image_viewmodel.width,
            image_viewmodel.TextureSize,
            cull_rect)

        if not self._uses_lazy_mesh_build():
            tc = self._transform_controller
            skip_remesh = tc is not None and tc.interactive_edit_in_progress
            needs_build = not self._built_mesh_tiles
            if not needs_build and visible is not None:
                needs_build = any(not self._tile_mesh_is_ready(coord) for coord in visible)
            if needs_build and not skip_remesh:
                self.update_all_tile_buffers(visible_rect=cull_rect)

        if self._uses_lazy_mesh_build():
            if cull_rect is not None:
                prefetch_rect = gltiles.expand_visible_rectangle_by_tiles(
                    cull_rect,
                    tuple(int(v) for v in image_viewmodel.TextureSize),
                    margin_tiles=1)
                prefetch_coords = gltiles.tile_coords_for_visible_bounds(
                    image_viewmodel.height, image_viewmodel.width,
                    image_viewmodel.TextureSize,
                    prefetch_rect)
            else:
                prefetch_coords = None
            if prefetch_coords is None:
                # Full grid, budgeted across frames (composite / unreliable cull).
                prefetch_coords = set(image_viewmodel.generate_grid_indicies())
            self._ensure_visible_tile_meshes(prefetch_coords)

        # Contrast is per image space, not per tile — resolve once outside the draw loop.
        contrast = image_contrast.contrast_for_space(self._image_space)

        for ix in range(0, image_viewmodel.NumCols):
            column = image_array[ix]
            for iy in range(0, image_viewmodel.NumRows):
                if visible is not None and (ix, iy) not in visible:
                    continue
                texture = column[iy]

                # Skip if texture is invalid
                if texture == 0:
                    continue

                render_data = self.get_or_create_tile_globjects(ix, iy)

                # Skip if shaders aren't initialized yet (render_data will be None)
                if render_data is None:
                    continue

                if self._uses_lazy_mesh_build() and not render_data.mesh_populated:
                    continue

                try:
                    shaders.texture_shader.draw(view_proj, texture, render_data.vao, tween=tween,  # type: ignore[union-attr]
                                                use_rigid_path=use_rigid_path,
                                                rigid_source_to_target=rigid_forward,
                                                rigid_target_to_source=rigid_inverse,
                                                rigid_native_is_target=rigid_native_is_target,
                                                rigid_source_in_target_display=rigid_source_in_target_display,
                                                rigid_interactive_native_shift=rigid_interactive_native_shift,
                                                rigid_source_display_matrix=rigid_source_display_matrix,
                                                rigid_target_display_matrix=rigid_target_display_matrix,
                                                contrast_min=float(contrast.min),
                                                contrast_max=float(contrast.max),
                                                contrast_gamma=float(contrast.gamma))
                except ValueError as e:
                    if "Shaders have not been initialized" in str(e):
                        # Shaders not ready yet, skip this frame
                        return
                    raise
                except RuntimeError as e:
                    if "Invalid texture ID" in str(e) or "Failed to bind texture" in str(e):
                        print(f"Warning: Skipping invalid texture {texture} at ({ix}, {iy})")
                        continue
                    raise

        if show_mesh_lines:
            try:
                self.draw_lines(draw_in_fixed_space=(space == Space.Target))
            except Exception as e:
                warnings.warn(f"draw_lines skipped: {e}")
