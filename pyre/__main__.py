"""
Created on Sep 12, 2013

@author: u0490822
"""
import multiprocessing
import os
import sys

_SMOKE_POOL_WORKERS = 2
_SMOKE_POOL_TASKS = 8
_SMOKE_POOL_TIMEOUT_S = 60.0


def _ensure_stdio_streams() -> None:
    """Attach devnull streams when PyInstaller windowed boot leaves stdio as None."""
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


_ensure_stdio_streams()

from pyre.frozen_paths import configure_frozen_environment


def _run_smoke_test() -> int:
    """Verify frozen/runtime imports without starting the GUI."""
    configure_frozen_environment()

    import nornir_imageregistration  # noqa: F401
    import nornir_pools  # noqa: F401
    import nornir_shared  # noqa: F401
    import pyre  # noqa: F401

    print("SMOKE_OK")
    return _run_pool_smoke_test()


def _run_pool_smoke_test() -> int:
    """Run tasks on a real process pool and fail if its workers keep dying.

    A worker that cannot start exits and is respawned by the pool, so its tasks never
    finish, or more distinct worker PIDs show up than the pool has slots.
    """
    import nornir_pools
    from nornir_pools.multiprocessthreadpool import MultiprocessThreadPool

    pool = nornir_pools.GetMultithreadingPool("Pyre smoke test pool", num_threads=_SMOKE_POOL_WORKERS)
    if not isinstance(pool, MultiprocessThreadPool):
        print(f"POOL_FAIL: expected a MultiprocessThreadPool, got {type(pool).__name__}")
        return 1

    tasks = [pool.add_task(f"smoke test pid {i}", os.getpid) for i in range(_SMOKE_POOL_TASKS)]
    try:
        pool.wait_completion(timeout=_SMOKE_POOL_TIMEOUT_S)
    except TimeoutError:
        pool.terminate_workers()
        print(f"POOL_FAIL: {len(tasks)} tasks did not finish in {_SMOKE_POOL_TIMEOUT_S:.0f} s; "
              "pool workers are not starting")
        return 1

    worker_pids = {task.wait_return() for task in tasks}
    pool.shutdown()
    if len(worker_pids) > _SMOKE_POOL_WORKERS:
        print(f"POOL_FAIL: {len(worker_pids)} worker PIDs for {_SMOKE_POOL_WORKERS} slots; "
              "workers were respawned")
        return 1

    print(f"POOL_OK workers={len(worker_pids)} tasks={len(tasks)}")
    return 0


def main():
    # A frozen pool worker starts as ``pyre.exe --multiprocessing-fork``. Without this it
    # re-runs Pyre, fails argument parsing and exits, and the pool respawns it forever.
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke-test":
        raise SystemExit(_run_smoke_test())

    import pyre.launcher as launcher

    launcher.Run()


if __name__ == '__main__':
    main()
