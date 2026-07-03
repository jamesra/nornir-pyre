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
from pyre.perf_debug import timed


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
    _image_space: Space  # The space the image is in
    _activate_context: Callable[
        [], None]  # A function we can call to ensure the view's GL context is current, must be used before creating GL Objects

    _gl_funcs: QOpenGLFunctions

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
                 ):
        """
        Constructor
        :param imageviewmodel image_view_model: Textures for image
        :param transform transform_controller: nornir_imageregistration transform
        """
        self._gl_funcs = gl_funcs
        self._activate_context = activate_context
        self._tile_render_data = {}
        self._image_space = space
        self._rendercache = RenderCache()
        self._image_viewmodel = image_view_model  # type: ignore[assignment]
        self._image_mask_viewmodel = image_mask_view_model
        self._transform_controller = transform_controller  # type: ignore[assignment]
        self._z = 0.5

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

        self.update_all_tile_buffers()

    def OnTransformChanged(self, transform_controller: TransformController | None = None):
        """Full tile mesh rebuild after transform changes (skipped during interactive drag)."""
        if not self._gl_initialized:
            return
        tc = transform_controller if transform_controller is not None else self._transform_controller
        if tc is not None and tc.interactive_edit_in_progress:
            return
        if self.transform is not None and gltiles.is_rigid_transform(self.transform):
            needs_rigid_init = not self._tile_render_data
            if not needs_rigid_init:
                for tile_data in self._tile_render_data.values():
                    if not tile_data.is_rigid_quad:
                        needs_rigid_init = True
                        break
            if needs_rigid_init:
                self.update_all_tile_buffers()
            return
        self.update_all_tile_buffers()

    def OnPointMoved(self, transform_controller: TransformController, indices: NDArray[np.integer]):
        """Incremental tile patch update for control point drag."""
        if not self._gl_initialized:
            return
        if self.transform is not None and gltiles.is_rigid_transform(self.transform):
            return
        self.update_tiles_for_point_indices(indices)

    def _view_model_cache_id(self) -> int:
        return id(self._image_viewmodel)

    def _get_or_build_cpu_entry(self, grid_coords: tuple[int, int]) -> 'pyre.controllers.tile_mesh_cache.TileMeshCpuEntry':
        from pyre.controllers.tile_mesh_cache import TileMeshCpuEntry

        assert self._transform_controller is not None
        assert self._image_viewmodel is not None
        cache = self._transform_controller.tile_mesh_cache
        vm_id = self._view_model_cache_id()
        entry = cache.get(vm_id, self._image_space, grid_coords)
        if entry is not None:
            return entry
        render_data = self.get_or_create_tile_globjects(grid_coords[0], grid_coords[1])
        entry = gltiles.build_tile_mesh_cpu(
            self.transform,
            grid_coords,
            self._image_viewmodel.TextureSize,  # type: ignore[arg-type]
            self._image_space,
            cached_entry=render_data)
        cache.put(vm_id, self._image_space, grid_coords, entry)
        return entry

    def update_tiles_for_point_indices(self, indices: NDArray[np.integer],
                                       visible_rect: nornir_imageregistration.Rectangle | None = None):
        """Update only tiles affected by moved control points."""
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

        with timed(f'update_tiles_for_points n={len(tile_coords)}'):
            for grid_coords in tile_coords:
                cpu_entry = self._get_or_build_cpu_entry(grid_coords)
                gltiles._update_tile_buffers(
                    self.transform,
                    grid_coords,
                    self._image_viewmodel.TextureSize,  # type: ignore[arg-type]
                    self._image_space,
                    get_or_create_tile_globjects=self.get_or_create_tile_globjects,
                    shared_cpu_entry=cpu_entry)

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
                                                 shared_cpu_entry=cpu_entry)
                    if grid_coords in unused_grid_coords:
                        unused_grid_coords.remove(grid_coords)

            for grid_coord in unused_grid_coords:
                del self._tile_render_data[grid_coord]

        except gl.GLError as e:
            # If we still get GL errors, it means the context isn't ready yet
            print(f"GL not ready yet, will retry: {e}")
            # Schedule a retry with context activation
            qt_post_to_main(self.update_all_tile_buffers, activate_context=self._activate_context)

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
            verts = np.fliplr(self.transform.SourcePoints)  # type: ignore[attr-defined]
            triangles = self.transform.source_space_trianglulation
        else:
            if not isinstance(self.transform, nornir_imageregistration.transforms.ITriangulatedTargetSpace):
                return

            verts = np.fliplr(self.transform.TargetPoints)  # type: ignore[attr-defined]
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
             rigid_composite_fixed_align: bool = False,
             force_live_rigid_matrix: bool = False):
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
                                  rigid_composite_fixed_align=rigid_composite_fixed_align,
                                  force_live_rigid_matrix=force_live_rigid_matrix)

    def _draw_imageviewmodel(self,
                             view_proj: NDArray[np.floating],
                             image_viewmodel: pyre.viewmodels.ImageViewModel | None,
                             space: pyre.Space,
                             bounding_box: nornir_imageregistration.Rectangle | None = None,
                             show_mesh_lines: bool = False,
                             rigid_composite_fixed_align: bool = False,
                             force_live_rigid_matrix: bool = False):

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
        use_rigid = self.transform is not None and gltiles.is_rigid_transform(self.transform)
        rigid_forward = None
        rigid_inverse = None
        use_rigid_path = False
        rigid_native_is_warped = self._image_space == Space.Target
        if use_rigid:
            rigid_forward, rigid_inverse = shaders.texture_shader.rigid_matrices_from_transform(self.transform)  # type: ignore[union-attr]
            use_rigid_path = True
            tc = self._transform_controller
            if (not force_live_rigid_matrix
                    and tc is not None and tc.interactive_edit_in_progress and tc.interactive_edit_space is not None
                    and self._image_space != tc.interactive_edit_space
                    and tc.rigid_matrix_at_edit_start is not None
                    and tc.rigid_inverse_matrix_at_edit_start is not None):
                rigid_forward = tc.rigid_matrix_at_edit_start
                rigid_inverse = tc.rigid_inverse_matrix_at_edit_start

        visible = gltiles.tile_coords_for_visible_bounds(
            image_viewmodel.height, image_viewmodel.width,
            image_viewmodel.TextureSize,
            bounding_box)

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

                try:
                    shaders.texture_shader.draw(view_proj, texture, render_data.vao, tween=tween,  # type: ignore[union-attr]
                                                use_rigid_path=use_rigid_path,
                                                rigid_source_to_target=rigid_forward,
                                                rigid_target_to_source=rigid_inverse,
                                                rigid_native_is_warped=rigid_native_is_warped,
                                                rigid_fixed_warped_into_target=rigid_composite_fixed_align)
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
