"""Configure shared phase profiling for Shift+Space registration debug session cc0899."""

from __future__ import annotations

from pathlib import Path

from nornir_shared.profiling import (
    PhaseProfiler,
    configure_phase_profiler,
    log_event,
    next_seq,
    phase_timer,
    start_cprofile,
    stop_cprofile,
)

_MONOREPO_ROOT = Path(__file__).resolve().parents[2]

configure_phase_profiler(
    PhaseProfiler(
        session_id="cc0899",
        log_path=_MONOREPO_ROOT / "debug-cc0899.log",
        profile_path=_MONOREPO_ROOT / "debug-cc0899-register-all.pstats",
        run_id="pre-fix",
    ),
)


def next_alignment_seq() -> int:
    """Return the next alignment sequence number for queue profiling."""
    return next_seq("alignment")


__all__ = [
    "log_event",
    "phase_timer",
    "start_cprofile",
    "stop_cprofile",
    "next_alignment_seq",
]
