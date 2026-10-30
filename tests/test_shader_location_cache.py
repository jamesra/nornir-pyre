"""Lazy-cached attrib/uniform location properties of the GL shaders.

Pins, without a GL context, what each location property queries (GL function and
name), what it caches, the exact ValueError message on -1, and the quirk that a -1
result is cached so a second access returns -1 instead of raising again.
"""
from __future__ import annotations

import importlib
import unittest
from typing import Any, NamedTuple
from unittest import mock

from hypothesis import given, settings
from hypothesis import strategies as st
from OpenGL import GL as gl

# Package __init__ binds module-level shader instances that shadow the submodules.
_mods = {name: importlib.import_module(f'pyre.gl_engine.shaders.{name}')
         for name in ('color_shader', 'controlpointset_shader', 'overlay_shader',
                      'pointset_shader', 'transform_shader')}

ColorShader = _mods['color_shader'].ColorShader
ControlPointSetShader = _mods['controlpointset_shader'].ControlPointSetShader
OverlayShader = _mods['overlay_shader'].OverlayShader
PointSetShader = _mods['pointset_shader'].PointSetShader
TransformShader = _mods['transform_shader'].TransformShader

FAKE_PROGRAM = 4242
ATTRIB = 'glGetAttribLocation'
UNIFORM = 'glGetUniformLocation'
MSG_ATTR = 'Could not find attribute'
MSG_TEXCOORD = 'Could not find texture coordinate attribute'
MSG_SAMPLER = 'Could not find texture_sampler attribute'


class Case(NamedTuple):
    """One location property: where it caches and what it asks GL for."""
    shader_cls: type
    prop: str
    cache_attr: str
    gl_func: str
    gl_name: str
    message: str


def _cases() -> list[Case]:
    """Table of every location property routed through the shared helper."""
    rows: list[tuple[type, str, str, str, str, str]] = [
        (ControlPointSetShader, 'texture_index_location', '_texture_index_location', ATTRIB, 'texture_index', MSG_ATTR),
        (ControlPointSetShader, 'vertex_location', '_vertex_location', ATTRIB, 'vertex_position', MSG_ATTR),
        (ControlPointSetShader, 'texture_coord_location', '_vertex_texture_location', ATTRIB,
         'vertex_texture_coordinate', MSG_TEXCOORD),
        (ControlPointSetShader, 'point_source_offset_location', '_point_source_offset_location', ATTRIB,
         'point_source_offset', MSG_ATTR),
        (ControlPointSetShader, 'point_target_offset_location', '_point_target_offset_location', ATTRIB,
         'point_target_offset', MSG_ATTR),
        (ControlPointSetShader, 'texture_sampler', '_texture_sampler_location', UNIFORM, 'texture_sampler',
         MSG_SAMPLER),
        (ControlPointSetShader, 'tween_location', '_tween_location', UNIFORM, 'tween', MSG_ATTR),
        (ControlPointSetShader, 'scale_location', '_scale_location', UNIFORM, 'scale', MSG_ATTR),
        (ControlPointSetShader, 'model_view_projection_matrix_location', '_view_projection_matrix_location',
         UNIFORM, 'view_projection_matrix', MSG_ATTR),
        (ControlPointSetShader, 'busy_angle_location', '_busy_angle_location', UNIFORM, 'busy_angle',
         'Could not find busy_angle uniform'),

        (PointSetShader, 'vertex_location', '_vertex_location', ATTRIB, 'vertex_position', MSG_ATTR),
        (PointSetShader, 'texture_coord_location', '_vertex_texture_location', ATTRIB,
         'vertex_texture_coordinate', MSG_TEXCOORD),
        (PointSetShader, 'point_source_offset_location', '_point_source_offset_location', ATTRIB,
         'point_source_offset', MSG_ATTR),
        (PointSetShader, 'point_target_offset_location', '_point_target_offset_location', ATTRIB,
         'point_target_offset', MSG_ATTR),
        (PointSetShader, 'texture_sampler', '_texture_sampler_location', UNIFORM, 'texture_sampler', MSG_SAMPLER),
        (PointSetShader, 'tween_location', '_tween_location', UNIFORM, 'tween', MSG_ATTR),
        (PointSetShader, 'model_view_projection_matrix_location', '_view_projection_matrix_location', UNIFORM,
         'view_projection_matrix', MSG_ATTR),

        (TransformShader, 'source_pos_location', '_source_pos_location', ATTRIB, 'vertex_source_position', MSG_ATTR),
        (TransformShader, 'target_pos_location', '_target_pos_location', ATTRIB, 'vertex_target_position', MSG_ATTR),
        (TransformShader, 'texture_coord_location', '_texture_coord_location', ATTRIB, 'vertex_texture_coordinate',
         MSG_TEXCOORD),
        (TransformShader, 'source_texture_location', '_source_texture_location', UNIFORM, 'source_texture',
         MSG_SAMPLER),
        (TransformShader, 'target_texture_location', '_target_texture_location', UNIFORM, 'target_texture',
         MSG_SAMPLER),
        (TransformShader, 'vertex_tween_location', '_vertex_tween_location', UNIFORM, 'vert_tween', MSG_ATTR),
        (TransformShader, 'texture_tween_location', '_texture_tween_location', UNIFORM, 'texture_tween', MSG_ATTR),
        (TransformShader, 'model_view_projection_matrix_location', '_model_view_projection_matrix_location',
         UNIFORM, 'model_view_projection_matrix', MSG_ATTR),

        (OverlayShader, 'vertex_position_location', '_vertex_position_location', ATTRIB, 'vertex_position', MSG_ATTR),
        (OverlayShader, 'texture_coord_location', '_texture_coord_location', ATTRIB, 'vertex_texture_coordinate',
         MSG_TEXCOORD),
        (OverlayShader, 'source_texture_location', '_source_texture_location', UNIFORM, 'source_texture',
         MSG_SAMPLER),
        (OverlayShader, 'target_texture_location', '_target_texture_location', UNIFORM, 'target_texture',
         MSG_SAMPLER),
        (OverlayShader, 'model_view_projection_matrix_location', '_model_view_projection_matrix_location',
         UNIFORM, 'model_view_projection_matrix', MSG_ATTR),
        (OverlayShader, 'source_channel_blend_location', '_source_channel_blend_location', UNIFORM,
         'source_channel_blend', MSG_ATTR),
        (OverlayShader, 'target_channel_blend_location', '_target_channel_blend_location', UNIFORM,
         'target_channel_blend', MSG_ATTR),

        (ColorShader, 'source_pos_location', '_source_pos_location', ATTRIB, 'vertex_source_position', MSG_ATTR),
        (ColorShader, 'target_pos_location', '_target_pos_location', ATTRIB, 'vertex_target_position', MSG_ATTR),
        (ColorShader, 'tween_location', '_tween_location', UNIFORM, 'tween', MSG_ATTR),
        (ColorShader, 'color_location', '_color_location', UNIFORM, 'color', MSG_ATTR),
        (ColorShader, 'model_view_projection_matrix', '_model_view_projection_matrix_location', UNIFORM,
         'model_view_projection_matrix', MSG_ATTR),
    ]
    return [Case(*row) for row in rows]


