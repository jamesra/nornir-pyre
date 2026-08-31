"""Tests that GL objects freed from __del__ neither raise nor vanish without a record.

__del__ runs at an arbitrary point, often during widget or interpreter teardown when no GL
context is current. A glDelete* issued then cannot reach the driver: it either raises, which
Python reports as "Exception ignored in __del__", or it was wrapped in `except Exception:
pass` and the leak became invisible. Both shapes were present across gl_buffer,
framebuffer and shader_base.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from pyre.gl_engine import gl_buffer as gl_buffer_module
from pyre.gl_engine import framebuffer as framebuffer_module
from pyre.gl_engine import helpers as helpers_module
from pyre.gl_engine.gl_buffer import GLBuffer, GLIndexBuffer
from pyre.gl_engine.helpers import delete_gl_object_on_teardown
from pyre.gl_engine.shaders import shader_base as shader_base_module
from pyre.gl_engine.shaders.shader_base import FragmentShader, VertexShader


class _CapturedTeardown:
    """Runs a callable with a chosen context state, capturing stdout."""

    def __init__(self, context_current: bool) -> None:
        self._current = object() if context_current else None
        self.output = ''

    def run(self, fn) -> None:
        buffer = io.StringIO()
        with patch.object(helpers_module.QOpenGLContext, 'currentContext',
                          staticmethod(lambda: self._current)):
            with redirect_stdout(buffer):
                fn()
        self.output = buffer.getvalue()


class TestTheTeardownHelper(unittest.TestCase):

    def test_a_delete_is_issued_when_a_context_is_current(self) -> None:
        calls = []
        harness = _CapturedTeardown(context_current=True)
        result = []
        harness.run(lambda: result.append(
            delete_gl_object_on_teardown(lambda: calls.append('deleted'), 'thing 7')))
        self.assertEqual(['deleted'], calls)
        self.assertTrue(result[0])

    def test_no_delete_is_attempted_without_a_context(self) -> None:
        calls = []
        harness = _CapturedTeardown(context_current=False)
        result = []
        harness.run(lambda: result.append(
            delete_gl_object_on_teardown(lambda: calls.append('deleted'), 'thing 7')))
        self.assertEqual([], calls, 'a delete with no context cannot reach the driver')
        self.assertFalse(result[0])

    def test_the_skipped_delete_is_reported(self) -> None:
        """The leak must leave a trace; the old code swallowed it entirely."""
        harness = _CapturedTeardown(context_current=False)
        harness.run(lambda: delete_gl_object_on_teardown(lambda: None, 'thing 7'))
        self.assertIn('thing 7', harness.output)
        self.assertIn('no current OpenGL context', harness.output)

    def test_a_raising_delete_is_contained_and_reported(self) -> None:
        def boom() -> None:
            raise RuntimeError('driver said no')

        harness = _CapturedTeardown(context_current=True)
        result = []
        harness.run(lambda: result.append(delete_gl_object_on_teardown(boom, 'thing 7')))
        self.assertFalse(result[0])
        self.assertIn('thing 7', harness.output)
        self.assertIn('driver said no', harness.output)


class _FakeGL:
    def __init__(self, raise_on_delete: bool = False) -> None:
        self.deleted: list[int] = []
        self._raise = raise_on_delete

    def _record(self, name: int) -> None:
        if self._raise:
            raise RuntimeError('no context')
        self.deleted.append(name)

    def glDeleteBuffers(self, count: int, names) -> None:
        self._record(int(names[0]))

    def glDeleteShader(self, shader: int) -> None:
        self._record(int(shader))

    def glDeleteProgram(self, program: int) -> None:
        self._record(int(program))


class _TeardownCase(unittest.TestCase):
    """Shared driver: build an object holding a GL name, then trigger __del__."""

    module = helpers_module

    def _run_del(self, obj, fake_gl, module, context_current: bool) -> str:
        buffer = io.StringIO()
        current = object() if context_current else None
        with patch.object(module, 'gl', fake_gl), \
                patch.object(helpers_module.QOpenGLContext, 'currentContext',
                             staticmethod(lambda: current)):
            with redirect_stdout(buffer):
                type(obj).__del__(obj)
        return buffer.getvalue()


class TestBufferTeardown(_TeardownCase):

    def _buffer(self, cls):
        obj = cls.__new__(cls)
        obj._buffer = 41
        return obj

    def test_a_vertex_buffer_is_deleted_when_a_context_is_current(self) -> None:
        fake, obj = _FakeGL(), self._buffer(GLBuffer)
        self._run_del(obj, fake, gl_buffer_module, context_current=True)
        self.assertEqual([41], fake.deleted)

    def test_an_index_buffer_is_deleted_when_a_context_is_current(self) -> None:
        fake, obj = _FakeGL(), self._buffer(GLIndexBuffer)
        self._run_del(obj, fake, gl_buffer_module, context_current=True)
        self.assertEqual([41], fake.deleted)

    def test_a_buffer_leak_is_reported_without_a_context(self) -> None:
        for cls, label in ((GLBuffer, 'vertex buffer'), (GLIndexBuffer, 'index buffer')):
            with self.subTest(cls=cls.__name__):
                fake, obj = _FakeGL(), self._buffer(cls)
                out = self._run_del(obj, fake, gl_buffer_module, context_current=False)
                self.assertEqual([], fake.deleted)
                self.assertIn(label, out)
                self.assertIn('41', out)

    def test_a_failing_buffer_delete_does_not_raise(self) -> None:
        fake, obj = _FakeGL(raise_on_delete=True), self._buffer(GLBuffer)
        out = self._run_del(obj, fake, gl_buffer_module, context_current=True)
        self.assertIn('41', out)


class TestShaderTeardown(_TeardownCase):

    def test_shaders_are_deleted_when_a_context_is_current(self) -> None:
        for cls, label in ((VertexShader, 'vertex shader'),
                           (FragmentShader, 'fragment shader')):
            with self.subTest(cls=cls.__name__):
                obj = cls.__new__(cls)
                obj._shader = 55
                fake = _FakeGL()
                self._run_del(obj, fake, shader_base_module, context_current=True)
                self.assertEqual([55], fake.deleted)

    def test_a_shader_leak_is_reported_without_a_context(self) -> None:
        obj = VertexShader.__new__(VertexShader)
        obj._shader = 55
        fake = _FakeGL()
        out = self._run_del(obj, fake, shader_base_module, context_current=False)
        self.assertEqual([], fake.deleted)
        self.assertIn('vertex shader 55', out)

    def test_a_shader_delete_no_longer_escapes_as_an_ignored_exception(self) -> None:
        """These three sites had no try at all, so __del__ could raise."""
        obj = VertexShader.__new__(VertexShader)
        obj._shader = 55
        fake = _FakeGL(raise_on_delete=True)
        out = self._run_del(obj, fake, shader_base_module, context_current=True)
        self.assertIn('vertex shader 55', out)


class TestFramebufferTeardown(unittest.TestCase):

    def test_nothing_is_attempted_when_already_freed(self) -> None:
        obj = framebuffer_module.FrameBuffer.__new__(framebuffer_module.FrameBuffer)
        obj._fbo = None
        obj._fbo_texture = None
        freed = []
        obj.free_fbo = lambda: freed.append('called')  # type: ignore[method-assign]
        with patch.object(helpers_module.QOpenGLContext, 'currentContext',
                          staticmethod(lambda: None)):
            type(obj).__del__(obj)
        self.assertEqual([], freed)

    def test_free_is_skipped_and_reported_without_a_context(self) -> None:
        obj = framebuffer_module.FrameBuffer.__new__(framebuffer_module.FrameBuffer)
        obj._fbo = 9
        obj._fbo_texture = 10
        freed = []
        obj.free_fbo = lambda: freed.append('called')  # type: ignore[method-assign]
        buffer = io.StringIO()
        with patch.object(helpers_module.QOpenGLContext, 'currentContext',
                          staticmethod(lambda: None)):
            with redirect_stdout(buffer):
                type(obj).__del__(obj)
        self.assertEqual([], freed, 'free_fbo raises through check_for_error without a context')
        self.assertIn('framebuffer 9', buffer.getvalue())

    def test_free_runs_when_a_context_is_current(self) -> None:
        obj = framebuffer_module.FrameBuffer.__new__(framebuffer_module.FrameBuffer)
        obj._fbo = 9
        obj._fbo_texture = 10
        freed = []
        obj.free_fbo = lambda: freed.append('called')  # type: ignore[method-assign]
        with patch.object(helpers_module.QOpenGLContext, 'currentContext',
                          staticmethod(lambda: object())):
            type(obj).__del__(obj)
        self.assertEqual(['called'], freed)

    def test_a_raising_free_does_not_escape_del(self) -> None:
        obj = framebuffer_module.FrameBuffer.__new__(framebuffer_module.FrameBuffer)
        obj._fbo = 9
        obj._fbo_texture = 10

        def boom() -> None:
            raise RuntimeError('OpenGL error after glDeleteTextures')

        obj.free_fbo = boom  # type: ignore[method-assign]
        buffer = io.StringIO()
        with patch.object(helpers_module.QOpenGLContext, 'currentContext',
                          staticmethod(lambda: object())):
            with redirect_stdout(buffer):
                type(obj).__del__(obj)
        self.assertIn('framebuffer 9', buffer.getvalue())


class TestTheOldShapesAreGone(unittest.TestCase):

    @staticmethod
    def _source(module) -> str:
        import inspect
        return inspect.getsource(module)

    def test_no_silent_except_pass_around_a_gl_delete(self) -> None:
        source = self._source(gl_buffer_module)
        self.assertNotIn('except Exception:\n                pass', source)

    def test_the_teardown_paths_use_the_shared_helper(self) -> None:
        for module in (gl_buffer_module, shader_base_module, framebuffer_module):
            with self.subTest(module=module.__name__):
                self.assertIn('delete_gl_object_on_teardown', self._source(module))


if __name__ == '__main__':
    unittest.main()
