"""gl_engine diagnostics go through logging, not print (#253)."""
from __future__ import annotations

import ast
import pathlib
import unittest

_GL_ENGINE = pathlib.Path(__file__).resolve().parents[1] / 'pyre' / 'gl_engine'


class TestGlEngineUsesLogging(unittest.TestCase):
    def test_modules_define_loggers(self) -> None:
        for relative in (
            'helpers.py',
            'context_aware_vao.py',
            'textures_gl.py',
            'shader_vao.py',
            'instanced_vao.py',
        ):
            with self.subTest(file=relative):
                source = (_GL_ENGINE / relative).read_text(encoding='utf-8')
                self.assertIn('logging.getLogger(__name__)', source)

    def test_no_active_print_calls_in_gl_engine_python(self) -> None:
        """AST walk so commented-out print examples do not count."""
        offenders: list[str] = []
        for path in _GL_ENGINE.rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Name) and func.id == 'print':
                    offenders.append(f'{path.relative_to(_GL_ENGINE)}:{node.lineno}')
        self.assertEqual([], offenders, f'active print() remain: {offenders}')


if __name__ == '__main__':
    unittest.main()
