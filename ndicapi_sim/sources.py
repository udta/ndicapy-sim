"""Pose generation, independent of the ndicapy compatibility functions."""

import math
import random
from collections.abc import Mapping


def _positive_number(configuration, key, default, allow_zero=False):
    value = configuration.get(key, default)
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or (value <= 0 if not allow_zero else value < 0)):
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"'{key}' must be a finite {qualifier} number")
    return float(value)


class CircularSource:
    """The attachment's circular trajectory, orientation and visibility pattern.

    Distances are millimetres; angles are radians. Quality phases retain the
    attachment's convention of an offset in seconds, sampled from [0, 2*pi].
    A zero visibility interval makes tools permanently visible.
    """

    def __init__(self, configuration, tool_count):
        self.period = _positive_number(configuration, "period", 10.0)
        self.visibility_interval = _positive_number(
            configuration, "visibility interval", 4.0, allow_zero=True)
        seed = configuration.get("seed")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise ValueError("'seed' must be an integer or None")
        self._random = random.Random(seed)
        self._tool_count = tool_count
        self._position_phases = []
        self._quality_phases = []

    def start(self):
        """Start a new run with independent phases for each tool."""
        self._quality_phases = [self._random.uniform(0, 2 * math.pi)
                                for _ in range(self._tool_count)]
        self._position_phases = [self._random.uniform(0, 2 * math.pi)
                                 for _ in range(self._tool_count)]

    def sample(self, elapsed, tool_index):  # pylint: disable=too-many-locals
        """Return (qw, qx, qy, qz, x, y, z, error), or 'MISSING'."""
        if (self.visibility_interval
                and int(elapsed / self.visibility_interval) % 2):
            return "MISSING"

        angle = ((elapsed % self.period) / self.period * 2 * math.pi
                 + self._position_phases[tool_index])
        radius = 100.0 + tool_index * 50.0
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        z = -1200.0 + 50.0 * math.sin(2 * angle)

        # Rz(yaw) @ Ry(pitch) @ Rx(roll), as in the attached implementation.
        roll, pitch, yaw = angle * 0.5, math.sin(angle) * 0.3, angle
        cr, sr = math.cos(roll / 2), math.sin(roll / 2)
        cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
        cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
        quaternion = (cr * cp * cy + sr * sp * sy,
                      sr * cp * cy - cr * sp * sy,
                      cr * sp * cy + sr * cp * sy,
                      cr * cp * sy - sr * sp * cy)
        quality_time = elapsed + self._quality_phases[tool_index]
        error = 0.105 + 0.095 * math.sin(2 * math.pi * quality_time / 5.0)
        return quaternion + (x, y, z, max(0.01, min(0.2, error)))


def create_source(configuration):
    """Select a pose source; playback is an explicit future extension point."""
    if not isinstance(configuration, Mapping):
        raise TypeError("'simulation' must be a mapping")
    mode = configuration.get("mode", "circular")
    if mode == "playback":
        raise NotImplementedError("Playback is reserved but not implemented yet")
    if mode != "circular":
        raise ValueError("Simulation mode must be 'circular' or 'playback'")
    unknown = set(configuration) - {
        "mode", "tool count", "seed", "period", "visibility interval"}
    if unknown:
        raise ValueError(f"Unknown circular simulation options: {sorted(unknown)}")
    count = configuration.get("tool count", 2)
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 255:
        raise ValueError("'tool count' must be an integer between 0 and 255")
    return CircularSource(configuration, count), count
