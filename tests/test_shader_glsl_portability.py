"""GLSL portability checks that run without a GL context.

NVIDIA drivers accept GLSL that the specification forbids; Qualcomm (Windows ARM64), Mesa and
macOS drivers reject it, and a shader that fails to compile there stops Pyre from starting.
"""
from __future__ import annotations

import importlib
import pathlib
import re
import unittest

_SHADER_DIR = pathlib.Path(importlib.import_module('pyre.gl_engine.shaders').__file__).parent

# GLSL reserves the gl_ prefix; a declaration such as "out float gl_FragDepth;" is a compile
# error on strict drivers ("gl_FragDepth redeclared").
_GL_DECLARATION = re.compile(r'\b(?:in|out|inout|uniform|varying|attribute)\s+\w+\s+gl_\w+')


def _glsl_sources() -> dict[str, str]:
    sources = {}
    for path in sorted(_SHADER_DIR.glob('*_shader.py')):
        module = importlib.import_module(f'pyre.gl_engine.shaders.{path.stem}')
        for name, value in vars(module).items():
            if isinstance(value, str) and value.lstrip().startswith('#version'):
                sources[f'{path.stem}.{name}'] = value
    return sources


class TestShaderGLSLPortability(unittest.TestCase):

    def test_shader_sources_found(self):
        self.assertIn('color_shader._color_fragment_shader_program', _glsl_sources())

    def test_no_reserved_gl_identifier_declarations(self):
        for name, source in _glsl_sources().items():
            with self.subTest(shader=name):
                self.assertIsNone(_GL_DECLARATION.search(source),
                                  f'{name} declares a reserved gl_ identifier')


if __name__ == '__main__':
    unittest.main()
