"""Small ndicapy-compatible subset for scikit-surgerynditracker.

This is a synthetic data provider, not a hardware or wire-protocol emulator.
Each opened device owns its clock, random generator, tools and cached frame.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from time import monotonic

from .sources import create_source

# Public names intentionally match the native ndicapy API.
# pylint: disable=invalid-name

NDI_OKAY = 0


@dataclass
# One record owns the complete state of an independent virtual device.
# pylint: disable-next=too-many-instance-attributes
class SimulatorDevice:
    """Opaque handle returned to consumers of the ndicapy-style API."""

    source: object
    tool_count: int
    tool_descriptions: tuple
    closed: bool = False
    started_at: object = None
    frame_number: int = 0
    initialised: set = field(default_factory=set)
    enabled: set = field(default_factory=set)
    queried_handles: tuple = ()
    transforms: dict = field(default_factory=dict)


def open_simulator(configuration=None, *, tracker_configuration=None):
    """Open using simulation overrides and optional original tracker settings.

    Explicit simulation options take priority over inferred tracker settings,
    followed by simulator defaults. No tracker configuration is mutated and no
    ROM files or hardware endpoints are accessed.
    """
    configuration = {} if configuration is None else configuration
    tracker_configuration = ({} if tracker_configuration is None
                             else tracker_configuration)
    if not isinstance(configuration, Mapping):
        raise TypeError("'simulation' must be a mapping")
    if not isinstance(tracker_configuration, Mapping):
        raise TypeError("Tracker configuration must be a mapping")
    romfiles = tracker_configuration.get("romfiles", ())
    if not isinstance(romfiles, (list, tuple)):
        raise TypeError("'romfiles' must be a list or tuple")

    options = dict(configuration)
    options.setdefault("tool count", len(romfiles)
                       if "romfiles" in tracker_configuration else 2)
    source, count = create_source(options)
    descriptions = tuple(romfiles[:count]) + tuple(
        f"simulator tool {index + 1}" for index in range(len(romfiles), count))
    return SimulatorDevice(source, count, descriptions)


def ndiOpen(name):  # pylint: disable=unused-argument
    """Open a default simulated device; the virtual port name is ignored."""
    return open_simulator()


def _check_device(device):
    if not isinstance(device, SimulatorDevice) or device.closed:
        raise ValueError("Simulator device is invalid or closed")


def _handle(device, handle):
    _check_device(device)
    if isinstance(handle, bytes):
        if len(handle) != 1:
            raise ValueError("Expected a single-byte tool handle")
        handle = handle[0]
    if (isinstance(handle, bool) or not isinstance(handle, int)
            or not 1 <= handle <= device.tool_count):
        raise ValueError("Unknown simulator tool handle")
    return handle


def get_tool_description(device, handle):
    """Return the original ROM description or a generated simulator name."""
    handle = _handle(device, handle)
    return device.tool_descriptions[handle - 1]


def ndiClose(device):
    """Close the virtual device without touching hardware."""
    _check_device(device)
    device.started_at = None
    device.transforms.clear()
    device.closed = True


def ndiCommand(device, command):  # pylint: disable=too-many-branches
    """Handle only the commands needed by the tracker simulator path.

    BX/TX captures one snapshot. Getters never advance time or frame numbers.
    Commands outside this documented subset fail explicitly.
    """
    _check_device(device)
    if command == "INIT:":
        device.started_at = None
        device.frame_number = 0
        device.initialised.clear()
        device.enabled.clear()
        device.queried_handles = ()
        device.transforms.clear()
    elif command.startswith("PHSR:"):
        mode = command[5:]
        handles = range(1, device.tool_count + 1)
        if mode == "01":
            device.queried_handles = ()
        elif mode == "02":
            device.queried_handles = tuple(
                handle for handle in handles if handle not in device.initialised)
        elif mode == "03":
            device.queried_handles = tuple(
                handle for handle in handles
                if handle in device.initialised and handle not in device.enabled)
        else:
            raise NotImplementedError(f"Unsupported simulator command: {command}")
    elif command.startswith("PINIT:"):
        device.initialised.add(_handle(device, int(command[6:], 16)))
    elif command.startswith("PENA:") and command.endswith("D"):
        handle = _handle(device, int(command[5:-1], 16))
        if handle not in device.initialised:
            raise ValueError("Tool must be initialised before enabling")
        device.enabled.add(handle)
    elif command == "TSTART:":
        if device.started_at is not None:
            raise ValueError("Simulator is already tracking")
        device.source.start()
        device.started_at = monotonic()
        device.frame_number = 0
        device.transforms.clear()
    elif command == "TSTOP:":
        device.started_at = None
    elif command in ("BX:0801", "TX:0801"):
        if device.started_at is None:
            raise ValueError("Simulator must be started before capturing a frame")
        elapsed = monotonic() - device.started_at
        device.transforms = {
            handle: device.source.sample(elapsed, handle - 1)
            if handle in device.enabled else "DISABLED"
            for handle in range(1, device.tool_count + 1)}
        device.frame_number += 1
    else:
        raise NotImplementedError(f"Unsupported simulator command: {command}")
    return "OKAY"


def ndiGetPHSRNumberOfHandles(device):
    """Read the most recent PHSR result."""
    _check_device(device)
    return len(device.queried_handles)


def ndiGetPHSRHandle(device, index):
    """Return a tool handle from the most recent PHSR result."""
    _check_device(device)
    return device.queried_handles[index]


def ndiGetBXFrame(device, handle):
    """Return the capture counter, shared by all tools in a snapshot."""
    _handle(device, handle)
    return device.frame_number


def ndiGetBXTransform(device, handle):
    """Return a cached quaternion/translation/error tuple or a status string."""
    handle = _handle(device, handle)
    if not device.transforms:
        raise ValueError("Capture a frame before reading transforms")
    return device.transforms[handle]


ndiGetTXFrame = ndiGetBXFrame
ndiGetTXTransform = ndiGetBXTransform


def ndiVER(device, mode):  # pylint: disable=unused-argument
    """Identify the synthetic provider, without pretending to be real firmware."""
    _check_device(device)
    return "Freeze Tag: ndicapi_sim 0.1.0\n"


def ndiGetError(device):
    """Supported calls succeed; misuse raises Python exceptions immediately."""
    _check_device(device)
    return NDI_OKAY


def ndiErrorString(error):
    """Return a diagnostic string for the supported success code."""
    return "No error" if error == NDI_OKAY else f"Unknown error: {error}"
