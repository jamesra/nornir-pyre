"""Regression: tile VAO must not double-delete the index buffer owned by GLIndexBuffer."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from pyre.gl_engine.dynamic_vao import DynamicVAO


class TestDynamicVaoIndexOwnership(unittest.TestCase):
    def test_dynamic_vao_does_not_own_index_buffer(self) -> None:
        vao = DynamicVAO()
        self.assertFalse(vao._owns_index_buffer)

    def test_cleanup_skips_index_buffer_delete(self) -> None:
        vao = DynamicVAO()
        vao._index_buffer_id = 42
        vao._initialized = True
        fake_ctx = MagicMock()
        fake_ctx.isValid.return_value = True

        with patch("pyre.gl_engine.context_aware_vao.QOpenGLContext") as mock_qctx, \
                patch("pyre.gl_engine.context_aware_vao.gl") as mock_gl:
            mock_qctx.currentContext.return_value = fake_ctx
            vao._context_vaos = {fake_ctx: 7}
            vao.cleanup()

        mock_gl.glDeleteBuffers.assert_not_called()
        self.assertEqual(vao._index_buffer_id, 42)
        mock_gl.glDeleteVertexArrays.assert_called()


if __name__ == "__main__":
    unittest.main()
