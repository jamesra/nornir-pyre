"""Regression for #205: native-shift GLSL is gated on use_rigid_path."""
from __future__ import annotations

import importlib
import unittest

# Package __init__ binds texture_shader = TextureShader(), shadowing the submodule.
texture_shader_mod = importlib.import_module('pyre.gl_engine.shaders.texture_shader')


class TestTextureShaderNativeShiftGate(unittest.TestCase):
    def test_interactive_shift_requires_rigid_path(self) -> None:
        """#205: mesh/grid must not apply rigid_interactive_native_shift."""
        source = texture_shader_mod._texture_vertex_shader_program
        self.assertIn('use_rigid_path > 0.5', source)
        self.assertNotIn('length(rigid_interactive_native_shift) > 0.001', source)
        gate_idx = source.find('if (use_rigid_path > 0.5) {\n                vec3 shift')
        self.assertGreaterEqual(gate_idx, 0, msg='native shift must be gated on use_rigid_path')
        self.assertIn('rigid_interactive_native_shift', source[gate_idx:gate_idx + 400])


if __name__ == '__main__':
    unittest.main()
