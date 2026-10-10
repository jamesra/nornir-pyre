"""Tests for InitializeStateFromSettings restoring saved Target/Source images (no STOS)."""

from __future__ import annotations

import logging
import unittest
from typing import Any
from unittest import mock

from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

import pyre.state
from pyre.interfaces.viewtype import ViewType
from pyre.settings.app import AppSettings, ImageAndMaskPath
from pyre.state import InitializeStateFromSettings, set_current_stos_config


class _LoadResult:
    """Stand-in for an image load result; only identity matters to the code under test."""

    key: str

    def __init__(self, key: str) -> None:
        self.key = key


class _FakeImageLoader:
    """Records load/viewmodel calls and raises configured exceptions per view key."""

    calls: list[tuple[str, dict[str, Any]]]
    load_errors: dict[str, BaseException]
    viewmodel_errors: dict[str, BaseException]
    _image_manager: object

    def __init__(self) -> None:
        self.calls = []
        self.load_errors = {}
        self.viewmodel_errors = {}
        self._image_manager = object()

    def load_image_into_manager(self, **kwargs: Any) -> _LoadResult:
        """Record the call, then raise the configured error for this key or return a result."""
        self.calls.append(("load", dict(kwargs)))
        err = self.load_errors.get(kwargs["key"])
        if err is not None:
            raise err
        return _LoadResult(kwargs["key"])

    def create_image_viewmodel(self, *, load_result: _LoadResult) -> None:
        """Record the call, then raise the configured error for this result's key."""
        self.calls.append(("viewmodel", {"key": load_result.key}))
        err = self.viewmodel_errors.get(load_result.key)
        if err is not None:
            raise err


def _image(path: str | None, mask: str | None = None) -> ImageAndMaskPath:
    """Build an ImageAndMaskPath, allowing a None image path as old settings files may hold."""
    return ImageAndMaskPath.model_construct(image_fullpath=path, mask_fullpath=mask)


