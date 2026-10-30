"""Tests for replacing the STOS image path while keeping the existing mask."""

from __future__ import annotations

import unittest

from hypothesis import example, given
from hypothesis import strategies as st

from pyre.settings import ImageAndMaskPath
from pyre.ui.windows.stoswindow import _with_new_image


def _old_inline(current: ImageAndMaskPath | None, filename: str) -> ImageAndMaskPath:
    """Reference copy of the inline logic the handlers used before the helper."""
    mask_path = None if current is None else current.mask_fullpath
    return ImageAndMaskPath(image_fullpath=filename, mask_fullpath=mask_path)


_paths = st.text(min_size=1, max_size=40)
_current = st.none() | st.builds(
    ImageAndMaskPath,
    image_fullpath=_paths,
    mask_fullpath=st.none() | _paths,
)


class TestWithNewImage(unittest.TestCase):
    """_with_new_image swaps the image path and carries the mask forward."""

    def test_none_current_gives_no_mask(self) -> None:
        result = _with_new_image(None, r"D:\data\new.png")
        self.assertEqual(result.image_fullpath, r"D:\data\new.png")
        self.assertIsNone(result.mask_fullpath)

    def test_existing_mask_is_preserved(self) -> None:
        current = ImageAndMaskPath(image_fullpath=r"D:\data\old.png",
                                   mask_fullpath=r"D:\data\old_mask.png")
        result = _with_new_image(current, r"D:\data\new.png")
        self.assertEqual(result.image_fullpath, r"D:\data\new.png")
        self.assertEqual(result.mask_fullpath, r"D:\data\old_mask.png")

    def test_current_without_mask_stays_without_mask(self) -> None:
        current = ImageAndMaskPath(image_fullpath=r"D:\data\old.png", mask_fullpath=None)
        result = _with_new_image(current, r"D:\data\new.png")
        self.assertEqual(result.image_fullpath, r"D:\data\new.png")
        self.assertIsNone(result.mask_fullpath)

    def test_returns_new_object_and_leaves_current_unchanged(self) -> None:
        current = ImageAndMaskPath(image_fullpath=r"D:\data\old.png",
                                   mask_fullpath=r"D:\data\old_mask.png")
        result = _with_new_image(current, r"D:\data\new.png")
        self.assertIsNot(result, current)
        self.assertEqual(current.image_fullpath, r"D:\data\old.png")

    @given(current=_current, filename=_paths)
    @example(current=None, filename="a.png")
    def test_matches_old_inline_logic(self, current: ImageAndMaskPath | None,
                                      filename: str) -> None:
        self.assertEqual(_with_new_image(current, filename), _old_inline(current, filename))


if __name__ == "__main__":
    unittest.main()
