"""Tests the precision boundary for rotation and scale pivots.

The pivot sites in TransformController hand a value straight to the rigid transform, which
casts to float32 on entry, so the caller's dtype is unobservable today. ScaleFixed differs:
it multiplies the pivot before that boundary, so float64 there avoids double rounding.

These tests pin both halves. If the rigid transform ever stops casting on entry, the
observability test below starts failing, which is the signal that the caller's dtype has
begun to matter.
"""

from __future__ import annotations

import inspect
import re
import unittest

import numpy as np

from nornir_imageregistration.transforms.rigid import CenteredSimilarity2DTransform
from pyre.controllers.transformcontroller import TransformController

# Slice coordinates in the tens of thousands, the regime the finding names.
PIVOT = np.array((32768.0 + 0.3, 41000.0 + 0.7), dtype=np.float64)


def _make_transform() -> CenteredSimilarity2DTransform:
    return CenteredSimilarity2DTransform(
        target_offset=np.array((0.0, 0.0)),
        source_rotation_center=np.array((0.0, 0.0)),
        angle=0.0, scalar=1.0)


def _as32(pivot: np.ndarray) -> np.ndarray:
    return np.asarray(pivot, dtype=np.float32).ravel()[:2]


def _as64(pivot: np.ndarray) -> np.ndarray:
    return np.asarray(pivot, dtype=np.float64).ravel()[:2]


def _state(t: CenteredSimilarity2DTransform) -> tuple:
    return (t._target_offset.copy(), t._source_space_center_of_rotation.copy(),
            t._angle, t._scalar)


def _assert_same_state(case: unittest.TestCase, a, b, msg: str) -> None:
    case.assertTrue(np.array_equal(a[0], b[0]), f"{msg}: target_offset")
    case.assertTrue(np.array_equal(a[1], b[1]), f"{msg}: center_of_rotation")
    case.assertEqual(a[2], b[2], f"{msg}: angle")
    case.assertEqual(a[3], b[3], f"{msg}: scalar")


class TestThePivotDtypeIsUnobservable(unittest.TestCase):
    """The rigid transform casts the pivot to float32 on entry, so the caller cannot matter."""

    OPS = (
        ('RotateFixedAboutSourcePoint', lambda t, p: t.RotateFixedAboutSourcePoint(0.005, p)),
        ('ScaleWarpedAboutSourcePoint', lambda t, p: t.ScaleWarpedAboutSourcePoint(1.1, p)),
    )

    def test_a_single_operation_is_identical(self) -> None:
        for name, op in self.OPS:
            with self.subTest(op=name):
                a, b = _make_transform(), _make_transform()
                op(a, _as32(PIVOT))
                op(b, _as64(PIVOT))
                _assert_same_state(self, _state(a), _state(b), name)

    def test_a_long_notch_train_does_not_diverge(self) -> None:
        """The finding's accumulation claim: 128 notches must not separate the two dtypes."""
        for name, op in self.OPS:
            with self.subTest(op=name):
                a, b = _make_transform(), _make_transform()
                for _ in range(128):
                    op(a, _as32(PIVOT))
                    op(b, _as64(PIVOT))
                _assert_same_state(self, _state(a), _state(b), f"{name} after 128 notches")

    def test_the_entry_cast_is_what_makes_it_unobservable(self) -> None:
        source = inspect.getsource(
            CenteredSimilarity2DTransform._pin_source_point_under_mutation)
        self.assertRegex(
            source, r'source_point\s*=\s*np\.asarray\(\s*source_point_yx,\s*dtype=np\.float32',
            'the caller dtype is only unobservable while the callee casts on entry; if this '
            'cast is gone, the pivot dtype in TransformController now matters')


class TestTheDriftIsFarBelowAPixel(unittest.TestCase):
    """The finding predicts ~4e-3 px per notch accumulating; measure what actually happens."""

    def _drift(self, op, notches: int) -> float:
        t = _make_transform()
        total = 0.0
        for _ in range(notches):
            before = np.squeeze(t.Transform(PIVOT.reshape(1, 2)))
            op(t, _as64(PIVOT))
            after = np.squeeze(t.Transform(PIVOT.reshape(1, 2)))
            total += float(np.linalg.norm(before - after))
        return total

    def test_rotation_drift_stays_negligible(self) -> None:
        drift = self._drift(lambda t, p: t.RotateFixedAboutSourcePoint(0.005, p), 128)
        self.assertLess(drift, 0.01, f'128 rotate notches drifted {drift} px')

    def test_scale_drift_stays_negligible(self) -> None:
        drift = self._drift(lambda t, p: t.ScaleWarpedAboutSourcePoint(1.1, p), 128)
        self.assertLess(drift, 0.01, f'128 scale notches drifted {drift} px')

    def test_the_pinned_point_holds_at_the_stored_pivot(self) -> None:
        """Evaluated at the pivot the model stored, the pin holds across a notch train."""
        stored = _as32(PIVOT).astype(np.float64)
        t = _make_transform()
        start = np.squeeze(t.Transform(stored.reshape(1, 2)))
        for _ in range(128):
            t.RotateFixedAboutSourcePoint(0.005, _as64(PIVOT))
        end = np.squeeze(t.Transform(stored.reshape(1, 2)))
        self.assertTrue(np.allclose(start, end, atol=1e-6),
                        f'stored pivot moved {np.linalg.norm(start - end)} px over 128 notches')


class TestTheScaleFixedSiteNeedsFloat64(unittest.TestCase):
    """Unlike the pivot sites, this one does arithmetic before the float32 boundary."""

    def test_float64_is_closer_to_exact(self) -> None:
        rng = np.random.default_rng(20260831)
        pivots = rng.uniform(0.0, 65536.0, size=(20000, 2))
        scales = rng.uniform(0.5, 2.0, size=20000)

        exact = pivots * (1.0 - scales)[:, None]
        via64 = (pivots * (1.0 - scales)[:, None]).astype(np.float32)
        via32 = (pivots.astype(np.float32)
                 * (1.0 - scales)[:, None].astype(np.float32)).astype(np.float32)

        differ = ~np.all(via64 == via32, axis=1)
        self.assertTrue(differ.any(),
                        'the dtype must be observable here, or float64 would be pointless')

        err64 = np.abs(via64[differ].astype(np.float64) - exact[differ]).sum(axis=1)
        err32 = np.abs(via32[differ].astype(np.float64) - exact[differ]).sum(axis=1)
        self.assertTrue(np.all(err64 <= err32),
                        'float64 before the boundary should never be worse')

    def test_the_scale_fixed_site_still_uses_float64(self) -> None:
        source = inspect.getsource(TransformController.ScaleFixed)
        self.assertIn('dtype=np.float64', source)


class TestTheCallerSitesAgree(unittest.TestCase):
    """All pivot sites should use one dtype so the asymmetry is not re-introduced."""

    def test_no_pivot_site_downcasts_to_float32(self) -> None:
        for name in ('Rotate', 'ScaleWarped', 'ScaleFixed'):
            with self.subTest(method=name):
                source = inspect.getsource(getattr(TransformController, name))
                pivot_casts = re.findall(r'np\.asarray\(\s*center,\s*dtype=np\.(float\d+)',
                                         source)
                self.assertTrue(pivot_casts, f'{name} should cast its center argument')
                self.assertNotIn('float32', pivot_casts,
                                 f'{name} downcasts the pivot below the ScaleFixed path')


if __name__ == '__main__':
    unittest.main()
