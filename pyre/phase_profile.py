"""Job-scoped PhaseProfiler for expensive Pyre registration work.

Configures NDJSON + ``.pstats`` under ``NORNIR_LOG_ROOT`` when available.
cProfile runs only inside :func:`profile_registration_job`, not during ordinary
Qt event processing.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from nornir_shared.profiling import (
    PhaseProfiler,
    configure_phase_profiler,
    get_phase_profiler,
    log_event,
    phase_timer,
    start_cprofile,
    stop_cprofile,
)

_logger = logging.getLogger(__name__)
_FALSEY = frozenset({"0", "false", "no", "off"})
_JOBS_ENV = "NORNIR_PHASE_PROFILE_JOBS"


def jobs_profiling_enabled() -> bool:
    """Return True unless ``NORNIR_PHASE_PROFILE_JOBS`` opts out."""
    flag = os.environ.get(_JOBS_ENV, "1").strip().lower()
    return flag not in _FALSEY


def ensure_configured() -> PhaseProfiler | None:
    """Install a session PhaseProfiler for Pyre when logging roots allow it.

    Defaults NDJSON and ``.pstats`` under the unified session directory when
    ``NORNIR_LOG_ROOT`` is set. Explicit ``NORNIR_PHASE_PROFILE_LOG`` /
    ``NORNIR_PHASE_PROFILE_PSTATS`` still win when present. Returns the active
    profiler, or ``None`` when profiling is disabled or no log destination exists.
    """
    existing = get_phase_profiler()
    if existing is not None:
        return existing
    if not jobs_profiling_enabled():
        return None

    env_log = os.environ.get("NORNIR_PHASE_PROFILE_LOG", "").strip()
    if env_log.lower() in _FALSEY:
        return None

    from nornir_shared import misc as nornir_misc

    session = nornir_misc.GetUnifiedSessionPaths()
    if session is None and not env_log:
        return None

    if env_log:
        profiler = PhaseProfiler()
        if profiler.profile_path is None and session is not None:
            log_dir = Path(session[0])
            session_id = nornir_misc._get_or_create_session_id()
            profiler = PhaseProfiler(
                log_path=profiler.log_path,
                profile_path=log_dir / f"nornir-phase-profile-{session_id}.pstats",
            )
        return configure_phase_profiler(profiler)

    assert session is not None
    log_dir = Path(session[0])
    session_id = nornir_misc._get_or_create_session_id()
    profiler = PhaseProfiler(
        log_path=log_dir / f"nornir-phase-profile-{session_id}.ndjson",
        profile_path=log_dir / f"nornir-phase-profile-{session_id}.pstats",
    )
    configured = configure_phase_profiler(profiler)
    _logger.info(
        "Pyre phase profiling ready: ndjson=%s pstats=%s "
        "(cProfile only during registration jobs)",
        configured.log_path,
        configured.profile_path,
    )
    return configured


@contextmanager
def profile_registration_job(title: str) -> Iterator[None]:
    """Profile one registration-job worker thread (cProfile + wall phase + refine buckets).

    No-op when job profiling is disabled or no profiler can be configured.
    Qt UI message handling stays outside this context so idle event loops are
    not sampled.
    """
    if not jobs_profiling_enabled():
        yield
        return

    profiler = ensure_configured()
    if profiler is None:
        yield
        return

    tag = title.strip() or "registration-job"
    refine_timer = None
    try:
        from nornir_imageregistration.refine_shared.phase_timer import get_phase_timer

        refine_timer = get_phase_timer()
        # Force detailed buckets for this job even when NORNIR_REFINE_PHASE_TIMING
        # is unset; restore to config-following afterward.
        refine_timer.enabled = True
        refine_timer.reset()
    except Exception:
        refine_timer = None

    start_cprofile(tag)
    try:
        with phase_timer("job", "pyre.registration_job", "worker", title=tag):
            yield
    finally:
        stop_cprofile(tag)
        if refine_timer is not None:
            totals = refine_timer.snapshot()
            counts = dict(refine_timer.counts)
            if totals:
                log_event(
                    hypothesis_id="job",
                    location="pyre.phase_profile:profile_registration_job",
                    message="refine_phase_totals",
                    data={
                        "title": tag,
                        "totals_s": {k: round(v, 4) for k, v in totals.items()},
                        "counts": counts,
                    },
                )
            refine_timer.enabled = None
