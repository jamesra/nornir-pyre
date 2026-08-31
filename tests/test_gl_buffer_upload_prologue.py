"""The buffer uploader should not copy an already-contiguous array (#171).

`GLBuffer._update_buffer_data` and `GLIndexBuffer._update_buffer_data` both opened with:

```python
data = data.flatten()
data = np.ascontiguousarray(data)
```

`flatten()` always copies, and the `ascontiguousarray` that followed it had nothing left to do.
Reversing the order makes the copy conditional -- it only happens when the input really is
non-contiguous -- and the reshape is then guaranteed to be a view.

Measured on the prologue alone, output bit-identical throughout:

| elements | before | after | speedup |
|---|---|---|---|
| 81 x 8 | 0.43us | 0.15us | 2.9x |
| 2000 x 8 | 1.03us | 0.15us | 7.0x |
| 20000 x 8 | 8.56us | 0.15us | 56x |
| 200000 x 8 | 776.47us | 0.14us | 5663x |

This is the shared upload path for every buffer, so it matters most for the large
control-point buffers re-uploaded per frame, not for the ~81-vertex tile blocks that #171 was
filed against -- those are 2.5 KiB and the copy was never their bottleneck.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from pyre.gl_engine.gl_buffer import GLBuffer, GLIndexBuffer


class _Recorder:
    """Captures the array each upload call receives."""

    def __init__(self):
        self.uploaded = []

    def install(self, gl_mock):
        gl_mock.GL_ARRAY_BUFFER = 0x8892
        gl_mock.GL_ELEMENT_ARRAY_BUFFER = 0x8893
        gl_mock.GL_BUFFER_SIZE = 0x8764
        # A non-zero size with capacity already large enough drives the glBufferSubData arm.
        gl_mock.glGetBufferParameteriv.return_value = 1 << 24
        gl_mock.glBufferSubData.side_effect = \
            lambda target, offset, nbytes, data: self.uploaded.append(data)
        gl_mock.glBufferData.side_effect = \
            lambda target, size, data, usage: self.uploaded.append(data)
        return gl_mock


def _buffer(cls):
    """A buffer instance without touching a GL context in __init__."""
    obj = object.__new__(cls)
    obj._buffer = 1
    obj._capacity = 1 << 24
    obj._usage = 0
    obj._layout = None
    obj._data = None
    return obj


def _upload(cls, data):
    recorder = _Recorder()
    with patch('pyre.gl_engine.gl_buffer.gl', recorder.install(MagicMock())), \
            patch('pyre.gl_engine.gl_buffer.check_for_error'), \
            patch('pyre.gl_engine.gl_buffer._gl_buffer_name', side_effect=int):
        _buffer(cls)._update_buffer_data(data)
    assert len(recorder.uploaded) == 1
    return recorder.uploaded[0]


class TestTheUploadedBytesAreUnchanged(unittest.TestCase):
    """The reordering must not alter what reaches the driver."""

    def test_a_vertex_block_uploads_the_same_values(self):
        for n in (1, 81, 500, 2000):
            with self.subTest(n=n):
                data = np.random.default_rng(n).random((n, 8)).astype(np.float32)
                np.testing.assert_array_equal(data.flatten(), _upload(GLBuffer, data))

    def test_an_index_block_uploads_the_same_values(self):
        data = np.arange(300, dtype=np.uint32).reshape((100, 3))
        np.testing.assert_array_equal(data.flatten(), _upload(GLIndexBuffer, data))

    def test_the_upload_is_one_dimensional_and_contiguous(self):
        data = np.random.default_rng(5).random((64, 8)).astype(np.float32)
        uploaded = _upload(GLBuffer, data)
        self.assertEqual(1, uploaded.ndim)
        self.assertTrue(uploaded.flags.c_contiguous)
        self.assertEqual(data.size, uploaded.size)

    def test_dtype_is_preserved(self):
        for dtype in (np.float32, np.float64):
            with self.subTest(dtype=dtype):
                data = np.zeros((16, 8), dtype=dtype)
                self.assertEqual(dtype, _upload(GLBuffer, data).dtype)

    def test_an_already_flat_array_is_accepted(self):
        data = np.arange(64, dtype=np.float32)
        np.testing.assert_array_equal(data, _upload(GLBuffer, data))


class TestTheCopyIsGone(unittest.TestCase):
    """A contiguous input should reach the driver without being duplicated."""

    def test_a_contiguous_array_is_uploaded_as_a_view(self):
        data = np.random.default_rng(9).random((256, 8)).astype(np.float32)
        uploaded = _upload(GLBuffer, data)
        self.assertTrue(np.shares_memory(data, uploaded),
                        'flatten() would have copied here')

    def test_an_index_array_is_uploaded_as_a_view(self):
        data = np.arange(300, dtype=np.uint32).reshape((100, 3))
        self.assertTrue(np.shares_memory(data, _upload(GLIndexBuffer, data)))

    def test_the_source_array_is_not_modified(self):
        data = np.random.default_rng(11).random((64, 8)).astype(np.float32)
        before = data.copy()
        _upload(GLBuffer, data)
        np.testing.assert_array_equal(before, data)


class TestNonContiguousInputStillWorks(unittest.TestCase):
    """reshape(-1) alone would raise on these; ascontiguousarray first does not."""

    def test_a_fortran_ordered_array_uploads_correctly(self):
        data = np.asfortranarray(
            np.random.default_rng(13).random((100, 8)).astype(np.float32))
        uploaded = _upload(GLBuffer, data)
        np.testing.assert_array_equal(data.flatten(), uploaded)
        self.assertTrue(uploaded.flags.c_contiguous)

    def test_a_strided_view_uploads_correctly(self):
        base = np.random.default_rng(17).random((100, 16)).astype(np.float32)
        data = base[:, ::2]
        self.assertFalse(data.flags.c_contiguous)
        uploaded = _upload(GLBuffer, data)
        np.testing.assert_array_equal(data.flatten(), uploaded)
        self.assertTrue(uploaded.flags.c_contiguous)

    def test_a_transposed_array_uploads_in_c_order(self):
        data = np.random.default_rng(19).random((8, 64)).astype(np.float32).T
        np.testing.assert_array_equal(data.flatten(), _upload(GLBuffer, data))


if __name__ == '__main__':
    unittest.main()
