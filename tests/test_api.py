"""Exercise the ndicapy subset that the tracker uses."""

import pytest
import ndicapi_sim as ndi


def ready_device(count=2):
    """Discover, initialise and enable tools using the public command API."""
    device = ndi.open_simulator({"tool count": count, "seed": 42})
    ndi.ndiCommand(device, "INIT:")
    ndi.ndiCommand(device, "PHSR:02")
    assert ndi.ndiGetPHSRNumberOfHandles(device) == count
    for index in range(count):
        handle = ndi.ndiGetPHSRHandle(device, index)
        ndi.ndiCommand(device, f"PINIT:{handle:02x}")
        ndi.ndiCommand(device, f"PENA:{handle:02x}D")
    ndi.ndiCommand(device, "PHSR:02")
    assert ndi.ndiGetPHSRNumberOfHandles(device) == 0
    return device


def test_snapshot_and_restart(monkeypatch):
    """Capture advances frames; getters read a stable cross-tool snapshot."""
    now = [100.0]
    monkeypatch.setattr(ndi, "monotonic", lambda: now[0])
    device = ready_device()
    ndi.ndiCommand(device, "TSTART:")
    ndi.ndiCommand(device, "BX:0801")
    pose = ndi.ndiGetBXTransform(device, b"\x01")
    now[0] = 102.0
    assert ndi.ndiGetBXTransform(device, 1) == pose
    assert ndi.ndiGetBXFrame(device, 1) == ndi.ndiGetBXFrame(device, b"\x02") == 1
    ndi.ndiCommand(device, "TX:0801")
    assert ndi.ndiGetTXFrame(device, 2) == 2
    assert ndi.ndiGetTXTransform(device, 1) != pose
    now[0] = 104.0
    ndi.ndiCommand(device, "BX:0801")
    assert ndi.ndiGetBXTransform(device, 1) == "MISSING"
    ndi.ndiCommand(device, "TSTOP:")
    with pytest.raises(ValueError, match="started"):
        ndi.ndiCommand(device, "BX:0801")
    ndi.ndiCommand(device, "TSTART:")
    ndi.ndiCommand(device, "BX:0801")
    assert ndi.ndiGetBXFrame(device, 1) == 1
    assert isinstance(ndi.ndiGetBXTransform(device, 1), tuple)
    ndi.ndiClose(device)
    with pytest.raises(ValueError, match="closed"):
        ndi.ndiCommand(device, "TSTART:")


def test_discovery_and_disabled_tool():
    """Port discovery reports the current initialisation and enable state."""
    device = ndi.ndiOpen("virtual")
    ndi.ndiCommand(device, "PHSR:01")
    assert ndi.ndiGetPHSRNumberOfHandles(device) == 0
    with pytest.raises(ValueError, match="initialised"):
        ndi.ndiCommand(device, "PENA:01D")
    ndi.ndiCommand(device, "PINIT:01")
    ndi.ndiCommand(device, "PHSR:03")
    assert ndi.ndiGetPHSRHandle(device, 0) == 1
    ndi.ndiCommand(device, "PENA:01D")
    ndi.ndiCommand(device, "TSTART:")
    with pytest.raises(ValueError, match="already tracking"):
        ndi.ndiCommand(device, "TSTART:")
    with pytest.raises(ValueError, match="Capture"):
        ndi.ndiGetBXTransform(device, 1)
    ndi.ndiCommand(device, "BX:0801")
    assert ndi.ndiGetBXTransform(device, 2) == "DISABLED"
    assert ndi.ndiGetError(device) == ndi.NDI_OKAY
    assert ndi.ndiErrorString(ndi.NDI_OKAY) == "No error"
    assert "Unknown" in ndi.ndiErrorString(99)
    assert "ndicapi_sim" in ndi.ndiVER(device, 0)


@pytest.mark.parametrize("handle", [0, 3, True, "1", b"", b"01", None])
def test_invalid_handles(handle):
    """Invalid handles are errors rather than fabricated observations."""
    with pytest.raises(ValueError):
        ndi.ndiGetBXFrame(ready_device(), handle)


@pytest.mark.parametrize("command", ["UNKNOWN:", "PHSR:99"])
def test_unsupported_commands(command):
    """The supported API subset is explicit."""
    with pytest.raises(NotImplementedError):
        ndi.ndiCommand(ready_device(), command)


def test_device_isolation_and_empty_capture(monkeypatch):
    """Independent devices do not share counters, clocks or tool state."""
    monkeypatch.setattr(ndi, "monotonic", lambda: 0.0)
    first, second, empty = ready_device(), ready_device(), ready_device(0)
    for device in (first, second, empty):
        ndi.ndiCommand(device, "TSTART:")
    ndi.ndiCommand(first, "BX:0801")
    assert ndi.ndiGetBXFrame(second, 1) == 0
    ndi.ndiCommand(second, "BX:0801")
    assert ndi.ndiGetBXTransform(first, 1) == ndi.ndiGetBXTransform(second, 1)
    ndi.ndiClose(first)
    ndi.ndiCommand(second, "BX:0801")
    assert ndi.ndiGetBXFrame(second, 1) == 2
    ndi.ndiCommand(empty, "BX:0801")
    assert empty.frame_number == 1
    assert not empty.transforms
    ndi.ndiCommand(second, "INIT:")
    assert not second.enabled
    assert second.frame_number == 0
    with pytest.raises(ValueError, match="invalid"):
        ndi.ndiGetError(None)
