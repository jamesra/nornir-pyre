"""Tests for Pyre job-scoped phase profiling."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from nornir_shared import profiling
from pyre import phase_profile


class TestPyrePhaseProfile(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "NORNIR_LOG_ROOT",
                "NORNIR_LOG_SESSION_ID",
                "NORNIR_PHASE_PROFILE_LOG",
                "NORNIR_PHASE_PROFILE_PSTATS",
                "NORNIR_PHASE_PROFILE_JOBS",
            )
        }
        import nornir_shared.misc as nornir_misc

        nornir_misc._active_log_session_id = None
        profiling._active_profiler = None

    def tearDown(self) -> None:
        import nornir_shared.misc as nornir_misc

        nornir_misc._active_log_session_id = None
        profiling._active_profiler = None
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_ensure_configured_defaults_under_log_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["NORNIR_LOG_ROOT"] = tmp
            os.environ["NORNIR_LOG_SESSION_ID"] = "20260101-120000"
            os.environ.pop("NORNIR_PHASE_PROFILE_LOG", None)
            os.environ.pop("NORNIR_PHASE_PROFILE_PSTATS", None)
            profiler = phase_profile.ensure_configured()
            self.assertIsNotNone(profiler)
            assert profiler is not None
            self.assertTrue(profiler.enabled)
            self.assertEqual(
                profiler.log_path,
                Path(tmp) / "2026-01-01" / "nornir-phase-profile-20260101-120000.ndjson",
            )
            self.assertEqual(
                profiler.profile_path,
                Path(tmp) / "2026-01-01" / "nornir-phase-profile-20260101-120000.pstats",
            )

    def test_jobs_opt_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["NORNIR_LOG_ROOT"] = tmp
            os.environ["NORNIR_PHASE_PROFILE_JOBS"] = "0"
            self.assertIsNone(phase_profile.ensure_configured())

    def test_profile_registration_job_writes_cprofile_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["NORNIR_LOG_ROOT"] = tmp
            os.environ["NORNIR_LOG_SESSION_ID"] = "20260103-010203"
            os.environ.pop("NORNIR_PHASE_PROFILE_LOG", None)
            profiler = phase_profile.ensure_configured()
            self.assertIsNotNone(profiler)
            assert profiler is not None
            assert profiler.log_path is not None

            def _busy() -> None:
                total = 0
                for i in range(20000):
                    total += i * i
                return None

            with phase_profile.profile_registration_job("unit-job"):
                _busy()

            lines = profiler.log_path.read_text(encoding="utf-8").strip().splitlines()
            messages = [json.loads(line)["message"] for line in lines]
            self.assertIn("cProfile started", messages)
            self.assertIn("cProfile saved", messages)
            self.assertIn("worker:end", messages)
            self.assertTrue(profiler.profile_path is not None and profiler.profile_path.is_file())


if __name__ == "__main__":
    unittest.main()