class TestRestoreSavedImages(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = _FakeImageLoader()
        self.settings = AppSettings()
        self.settings.stos.stos_filename = None
        set_current_stos_config(mock.MagicMock())
        patcher = mock.patch.object(pyre.state, "_sync_registration_roles_from_manager")
        self.sync = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        set_current_stos_config(None)

    def _run(self) -> None:
        InitializeStateFromSettings(
            mock.MagicMock(),
            image_loader=self.loader,  # type: ignore[arg-type]
            settings=self.settings,
        )

    def test_loads_target_then_source_with_masks(self) -> None:
        self.settings.stos.target_image = _image("/t.png", "/t_mask.png")
        self.settings.stos.source_image = _image("/s.png", None)
        self._run()
        self.assertEqual(self.loader.calls, [
            ("load", {"key": ViewType.Target.value, "image_fullpath": "/t.png",
                      "mask_fullpath": "/t_mask.png"}),
            ("viewmodel", {"key": ViewType.Target.value}),
            ("load", {"key": ViewType.Source.value, "image_fullpath": "/s.png",
                      "mask_fullpath": None}),
            ("viewmodel", {"key": ViewType.Source.value}),
        ])
        self.sync.assert_called_once()
        kwargs = self.sync.call_args.kwargs
        self.assertIsNone(kwargs["stos_filename"])
        self.assertEqual(kwargs["settings_source_image_path"], "/s.png")
        self.assertEqual(kwargs["settings_target_image_path"], "/t.png")
        self.assertIs(self.sync.call_args.args[1], self.loader._image_manager)

    def test_missing_settings_skip_load_and_pass_none(self) -> None:
        self.settings.stos.target_image = None
        self.settings.stos.source_image = None
        self._run()
        self.assertEqual(self.loader.calls, [])
        kwargs = self.sync.call_args.kwargs
        self.assertIsNone(kwargs["settings_source_image_path"])
        self.assertIsNone(kwargs["settings_target_image_path"])

    def test_none_image_path_is_skipped(self) -> None:
        self.settings.stos.target_image = _image(None, "/t_mask.png")
        self.settings.stos.source_image = _image("/s.png")
        self._run()
        self.assertEqual([c[1]["key"] for c in self.loader.calls],
                         [ViewType.Source.value, ViewType.Source.value])
        kwargs = self.sync.call_args.kwargs
        self.assertIsNone(kwargs["settings_target_image_path"])
        self.assertEqual(kwargs["settings_source_image_path"], "/s.png")

    def test_file_not_found_on_target_warns_and_continues(self) -> None:
        self.settings.stos.target_image = _image("/t.png")
        self.settings.stos.source_image = _image("/s.png")
        self.loader.load_errors[ViewType.Target.value] = FileNotFoundError("gone")
        with self.assertLogs(pyre.state.__name__, level=logging.WARNING) as logs:
            self._run()
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(logs.records[0].getMessage(),
                         "Saved target image not found — starting without it: gone")
        self.assertEqual(self.loader.calls[-1], ("viewmodel", {"key": ViewType.Source.value}))
        self.sync.assert_called_once()

    def test_value_error_on_source_viewmodel_warns(self) -> None:
        self.settings.stos.target_image = _image("/t.png")
        self.settings.stos.source_image = _image("/s.png")
        self.loader.viewmodel_errors[ViewType.Source.value] = ValueError("bad")
        with self.assertLogs(pyre.state.__name__, level=logging.WARNING) as logs:
            self._run()
        self.assertEqual(logs.records[0].getMessage(),
                         "Saved source image not found — starting without it: bad")
        self.sync.assert_called_once()

    def test_other_exceptions_propagate(self) -> None:
        self.settings.stos.target_image = _image("/t.png")
        self.settings.stos.source_image = _image("/s.png")
        self.loader.load_errors[ViewType.Target.value] = RuntimeError("boom")
        with self.assertRaises(RuntimeError):
            self._run()
        self.assertEqual(len(self.loader.calls), 1)
        self.sync.assert_not_called()

    def test_no_stos_config_skips_sync(self) -> None:
        set_current_stos_config(None)
        self.settings.stos.target_image = _image("/t.png")
        self._run()
        self.sync.assert_not_called()


_slot = st.one_of(
    st.none(),
    st.tuples(
        st.one_of(st.none(), st.just("/img.png")),
        st.one_of(st.none(), st.just("/mask.png")),
        st.sampled_from([None, "load", "viewmodel"]),
        st.sampled_from([FileNotFoundError, ValueError]),
    ),
)


class TestRestoreSavedImagesProperty(unittest.TestCase):
    @hyp_settings(max_examples=150, deadline=None)
    @given(target=_slot, source=_slot)
    def test_call_sequence_and_sync_args(self, target: Any, source: Any) -> None:
        """Each present slot is loaded in Target, Source order; swallowed errors stop only that slot."""
        loader = _FakeImageLoader()
        app = AppSettings()
        app.stos.stos_filename = None
        expected: list[tuple[str, str]] = []
        for view, slot, attr in ((ViewType.Target.value, target, "target_image"),
                                 (ViewType.Source.value, source, "source_image")):
            if slot is None:
                setattr(app.stos, attr, None)
                continue
            path, mask, fail_at, exc = slot
            setattr(app.stos, attr, _image(path, mask))
            if path is None:
                continue
            expected.append(("load", view))
            if fail_at == "load":
                loader.load_errors[view] = exc("x")
                continue
            expected.append(("viewmodel", view))
            if fail_at == "viewmodel":
                loader.viewmodel_errors[view] = exc("x")

        set_current_stos_config(mock.MagicMock())
        try:
            with mock.patch.object(pyre.state, "_sync_registration_roles_from_manager") as sync:
                InitializeStateFromSettings(
                    mock.MagicMock(),
                    image_loader=loader,  # type: ignore[arg-type]
                    settings=app,
                )
        finally:
            set_current_stos_config(None)

        self.assertEqual([(kind, args["key"]) for kind, args in loader.calls], expected)
        kwargs = sync.call_args.kwargs
        self.assertEqual(kwargs["settings_target_image_path"],
                         None if target is None else target[0])
        self.assertEqual(kwargs["settings_source_image_path"],
                         None if source is None else source[0])


if __name__ == "__main__":
    unittest.main()
