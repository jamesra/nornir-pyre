"""
Unit tests for pure logic (no Qt, no OpenGL). Safe to run in CI without display.
"""
import unittest
from unittest.mock import MagicMock, patch

from pyre.interfaces.viewtype import ViewType, convert_to_key
import pyre.state
from pyre.state.stos import param_to_stosfile
from pyre.selection_event_data import InputModifiers
from pyre.observable.olist import ObservableList, ObservedAction as ListObservedAction
from pyre.observable import ObservableSet, ObservedAction as SetObservedAction


class TestViewTypeConvertToKey(unittest.TestCase):
    def test_convert_string_returns_unchanged(self):
        self.assertEqual(convert_to_key("Source"), "Source")
        self.assertEqual(convert_to_key(""), "")

    def test_convert_enum_returns_string_value(self):
        self.assertEqual(convert_to_key(ViewType.Source), "Source")
        self.assertEqual(convert_to_key(ViewType.Target), "Target")
        self.assertEqual(convert_to_key(ViewType.Composite), "Composite")

    def test_convert_invalid_raises_type_error(self):
        with self.assertRaises(TypeError) as ctx:
            convert_to_key(42)
        self.assertIn("key must be a string or ViewType", str(ctx.exception))
        with self.assertRaises(TypeError):
            convert_to_key(None)


class TestStateFacade(unittest.TestCase):
    def setUp(self):
        self._saved_stos = pyre.state.get_current_stos_config()
        self._saved_mosaic = pyre.state.get_current_mosaic_config()

    def tearDown(self):
        pyre.state.set_current_stos_config(self._saved_stos)
        pyre.state.set_current_mosaic_config(self._saved_mosaic)

    def test_get_set_stos_config(self):
        mock = MagicMock()
        pyre.state.set_current_stos_config(mock)
        self.assertIs(pyre.state.get_current_stos_config(), mock)
        pyre.state.set_current_stos_config(None)
        self.assertIsNone(pyre.state.get_current_stos_config())

    def test_get_set_mosaic_config(self):
        mock = MagicMock()
        pyre.state.set_current_mosaic_config(mock)
        self.assertIs(pyre.state.get_current_mosaic_config(), mock)
        pyre.state.set_current_mosaic_config(None)
        self.assertIsNone(pyre.state.get_current_mosaic_config())


class TestParamToStosFile(unittest.TestCase):
    def test_passthrough_stosfile(self):
        from nornir_imageregistration import StosFile
        # StosFile() is used inside Load(); passthrough returns the same instance
        stub = StosFile()
        result = param_to_stosfile(stub)
        self.assertIs(result, stub)

    def test_string_calls_load(self):
        with patch("pyre.state.stos.StosFile") as mock_stos_class:
            mock_instance = MagicMock()
            mock_stos_class.Load.return_value = mock_instance
            result = param_to_stosfile("/some/path.stos")
            mock_stos_class.Load.assert_called_once_with("/some/path.stos")
            self.assertIs(result, mock_instance)

    def test_invalid_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            param_to_stosfile(123)
        self.assertIn("Could not load stos file", str(ctx.exception))


class TestInputModifiers(unittest.TestCase):
    def test_is_key_chord_pressed_only_shift(self):
        self.assertTrue(
            InputModifiers.is_key_chord_pressed(InputModifiers.ShiftKey, InputModifiers.ShiftKey)
        )
        self.assertFalse(
            InputModifiers.is_key_chord_pressed(InputModifiers.ShiftKey | InputModifiers.ControlKey, InputModifiers.ShiftKey)
        )
        self.assertFalse(
            InputModifiers.is_key_chord_pressed(InputModifiers.NoModifiers, InputModifiers.ShiftKey)
        )

    def test_is_mouse_chord_pressed_only_left(self):
        self.assertTrue(
            InputModifiers.is_mouse_chord_pressed(InputModifiers.LeftMouseButton, InputModifiers.LeftMouseButton)
        )
        self.assertFalse(
            InputModifiers.is_mouse_chord_pressed(
                InputModifiers.LeftMouseButton | InputModifiers.RightMouseButton,
                InputModifiers.LeftMouseButton,
            )
        )

    def test_is_chord_pressed_combined(self):
        chord = InputModifiers.ShiftKey | InputModifiers.LeftMouseButton
        self.assertTrue(
            InputModifiers.is_chord_pressed(chord, chord)
        )
        self.assertFalse(
            InputModifiers.is_chord_pressed(InputModifiers.ShiftKey, chord)
        )

    def test_is_only_one_key_modifier_set(self):
        self.assertTrue(
            InputModifiers.is_only_one_key_modifier_set(InputModifiers.ShiftKey, InputModifiers.ShiftKey)
        )
        self.assertFalse(
            InputModifiers.is_only_one_key_modifier_set(InputModifiers.ShiftKey | InputModifiers.AltKey, InputModifiers.ShiftKey)
        )

    def test_is_only_one_mouse_button_pressed(self):
        self.assertTrue(
            InputModifiers.is_only_one_mouse_button_pressed(InputModifiers.LeftMouseButton, InputModifiers.LeftMouseButton)
        )
        self.assertFalse(
            InputModifiers.is_only_one_mouse_button_pressed(
                InputModifiers.LeftMouseButton | InputModifiers.MiddleMouseButton,
                InputModifiers.LeftMouseButton,
            )
        )


class TestObservableList(unittest.TestCase):
    def test_append_notifies_observer(self):
        calls = []
        def observe(lst, action, items):
            calls.append((action, items))
        ol = ObservableList()
        ol.add_observer(observe)
        ol.append(1)
        ol.append(2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], ListObservedAction.ADD)
        self.assertEqual(calls[0][1], [0])
        self.assertEqual(calls[1][1], [1])

    def test_remove_notifies_observer(self):
        calls = []
        def observe(lst, action, items):
            calls.append((action, items))
        ol = ObservableList([1, 2, 3])
        ol.add_observer(observe)
        ol.remove(2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], ListObservedAction.REMOVE)
        self.assertEqual(calls[0][1], [1])

    def test_clear_notifies_observer(self):
        calls = []
        def observe(lst, action, items):
            calls.append((action, items))
        ol = ObservableList([1, 2])
        ol.add_observer(observe)
        ol.clear()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], ListObservedAction.CLEAR)


class TestObservableSet(unittest.TestCase):
    def test_add_notifies_observer(self):
        calls = []
        def observe(s, action, items):
            calls.append((action, items))
        os = ObservableSet()
        os.add_observer(observe)
        os.add(1)
        os.add(2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], SetObservedAction.ADD)
        self.assertEqual(calls[0][1], frozenset([1]))
        self.assertEqual(calls[1][1], frozenset([2]))

    def test_discard_notifies_observer(self):
        calls = []
        def observe(s, action, items):
            calls.append((action, items))
        os = ObservableSet([1, 2])
        os.add_observer(observe)
        os.discard(1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], SetObservedAction.REMOVE)
        self.assertEqual(calls[0][1], frozenset([1]))

    def test_clear_notifies_observer(self):
        calls = []
        def observe(s, action, items):
            calls.append((action, items))
        os = ObservableSet([1, 2])
        os.add_observer(observe)
        os.clear()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], SetObservedAction.CLEAR)


if __name__ == "__main__":
    unittest.main()
