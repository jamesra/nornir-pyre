"""swap_columns_to_XY should hand the upload path a contiguous array (#170).

Every caller of `TransformController.swap_columns_to_XY` feeds the result straight into a GL
buffer, and `GLBuffer._update_buffer_data` needs it C-contiguous. The previous
`input[:, [1, 0, 3, 2]]` returned a **non**-contiguous array, so the uploader's
`ascontiguousarray` had to copy the whole Nx4 block a second time.

Writing the four columns into a C-ordered buffer costs about the same as the fancy index and
removes that second pass. Measured on the full convert-swap-upload sequence, output
bit-identical throughout:

| N | before | after | gain |
|---|---|---|---|
| 100 | 2.50us | 1.87us | 1.34x |
| 1000 | 6.42us | 3.74us | 1.72x |
| 5000 | 22.49us | 9.84us | 2.29x |
| 20000 | 82.64us | 33.17us | 2.49x |

The composite display-row path of #170 performs two of these per frame, so it saves 5.3us at
N=1000 and 97us at N=20000. All six call sites benefit, not just the composite one.

Column convention, per the pyre-stos-rigid-transform-ui skill: GL columns 0:2 are TargetPoints
and 2:4 are SourcePoints, each pair swapped from (Y, X) to (X, Y). This must not change --
the composite override relies on the setter doing the swap, which is why the display-row helper
returns unswapped YX rows.
"""

from __future__ import annotations

import unittest

import numpy as np

from pyre.controllers.transformcontroller import TransformController

_swap = TransformController.swap_columns_to_XY


def _points(n: int, dtype=np.float32) -> np.ndarray:
    return (np.random.default_rng(n).random((n, 4)) * 1000.0).astype(dtype)


class TestTheSwapIsUnchanged(unittest.TestCase):
    """The column mapping is a rendering contract; it must stay exactly as it was."""

    def test_it_matches_the_fancy_index_it_replaced(self):
        for n in (1, 5, 100, 1000):
            for dtype in (np.float32, np.float64):
                with self.subTest(n=n, dtype=dtype):
                    pts = _points(n, dtype)
                    np.testing.assert_array_equal(pts[:, [1, 0, 3, 2]], _swap(pts))

    def test_each_pair_is_swapped(self):
        pts = np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32)
        np.testing.assert_array_equal(np.array([[2.0, 1.0, 4.0, 3.0]]), _swap(pts))

    def test_dtype_is_preserved(self):
        for dtype in (np.float32, np.float64):
            with self.subTest(dtype=dtype):
                self.assertEqual(dtype, _swap(_points(8, dtype)).dtype)

    def test_the_shape_is_nx4(self):
        for n in (1, 17, 500):
            with self.subTest(n=n):
                self.assertEqual((n, 4), _swap(_points(n)).shape)

    def test_an_empty_set_is_handled(self):
        out = _swap(np.empty((0, 4), dtype=np.float32))
        self.assertEqual((0, 4), out.shape)

    def test_extra_columns_are_dropped_as_before(self):
        pts = (np.random.default_rng(3).random((10, 8)) * 100).astype(np.float32)
        np.testing.assert_array_equal(pts[:, [1, 0, 3, 2]], _swap(pts))

    def test_the_input_is_not_modified(self):
        pts = _points(64)
        before = pts.copy()
        _swap(pts)
        np.testing.assert_array_equal(before, pts)


class TestTheResultIsUploadReady(unittest.TestCase):
    """The point of the change."""

    def test_the_result_is_c_contiguous(self):
        for n in (1, 100, 1000, 5000):
            with self.subTest(n=n):
                self.assertTrue(_swap(_points(n)).flags.c_contiguous)

    def test_the_fancy_index_was_not(self):
        # The premise. If NumPy ever starts returning contiguous results here, this test
        # fails and the change becomes redundant rather than wrong.
        pts = _points(1000)
        self.assertFalse(pts[:, [1, 0, 3, 2]].flags.c_contiguous)

    def test_the_uploader_prologue_needs_no_copy(self):
        pts = _points(1000)
        swapped = _swap(pts)
        flattened = np.ascontiguousarray(swapped).reshape(-1)
        self.assertTrue(np.shares_memory(swapped, flattened),
                        'a non-contiguous swap would force a second full copy here')

    def test_a_non_contiguous_input_still_works(self):
        base = (np.random.default_rng(9).random((100, 8)) * 100).astype(np.float32)
        strided = base[:, ::2]
        self.assertFalse(strided.flags.c_contiguous)
        np.testing.assert_array_equal(strided[:, [1, 0, 3, 2]], _swap(strided))
        self.assertTrue(_swap(strided).flags.c_contiguous)

    def test_a_fortran_ordered_input_still_works(self):
        pts = np.asfortranarray(_points(100))
        np.testing.assert_array_equal(pts[:, [1, 0, 3, 2]], _swap(pts))
        self.assertTrue(_swap(pts).flags.c_contiguous)


class TestTheColumnConventionHolds(unittest.TestCase):
    """Columns 0:2 are TargetPoints, 2:4 SourcePoints, each swapped YX -> XY."""

    def test_target_columns_come_from_the_first_pair(self):
        pts = np.array([[10.0, 20.0, 30.0, 40.0]], dtype=np.float32)
        out = _swap(pts)
        self.assertEqual(20.0, out[0, 0], 'target X is source-array column 1')
        self.assertEqual(10.0, out[0, 1], 'target Y is source-array column 0')

    def test_source_columns_come_from_the_second_pair(self):
        pts = np.array([[10.0, 20.0, 30.0, 40.0]], dtype=np.float32)
        out = _swap(pts)
        self.assertEqual(40.0, out[0, 2])
        self.assertEqual(30.0, out[0, 3])

    def test_swapping_twice_returns_the_original(self):
        pts = _points(50)
        np.testing.assert_array_equal(pts, _swap(_swap(pts)))


if __name__ == '__main__':
    unittest.main()
