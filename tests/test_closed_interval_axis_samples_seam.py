"""Regression for #206: seam float noise must not duplicate tile-edge samples."""
from __future__ import annotations

import unittest

import numpy as np

from pyre.views import gltiles


class TestClosedIntervalAxisSamplesSeamSnap(unittest.TestCase):
    def test_near_hi_endpoint_collapses_to_exact_edge(self) -> None:
        """#206: 4096 + 1e-9 must not survive np.unique next to hi=4096."""
        axis = np.array([4096.0 + 1e-9, 6144.0, 8192.0], dtype=np.float64)
        samples = gltiles._closed_interval_axis_samples(axis, 4096.0, 8192.0)
        self.assertEqual(int(samples.shape[0]), 3)
        np.testing.assert_array_equal(samples, np.array([4096.0, 6144.0, 8192.0]))
        self.assertTrue(np.all(np.diff(samples) > 1e-6))

    def test_near_lo_endpoint_collapses_to_exact_edge(self) -> None:
        axis = np.array([0.0, 2048.0, 4096.0 - 1e-9], dtype=np.float64)
        samples = gltiles._closed_interval_axis_samples(axis, 0.0, 4096.0)
        self.assertEqual(int(samples.shape[0]), 3)
        np.testing.assert_array_equal(samples, np.array([0.0, 2048.0, 4096.0]))

    def test_distinct_interior_lattice_is_kept(self) -> None:
        axis = np.array([0.0, 100.0, 200.0], dtype=np.float64)
        samples = gltiles._closed_interval_axis_samples(axis, 0.0, 200.0)
        np.testing.assert_array_equal(samples, axis)


if __name__ == '__main__':
    unittest.main()