CASES = _cases()


class _FakeGL:
    """Records glGet*Location calls and answers with a fixed location."""

    calls: list[tuple[str, Any, str]]
    location: int

    def __init__(self, location: int) -> None:
        self.calls = []
        self.location = location

    def attrib(self, program: Any, name: str) -> int:
        """Stand-in for glGetAttribLocation."""
        self.calls.append((ATTRIB, program, name))
        return self.location

    def uniform(self, program: Any, name: str) -> int:
        """Stand-in for glGetUniformLocation."""
        self.calls.append((UNIFORM, program, name))
        return self.location


def _access(case: Case, location: int) -> tuple[list[Any], list[tuple[str, Any, str]], Any]:
    """Read the property twice on a fresh shader; return outcomes, GL calls and the cached value.

    Each outcome is the returned location or ``('raise', message)``.
    """
    fake = _FakeGL(location)
    outcomes: list[Any] = []
    with mock.patch.object(case.shader_cls, 'program', property(lambda self: FAKE_PROGRAM)), \
            mock.patch.object(gl, ATTRIB, fake.attrib), \
            mock.patch.object(gl, UNIFORM, fake.uniform):
        shader = case.shader_cls()
        for _ in range(2):
            try:
                outcomes.append(getattr(shader, case.prop))
            except ValueError as e:
                outcomes.append(('raise', str(e)))
        cached = shader.__dict__.get(case.cache_attr, 'missing')
    return outcomes, fake.calls, cached


def _expected(case: Case, location: int) -> tuple[list[Any], list[tuple[str, Any, str]], Any]:
    """Old behavior: query once, cache the result (even -1), raise only on the first -1."""
    first: Any = ('raise', case.message) if location == -1 else location
    return [first, location], [(case.gl_func, FAKE_PROGRAM, case.gl_name)], location


class TestShaderLocationCache(unittest.TestCase):
    """Every routed location property keeps its query, cache and error behavior."""

    def test_table_covers_every_shader_class(self) -> None:
        """The table names five shader classes and 37 properties."""
        self.assertEqual(len({c.shader_cls for c in CASES}), 5)
        self.assertEqual(len(CASES), 37)

    def test_found_location_is_queried_once_and_cached(self) -> None:
        """A found location is asked for once with the right GL call and name, then cached."""
        for case in CASES:
            with self.subTest(cls=case.shader_cls.__name__, prop=case.prop):
                self.assertEqual(_access(case, 3), _expected(case, 3))

    def test_missing_location_raises_exact_message_then_returns_cached_minus_one(self) -> None:
        """-1 raises ValueError with the property's message once; the cached -1 is returned after."""
        for case in CASES:
            with self.subTest(cls=case.shader_cls.__name__, prop=case.prop):
                self.assertEqual(_access(case, -1), _expected(case, -1))

    def test_zero_location_is_valid(self) -> None:
        """Location 0 is a real location, not a missing one."""
        for case in CASES:
            with self.subTest(cls=case.shader_cls.__name__, prop=case.prop):
                self.assertEqual(_access(case, 0), _expected(case, 0))

    @settings(max_examples=200, deadline=None)
    @given(case=st.sampled_from(CASES), location=st.integers(min_value=-1, max_value=2 ** 31 - 1))
    def test_property_matches_reference(self, case: Case, location: int) -> None:
        """Any location GL can return gives the reference outcome for any routed property."""
        self.assertEqual(_access(case, location), _expected(case, location))


if __name__ == '__main__':
    unittest.main()
