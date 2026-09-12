"""Simple rate limiter for outbound AkShare calls.

Enforces a minimum interval between requests plus small random jitter to avoid
hammering upstream sources (reduces IP-block / rate-limit risk).
"""
from __future__ import annotations

import random
import threading
import time


class Throttle:
    def __init__(self, min_interval: float = 0.4, jitter: float = 0.15) -> None:
        self.min_interval = max(0.0, min_interval)
        self.jitter = max(0.0, jitter)
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            delay = self.min_interval - elapsed
            if delay > 0:
                time.sleep(delay + random.uniform(0, self.jitter))
            self._last = time.monotonic()


# Shared default throttle (configured by pipeline from settings).
default_throttle = Throttle()


def configure(min_interval: float, jitter: float = 0.15) -> None:
    default_throttle.min_interval = max(0.0, min_interval)
    default_throttle.jitter = max(0.0, jitter)
