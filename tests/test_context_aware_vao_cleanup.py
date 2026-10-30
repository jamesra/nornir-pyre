"""Tests that ContextAwareVAOHelper.cleanup does not drop undeleted VAO names.

A VAO can only be deleted while its own context is current. cleanup() guarded the delete
on that, but then cleared the whole per-context dict regardless, so VAOs belonging to other
live contexts were forgotten without ever being released -- a leak for the life of the
process. __del__ makes this routine, since it runs under whatever context happens to be
current at collection time.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pyre.gl_engine import context_aware_vao
from pyre.gl_engine.context_aware_vao import ContextAwareVAOHelper


class _Context:
    """Stand-in for QOpenGLContext; identity-keyed and able to go invalid."""

    def __init__(self, name: str, valid: bool = True) -> None:
        self.name = name
        self._valid = valid

    def isValid(self) -> bool:
        return self._valid

    def invalidate(self) -> None:
        self._valid = False

    def __repr__(self) -> str:
        return f'<Context {self.name}>'


class _Helper(ContextAwareVAOHelper):
    """Concrete subclass: only _create_vao_for_context is abstract."""

    def _create_vao_for_context(self, context) -> int:
        return 0


class _FakeGL:
    """Records deletes instead of issuing them."""

    def __init__(self, fail_on: set[int] | None = None) -> None:
        self.deleted_vaos: list[int] = []
        self.deleted_buffers: list[int] = []
        self._fail_on = fail_on or set()

    def glDeleteVertexArrays(self, count: int, ids) -> None:
        vao_id = ids[0]
        if vao_id in self._fail_on:
            raise RuntimeError(f'simulated GL failure for {vao_id}')
        self.deleted_vaos.append(vao_id)

    def glDeleteBuffers(self, count: int, ids) -> None:
        self.deleted_buffers.append(ids[0])


class _Fixture:
    """Runs cleanup() with a chosen current context and a fake GL."""

    def __init__(self, contexts: dict, current, fail_on: set[int] | None = None,
                 index_buffer: int | None = None) -> None:
        self.helper = _Helper()
        self.helper._context_vaos = dict(contexts)
        self.helper._index_buffer_id = index_buffer
        self.gl = _FakeGL(fail_on)
        self._current = current

    def cleanup(self) -> None:
        with patch.object(context_aware_vao, 'gl', self.gl), \
                patch.object(context_aware_vao, 'check_for_error', lambda *a, **k: None), \
                patch.object(context_aware_vao.QOpenGLContext, 'currentContext',
                             staticmethod(lambda: self._current)):
            self.helper.cleanup()

    @property
    def remaining(self) -> dict:
        return self.helper._context_vaos


class TestOtherContextsAreNotForgotten(unittest.TestCase):

    def setUp(self) -> None:
        self.a, self.b, self.c = _Context('A'), _Context('B'), _Context('C')
        self.vaos = {self.a: 11, self.b: 22, self.c: 33}

    def test_only_the_current_context_is_deleted(self) -> None:
        fx = _Fixture(self.vaos, current=self.b)
        fx.cleanup()
        self.assertEqual([22], fx.gl.deleted_vaos)

    def test_the_undeleted_names_are_retained(self) -> None:
        """The headline leak: these used to be cleared without being released."""
        fx = _Fixture(self.vaos, current=self.b)
        fx.cleanup()
        self.assertEqual({self.a: 11, self.c: 33}, fx.remaining)

    def test_a_later_cleanup_can_still_release_them(self) -> None:
        fx = _Fixture(self.vaos, current=self.b)
        fx.cleanup()
        for context in (self.a, self.c):
            fx._current = context
            fx.cleanup()
        self.assertEqual([22, 11, 33], fx.gl.deleted_vaos)
        self.assertEqual({}, fx.remaining)

    def test_every_name_is_eventually_released(self) -> None:
        fx = _Fixture(self.vaos, current=self.a)
        for context in (self.a, self.b, self.c):
            fx._current = context
            fx.cleanup()
        self.assertEqual(sorted(self.vaos.values()), sorted(fx.gl.deleted_vaos))


class TestDestroyedContexts(unittest.TestCase):

    def test_an_invalid_context_is_dropped_without_a_delete(self) -> None:
        """GL objects die with their context, so there is nothing left to release."""
        dead, live = _Context('dead', valid=False), _Context('live')
        fx = _Fixture({dead: 11, live: 22}, current=live)
        fx.cleanup()
        self.assertEqual([22], fx.gl.deleted_vaos)
        self.assertEqual({}, fx.remaining)

    def test_a_context_invalidated_later_stops_being_retained(self) -> None:
        a, b = _Context('A'), _Context('B')
        fx = _Fixture({a: 11, b: 22}, current=b)
        fx.cleanup()
        self.assertEqual({a: 11}, fx.remaining)
        a.invalidate()
        fx.cleanup()
        self.assertEqual({}, fx.remaining)


class TestNoContextCurrent(unittest.TestCase):
    """__del__ can run with no context current at all."""

    def test_nothing_is_deleted_and_nothing_is_lost(self) -> None:
        a, b = _Context('A'), _Context('B')
        fx = _Fixture({a: 11, b: 22}, current=None)
        fx.cleanup()
        self.assertEqual([], fx.gl.deleted_vaos)
        self.assertEqual({a: 11, b: 22}, fx.remaining)

    def test_the_index_buffer_is_kept_when_no_context_is_current(self) -> None:
        fx = _Fixture({}, current=None, index_buffer=77)
        fx.cleanup()
        self.assertEqual([], fx.gl.deleted_buffers)
        self.assertEqual(77, fx.helper._index_buffer_id,
                         'deleting a buffer needs a current context; keep it for later')

    def test_the_index_buffer_is_released_once_a_context_is_current(self) -> None:
        a = _Context('A')
        fx = _Fixture({}, current=a, index_buffer=77)
        fx.cleanup()
        self.assertEqual([77], fx.gl.deleted_buffers)
        self.assertIsNone(fx.helper._index_buffer_id)


class TestAFailedDeleteIsRetained(unittest.TestCase):

    def test_a_raising_delete_keeps_the_name(self) -> None:
        a = _Context('A')
        fx = _Fixture({a: 11}, current=a, fail_on={11})
        fx.cleanup()
        self.assertEqual([], fx.gl.deleted_vaos)
        self.assertEqual({a: 11}, fx.remaining,
                         'a failed delete must not silently forget the name')

    def test_a_failure_does_not_block_other_contexts(self) -> None:
        a, b = _Context('A'), _Context('B')
        fx = _Fixture({a: 11, b: 22}, current=a, fail_on={11})
        fx.cleanup()
        fx._current = b
        fx.cleanup()
        self.assertEqual([22], fx.gl.deleted_vaos)
        self.assertEqual({a: 11}, fx.remaining)


if __name__ == '__main__':
    unittest.main()
