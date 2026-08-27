"""Composite overlay for the phase-correlation cell around busy control points."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from numpy.typing import NDArray

from pyre.gl_engine.shader_vao import ShaderVAO
from pyre.interfaces.viewtype import ViewType

REGISTRATION_ROI_FADE_SECONDS = 5.0
# Match the busy-glyph comet so the cell box reads as the same feedback.
REGISTRATION_ROI_RGB = (0.35, 0.65, 1.0)
REGISTRATION_ROI_FILL_ALPHA = 0.28
REGISTRATION_ROI_EDGE_ALPHA = 0.9


@dataclass(frozen=True)
class RegistrationRoiOverlay:
    """One axis-aligned phase-correlation cell to draw in composite display space."""

    center_yx: tuple[float, float]
    size_yx: tuple[float, float]
    alpha: float


class RegistrationRoiFadeTracker:
    """Record when each busy session ID first appeared so its box can fade out."""

    _started_at: dict[int, float]

    def __init__(self) -> None:
        self._started_at = {}

    @property
    def started_at(self) -> Mapping[int, float]:
        """Monotonic start times keyed by session ID."""
        return self._started_at

    def sync(self, busy_ids: frozenset[int], now: float) -> None:
        """Keep start times for current busy IDs; assign ``now`` to newly busy IDs."""
        for point_id in [pid for pid in self._started_at if pid not in busy_ids]:
            del self._started_at[point_id]
        for point_id in busy_ids:
            self._started_at.setdefault(int(point_id), now)


def registration_roi_fade_alpha(
        elapsed_seconds: float,
        duration_seconds: float = REGISTRATION_ROI_FADE_SECONDS) -> float:
    """Linear fade from 1 at t=0 to 0 at ``duration_seconds``."""
    if duration_seconds <= 0.0:
        return 0.0
    if elapsed_seconds <= 0.0:
        return 1.0
    if elapsed_seconds >= duration_seconds:
        return 0.0
    return 1.0 - (elapsed_seconds / duration_seconds)


def alignment_area_yx(alignment_area: object | None,
                      fallback: object | None = None) -> tuple[float, float]:
    """Return (height, width) for the phase-correlation crop, in image pixels."""
    source: object | None = alignment_area
    if source is None:
        source = fallback
    if source is None:
        return (0.0, 0.0)
    area = np.asarray(source, dtype=np.float64).ravel()
    if area.size < 2:
        side = float(area[0]) if area.size == 1 else 0.0
        return (side, side)
    return (float(area[0]), float(area[1]))


def phase_correlation_roi_bounds_yx(
        center_yx: NDArray[np.floating] | Sequence[float],
        alignment_area_yx_shape: NDArray[np.floating] | Sequence[float]) -> NDArray[np.floating]:
    """Axis-aligned (min_y, min_x, max_y, max_x) centered on a control point.

    Matches ``BuildAlignmentROIs`` before integer snap: a rectangle of
    ``alignmentArea`` (height, width) centered on the target-space point.
    """
    center = np.asarray(center_yx, dtype=np.float64).ravel()[:2]
    height, width = alignment_area_yx(alignment_area_yx_shape)
    half_y = height / 2.0
    half_x = width / 2.0
    return np.array(
        (float(center[0]) - half_y,
         float(center[1]) - half_x,
         float(center[0]) + half_y,
         float(center[1]) + half_x),
        dtype=np.float64)


def gl_scale_translate_xy(center_xy: tuple[float, float],
                          size_xy: tuple[float, float]) -> NDArray[np.floating]:
    """4x4 scale-then-translate with translation in the last row (Pyre camera convention)."""
    sx, sy = float(size_xy[0]), float(size_xy[1])
    tx, ty = float(center_xy[0]), float(center_xy[1])
    return np.array(
        ((sx, 0.0, 0.0, 0.0),
         (0.0, sy, 0.0, 0.0),
         (0.0, 0.0, 1.0, 0.0),
         (tx, ty, 0.0, 1.0)),
        dtype=np.float64)


def model_matrix_for_roi_overlay(overlay: RegistrationRoiOverlay) -> NDArray[np.floating]:
    """Map a unit quad centered at the origin onto ``overlay`` in GL XY world space."""
    cy, cx = overlay.center_yx
    height, width = overlay.size_yx
    return gl_scale_translate_xy((cx, cy), (width, height))


def combined_mvp_for_roi(view_proj: NDArray[np.floating],
                         overlay: RegistrationRoiOverlay) -> NDArray[np.floating]:
    """Compose overlay model with the camera view-projection (translation-last-row numpy)."""
    model = model_matrix_for_roi_overlay(overlay)
    return model @ np.asarray(view_proj, dtype=np.float64)


def should_draw_registration_roi(view_type: ViewType) -> bool:
    """Phase-correlation cells are shown only on the composite view."""
    return view_type == ViewType.Composite


def phase_correlation_roi_overlays(
        *,
        busy_ids: frozenset[int],
        started_at: Mapping[int, float],
        index_for_id: Callable[[int], int | None],
        target_points_yx: NDArray[np.floating],
        alignment_area_yx_shape: object | None,
        now: float,
        fade_seconds: float = REGISTRATION_ROI_FADE_SECONDS) -> list[RegistrationRoiOverlay]:
    """Build fading cell overlays for busy control points in target display space."""
    height, width = alignment_area_yx(alignment_area_yx_shape)
    if height <= 0.0 or width <= 0.0:
        return []
    points = np.asarray(target_points_yx, dtype=np.float64)
    if points.ndim != 2 or points.shape[0] == 0 or points.shape[1] < 2:
        return []
    overlays: list[RegistrationRoiOverlay] = []
    n_points = int(points.shape[0])
    for point_id in busy_ids:
        started = started_at.get(int(point_id))
        if started is None:
            continue
        alpha = registration_roi_fade_alpha(now - started, fade_seconds)
        if alpha <= 0.0:
            continue
        index = index_for_id(int(point_id))
        if index is None or index < 0 or index >= n_points:
            continue
        y = float(points[index, 0])
        x = float(points[index, 1])
        overlays.append(RegistrationRoiOverlay(
            center_yx=(y, x),
            size_yx=(height, width),
            alpha=alpha,
        ))
    return overlays


_fill_vao: ShaderVAO | None = None
_edge_vao: ShaderVAO | None = None


def _unit_quad_vertices() -> NDArray[np.floating]:
    """ColorShader layout: source xyz + target xyz for a unit square centered at the origin."""
    corners = (
        (-0.5, -0.5, 0.0),
        (0.5, -0.5, 0.0),
        (0.5, 0.5, 0.0),
        (-0.5, 0.5, 0.0),
    )
    rows = [[x, y, z, x, y, z] for x, y, z in corners]
    return np.asarray(rows, dtype=np.float32)


def _ensure_unit_quad_vaos() -> tuple[ShaderVAO, ShaderVAO]:
    """Create (once) fill and outline VAOs for the current ColorShader layout."""
    global _fill_vao, _edge_vao
    if _fill_vao is not None and _edge_vao is not None:
        return _fill_vao, _edge_vao

    from pyre.gl_engine.shaders import color_shader

    if color_shader is None:
        raise RuntimeError("ColorShader is not available")
    verts = _unit_quad_vertices()
    fill_indices = np.array((0, 1, 2, 2, 3, 0), dtype=np.uint16)
    edge_indices = np.array((0, 1, 2, 3), dtype=np.uint16)
    layout = color_shader.vertex_layout
    _fill_vao = ShaderVAO(layout, verts, fill_indices)
    _edge_vao = ShaderVAO(layout, verts, edge_indices)
    return _fill_vao, _edge_vao


def draw_registration_roi_overlays(
        view_proj: NDArray[np.floating],
        overlays: Sequence[RegistrationRoiOverlay]) -> None:
    """Draw fading blue cell rectangles in composite world space."""
    if not overlays:
        return

    from OpenGL import GL as gl
    from pyre.gl_engine.shaders import color_shader

    if color_shader is None or not color_shader.initialized:
        return

    fill_vao, edge_vao = _ensure_unit_quad_vaos()
    rgb = REGISTRATION_ROI_RGB
    gl.glDisable(gl.GL_DEPTH_TEST)
    gl.glDepthMask(gl.GL_FALSE)
    gl.glEnable(gl.GL_BLEND)
    gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
    try:
        for overlay in overlays:
            mvp = combined_mvp_for_roi(view_proj, overlay)
            fill = (rgb[0], rgb[1], rgb[2], REGISTRATION_ROI_FILL_ALPHA * overlay.alpha)
            edge = (rgb[0], rgb[1], rgb[2], REGISTRATION_ROI_EDGE_ALPHA * overlay.alpha)
            color_shader.draw(mvp, fill_vao, tween=1.0, color=fill, mode=gl.GL_TRIANGLES)
            color_shader.draw(mvp, edge_vao, tween=1.0, color=edge, mode=gl.GL_LINE_LOOP)
    finally:
        gl.glDepthMask(gl.GL_TRUE)
        gl.glEnable(gl.GL_DEPTH_TEST)
