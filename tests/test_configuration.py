"""Configuration inference must not require ROM files or mutate settings."""

import copy
from pathlib import Path

import pytest
import ndicapi_sim as ndi


@pytest.mark.parametrize("original, options, descriptions", [
    ({}, {}, ("simulator tool 1", "simulator tool 2")),
    ({"romfiles": ["a.rom", "b.rom", "c.rom"]}, {},
     ("a.rom", "b.rom", "c.rom")),
    ({"romfiles": []}, {}, ()),
    ({"romfiles": ["a.rom", "b.rom"]}, {"tool count": 1}, ("a.rom",)),
    ({"romfiles": ["a.rom"]}, {"tool count": 3},
     ("a.rom", "simulator tool 2", "simulator tool 3")),
    ({"romfiles": ["a.rom"]}, {"tool count": 0}, ()),
    ({"romfiles": (Path("not-present.rom"),)}, {}, (Path("not-present.rom"),)),
])
def test_inference(original, options, descriptions):
    """Explicit overrides, inferred entries and defaults have clear priority."""
    original_before, options_before = copy.deepcopy(original), copy.deepcopy(options)
    device = ndi.open_simulator(options, tracker_configuration=original)
    assert device.tool_count == len(descriptions)
    assert tuple(ndi.get_tool_description(device, index + 1)
                 for index in range(device.tool_count)) == descriptions
    assert original == original_before
    assert options == options_before


@pytest.mark.parametrize("count", [-1, 256, True, 1.5, "2", None])
def test_invalid_count(count):
    """Malformed counts do not become surprising tool layouts."""
    with pytest.raises(ValueError, match="tool count"):
        ndi.open_simulator({"tool count": count})


@pytest.mark.parametrize("options", [[], "circular", 1])
def test_invalid_options(options):
    """Simulation options must be a mapping."""
    with pytest.raises(TypeError, match="simulation"):
        ndi.open_simulator(options)


@pytest.mark.parametrize("romfiles", [None, "file.rom", 42])
def test_invalid_rom_list(romfiles):
    """A path string is not a list of tools."""
    with pytest.raises(TypeError, match="romfiles"):
        ndi.open_simulator(tracker_configuration={"romfiles": romfiles})


def test_invalid_tracker_configuration():
    """Direct API callers must also pass original settings as a mapping."""
    with pytest.raises(TypeError, match="Tracker configuration"):
        ndi.open_simulator(tracker_configuration=[])


@pytest.mark.parametrize("key, value", [
    ("period", 0), ("period", float("inf")), ("period", True),
    ("visibility interval", -1), ("visibility interval", float("nan")),
    ("seed", True), ("seed", "42"), ("mode", "unknown"),
    ("typo", 1),
])
def test_invalid_source_options(key, value):
    """Unsupported or invalid source settings fail at construction."""
    with pytest.raises(ValueError):
        ndi.open_simulator({key: value})


def test_playback_reserved():
    """A reserved source never falls back to synthetic circular motion."""
    with pytest.raises(NotImplementedError, match="Playback"):
        ndi.open_simulator({"mode": "playback", "file": "missing.ndirec"})
