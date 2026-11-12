"""Deterministic geometry and visibility checks without wall-clock sleeps."""

import math
import random

import pytest
from ndicapi_sim.sources import CircularSource


def test_reference_poses(monkeypatch):
    """Zero phases give analytically known positions and rotations."""
    monkeypatch.setattr(random.Random, "uniform", lambda *_args: 0.0)
    source = CircularSource({"visibility interval": 0}, 2)
    source.start()
    assert source.sample(0, 0) == pytest.approx((1, 0, 0, 0, 100, 0, -1200, .105))
    assert source.sample(0, 1)[4:7] == pytest.approx((150, 0, -1200))
    root_half = math.sqrt(.5)
    assert source.sample(5, 0) == pytest.approx(
        (0, 0, root_half, root_half, -100, 0, -1200, .105))


@pytest.mark.parametrize("elapsed, missing", [
    (0, False), (3.999, False), (4, True), (7.999, True),
    (8, False), (20, True), (24, False),
])
def test_visibility_intervals(elapsed, missing):
    """Crossing or skipping boundaries respects elapsed time for all tools."""
    source = CircularSource({}, 2)
    source.start()
    for index in range(2):
        assert (source.sample(elapsed, index) == "MISSING") is missing


def test_geometry_and_reproducibility():
    """Seeded tools are independent, unit rotations stay valid and bounded."""
    global_state = random.getstate()
    first = CircularSource({"seed": 42, "visibility interval": 0}, 3)
    second = CircularSource({"seed": 42, "visibility interval": 0}, 3)
    for _ in range(2):
        first.start()
        second.start()
        for elapsed in (0, 1, 2.5, 9.99, 10, 101):
            for index in range(3):
                pose = first.sample(elapsed, index)
                assert pose == second.sample(elapsed, index)
                assert sum(value * value for value in pose[:4]) == pytest.approx(1)
                assert math.hypot(*pose[4:6]) == pytest.approx(100 + 50 * index)
                assert -1250 <= pose[6] <= -1150
                assert .01 <= pose[7] <= .2
        assert first.sample(1, 0) != first.sample(1, 1)
    assert random.getstate() == global_state


def test_custom_period_and_disabled_visibility():
    """Orbit period is configurable independently of the quality cycle."""
    source = CircularSource({"period": 2, "visibility interval": 0}, 1)
    source.start()
    assert source.sample(0, 0)[:7] == pytest.approx(source.sample(2, 0)[:7])
    assert isinstance(source.sample(4, 0), tuple)
