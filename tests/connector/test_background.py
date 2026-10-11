"""The suite's guards against background work and a sleeping machine.

Neither is a spec behavior; both keep the suite honest. ``wait_idle`` lets the
connector fixtures wait for the materials pool, so no job outlives its test, and
``slept_seconds`` reports a laptop that idle-slept mid-run, which otherwise
looks exactly like a hang.
"""

from __future__ import annotations

import threading

from src.connector.materials import pipeline
from tests.conftest import slept_seconds


def test_wait_idle_counts_a_running_job_until_it_finishes():
    release = threading.Event()
    future = pipeline.run_in_background(release.wait, 10)
    try:
        assert pipeline.wait_idle(0.05) == 1
    finally:
        release.set()
    assert pipeline.wait_idle(5) == 0
    assert future.done()


def test_slept_seconds_is_wall_time_the_monotonic_clock_did_not_see():
    assert slept_seconds((1000.0, 50.0), (1100.0, 90.0)) == 60.0  # 100 s wall, 40 s awake
    assert slept_seconds((1000.0, 50.0), (1040.0, 90.0)) == 0.0
    assert slept_seconds((1000.0, 50.0), (1039.5, 90.0)) == 0.0  # a wall clock stepped back
