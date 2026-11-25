"""Limites del proceso hijo Prefect que ejecuta el master diario."""

from __future__ import annotations

import os
import signal
from contextlib import contextmanager
from threading import Event, Timer
from typing import Iterator


POSIX_SIGNALS_AVAILABLE = os.name == "posix"


@contextmanager
def hard_process_deadline(
    timeout_seconds: int = 9_900,
    grace_seconds: int = 30,
) -> Iterator[None]:
    """Termina el proceso del flow si Prefect no logro interrumpir una tarea.

    En process workers el flow corre en su propio proceso. SIGTERM permite la
    salida normal; SIGKILL garantiza el cierre de sockets y locks restantes.
    """
    if timeout_seconds <= 0 or grace_seconds <= 0:
        raise ValueError("Los limites del proceso deben ser positivos")
    if not POSIX_SIGNALS_AVAILABLE:
        yield
        return

    pid = os.getpid()
    expired = Event()
    force_timer: Timer | None = None

    def terminate() -> None:
        nonlocal force_timer
        expired.set()
        force_timer = Timer(grace_seconds, os.kill, args=(pid, signal.SIGKILL))
        force_timer.daemon = True
        force_timer.start()
        os.kill(pid, signal.SIGTERM)

    deadline = Timer(timeout_seconds, terminate)
    deadline.daemon = True
    deadline.start()
    try:
        yield
    finally:
        deadline.cancel()
        if not expired.is_set() and force_timer is not None:
            force_timer.cancel()
