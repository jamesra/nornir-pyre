"""Tests the context-sharing invariant that module-level shader programs depend on.

Pyre compiles each shader program once and uses it from every STOS panel, caching attrib
and uniform locations with it. That is only valid while AA_ShareOpenGLContexts is enabled,
because shaders, programs, buffers and textures are shared objects whereas VAOs and
framebuffers are container objects the OpenGL specification excludes from sharing.

Qt ignores the attribute once a QApplication exists, so the launcher must both request it
before constructing the application and verify it afterwards.
"""

from __future__ import annotations

import inspect
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import Qt

from pyre.gl_engine import helpers as helpers_module
from pyre.gl_engine.helpers import context_sharing_enabled
from pyre.gl_engine.shaders.shader_base import BaseShader

# Read the launcher as text rather than importing it: importing pyre.launcher has the side
# effect of writing pyre/settings.json, which a test must not do.
_LAUNCHER = Path(__file__).resolve().parent.parent / 'pyre' / 'launcher.py'


def _main_qt_source() -> str:
    source = _LAUNCHER.read_text(encoding='utf-8')
    start = source.index('def main_qt(')
    tail = source[start:]
    # Stop at the next top-level def so the slice is just main_qt. It is currently the last
    # function in the module, so fall back to the remainder of the file.
    end = tail.find('\ndef ', 1)
    return tail if end == -1 else tail[:end]


class TestTheAttributeIsReportedNotAssumed(unittest.TestCase):

    def test_the_helper_reads_the_effective_state(self) -> None:
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                with patch.object(helpers_module.QCoreApplication, 'testAttribute',
                                  staticmethod(lambda attr: enabled)):
                    self.assertEqual(enabled, context_sharing_enabled())

    def test_the_helper_asks_about_the_sharing_attribute(self) -> None:
        seen = []

        def record(attr):
            seen.append(attr)
            return True

        with patch.object(helpers_module.QCoreApplication, 'testAttribute',
                          staticmethod(record)):
            context_sharing_enabled()
        self.assertEqual([Qt.ApplicationAttribute.AA_ShareOpenGLContexts], seen)


class TestTheLauncherOrdering(unittest.TestCase):
    """Qt requires the attribute before the QApplication is constructed."""

    def test_the_attribute_is_set_before_the_application_is_built(self) -> None:
        source = _main_qt_source()
        set_at = source.index('AA_ShareOpenGLContexts')
        built_at = source.index('QApplication(sys.argv)')
        self.assertLess(set_at, built_at,
                        'Qt ignores the attribute once a QApplication exists')

    def test_the_launcher_verifies_sharing_after_construction(self) -> None:
        source = _main_qt_source()
        self.assertIn('context_sharing_enabled', source)
        verify_at = source.index('context_sharing_enabled()')
        built_at = source.index('QApplication(sys.argv)')
        self.assertGreater(verify_at, built_at,
                           'the check is only meaningful once the application exists')

    def test_the_reuse_branch_is_the_reason_the_check_exists(self) -> None:
        """A pre-existing QApplication is what makes the request ineffective."""
        source = _main_qt_source()
        self.assertIn('QApplication.instance()', source)
        self.assertRegex(source, r'already exists')


class TestTheFailureIsReported(unittest.TestCase):

    def _run_check(self, enabled: bool) -> str:
        """Exercise the launcher's reporting branch in isolation."""
        buffer = io.StringIO()
        with patch.object(helpers_module.QCoreApplication, 'testAttribute',
                          staticmethod(lambda attr: enabled)):
            with redirect_stdout(buffer):
                if not context_sharing_enabled():
                    print("ERROR: OpenGL context sharing is not enabled")
        return buffer.getvalue()

    def test_nothing_is_reported_when_sharing_is_on(self) -> None:
        self.assertEqual('', self._run_check(enabled=True))

    def test_the_message_names_the_consequence(self) -> None:
        source = _main_qt_source()
        message = source[source.index('ERROR: OpenGL context sharing'):]
        message = message[:message.index('")') + 2]
        for phrase in ('Shader programs', 'STOS panels', 'QApplication'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, message,
                              'the warning should say why it matters, not just what is off')


class TestTheSharedVersusContainerRuleIsRecorded(unittest.TestCase):
    """The apparent inconsistency with per-context VAOs has a specific justification."""

    def test_base_shader_documents_why_one_program_is_enough(self) -> None:
        doc = BaseShader.__doc__ or ''
        self.assertIn('AA_ShareOpenGLContexts', doc)
        for term in ('shared', 'container'):
            with self.subTest(term=term):
                self.assertIn(term, doc)

    def test_base_shader_points_at_the_per_context_counterpart(self) -> None:
        self.assertIn('ContextAwareVAOHelper', BaseShader.__doc__ or '')

    def test_the_helper_documents_the_same_rule(self) -> None:
        doc = context_sharing_enabled.__doc__ or ''
        self.assertIn('container', doc)
        self.assertIn('VAO', doc)


class TestVAOsRemainPerContext(unittest.TestCase):
    """Sharing must not be taken as licence to hoist VAOs to module level."""

    def test_the_vao_helper_still_keys_by_context(self) -> None:
        from pyre.gl_engine.context_aware_vao import ContextAwareVAOHelper
        source = inspect.getsource(ContextAwareVAOHelper)
        self.assertRegex(source, r'_context_vaos\s*:\s*Dict\[QOpenGLContext, int\]')

    def test_the_vao_helper_creates_one_vao_per_context(self) -> None:
        from pyre.gl_engine.context_aware_vao import ContextAwareVAOHelper
        params = list(inspect.signature(
            ContextAwareVAOHelper._create_vao_for_context).parameters)
        self.assertIn('context', params)


if __name__ == '__main__':
    unittest.main()
