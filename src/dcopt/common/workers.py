"""Worker processes for scripts that run many solves side by side."""
from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor


def solver_threads() -> int:
    """Threads per solve from DCOPT_THREADS (0 or unset: the solver's default). Set it when several
    solves run side by side, so that their time limits mean the same thing on a busy machine.

    Every HiGHS solve of a process has to ask for the same number (see pool), so each call of the
    solver reads it here: the v1 and the v2 heat model may run in one process."""
    return max(0, int(os.environ.get("DCOPT_THREADS", "0") or 0))


def pool(workers: int, initializer=None, initargs: tuple = ()) -> ProcessPoolExecutor:
    """A process pool whose workers start as fresh processes on every platform.

    HiGHS sets up its thread scheduler on the first solve of a process and afterwards refuses to run
    with another number of threads. Where a worker starts as a copy of another process (Linux before
    Python 3.14 copies the parent), it inherits that state, so a worker that asks for one thread
    (DCOPT_THREADS=1) ends every solve with an error and no solution. A fresh process inherits
    nothing. macOS and Windows already start workers this way; the functions and arguments given to
    the pool must be importable and picklable, as they must be there."""
    return ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn"),
                               initializer=initializer, initargs=initargs)
