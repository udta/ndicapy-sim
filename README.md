# ndicapi-sim

Installable, standard-library-only synthetic data provider. The distribution is
`ndicapi-sim` (pip also accepts `ndicapi_sim`); the import is `ndicapi_sim`.
It implements the small ndicapy subset used by scikit-surgerynditracker's
`simulator` path, not a complete hardware or protocol emulator.

The simulator is optional: a base tracker installation and its native/dummy
tests work without this package. Selecting simulator mode without installing it
raises an installation hint. Once released, the tracker extra can install it via
`python -m pip install 'scikit-surgerynditracker[simulator]'`.

## Installation and use

With both repositories checked out next to each other:

```bash
python -m pip install ./ndicapy-sim
python -m pip install ./scikit-surgerynditracker
```

```python
from sksurgerynditracker.nditracker import NDITracker

tracker = NDITracker({
    "tracker type": "simulator",
    "romfiles": ["pointer.rom", "reference.rom"],
    "simulation": {},
    "use quaternions": False,
})
try:
    tracker.start_tracking()
    handles, timestamps, frames, poses, errors = tracker.get_frame()
finally:
    tracker.close()
```

No ROM files, serial devices, network endpoints or ping are needed. Existing
tracker methods, matrix/quaternion output and smoothing remain unchanged. Tool
handles start at 1; tool descriptions preserve the supplied ROM paths, with
generated names such as `simulator tool 1` when no path is available.
The simulator package itself does not import ndicapy; the existing
tracker package still installs/imports its native ndicapi dependency.

## Configuration

Simulation overrides live in the nested `simulation` dictionary. An omitted or
empty dictionary uses information inferred from the original tracker settings,
then simulator defaults. Unknown circular options are rejected. Original
top-level hardware settings and other application fields remain accepted.

| Option | Default | Meaning |
| --- | --- | --- |
| `mode` | `"circular"` | `"circular"` or reserved `"playback"` |
| `tool count` | Length of `romfiles`, otherwise `2` | Integer from 0 to 255 |
| `seed` | `None` | Optional integer for reproducible initial phases |
| `period` | `10.0` | Positive orbit period in seconds |
| `visibility interval` | `4.0` | Seconds between collective visibility changes; `0` means always visible |

To switch an existing Polaris, Vega or Aurora configuration, change only
`"tracker type"` to `"simulator"`. Adding `"simulation": {}` is optional:

```python
offline_settings = dict(existing_settings, **{"tracker type": "simulator"})
tracker = NDITracker(offline_settings)
```

The inference rules are:

* **Polaris/Vega:** a `romfiles` list determines the number of tools and their
  descriptions in the original order. The paths are retained without opening or
  checking the files. `romfiles: []` explicitly means zero tools.
* **Aurora or other configurations without `romfiles`:** hardware-discovered
  tool information is unavailable offline, so generate two tools by default.
  Set `simulation: {"tool count": 3}` to request a different number.
* **Explicit overrides:** `simulation["tool count"]` takes priority over the ROM
  list, including an explicit zero. Reducing the count keeps the first N ROM
  descriptions; increasing it appends generated names for additional tools.
* **Common settings:** top-level `use quaternions` and `smoothing buffer` still
  go through the existing tracker implementation.
* **Hardware settings:** serial ports, port-probing limits, IP addresses and
  network ports are ignored during simulation. Device model and real port
  handles are not inferred. `dummy` is unchanged.

Input dictionaries and ROM lists are not modified. `romfiles` accepts a list or
tuple; a string or `None` is rejected rather than interpreted as tool entries.

For zero-based tool index `i`, radius is `100 + 50*i` mm. With a random per-tool
phase, `angle = 2*pi*(elapsed % period)/period + phase`:

* `x = radius*cos(angle)`, `y = radius*sin(angle)`.
* `z = -1200 + 50*sin(2*angle)` mm.
* Orientation is `Rz(angle) @ Ry(0.3*sin(angle)) @ Rx(0.5*angle)`.
* Error/quality is clamped to `[0.01, 0.2]`, with a five-second sinusoidal
  cycle and independent per-tool phase offsets.

These match the supplied circular-motion design, including its angle wrapping
at the orbit boundary. All tools start visible, become missing at four seconds,
and visible again at eight seconds. Visibility uses elapsed intervals, so it
remains correct even if no frames are requested during a transition. Missing
tools return `"MISSING"` at the ndicapy boundary; the tracker converts this to
NaN pose components and quality using its existing path. A matrix's homogeneous
bottom row remains `[0, 0, 0, 1]`. Existing smoothing may retain valid samples
while a tool is missing; use the default buffer size of 1 for direct visibility.

Time is monotonic elapsed wall time since `TSTART`, without sleeping or enforcing
a capture rate. Each BX/TX command increments the frame counter once, regardless
of polling frequency. Every tool in that capture shares the counter and capture
time; repeated getters return the same snapshot. Tracker timestamps remain the
current host timestamps. A seed reproduces phases for the same start sequence,
not wall-clock polling times. Restarting resets elapsed time and frame count and
generates new phases, as in the attachment. Devices do not share random state.

## Direct API and future playback

`open_simulator(options, tracker_configuration=original_settings)` is the
configuration entry point. The first argument remains the nested simulation
options for direct users; the optional keyword supplies original tracker
settings for inference. `get_tool_description(device, handle)` exposes the
resolved description. These are simulator-specific helpers, not native ndicapy
functions. `ndiOpen(name)` opens a default device, ignoring the virtual port
name. Supported ndicapy functions:
`ndiClose`, `ndiCommand`, `ndiVER`, `ndiGetError`, `ndiErrorString`,
`ndiGetPHSRNumberOfHandles`, `ndiGetPHSRHandle`, `ndiGetBXFrame`,
`ndiGetBXTransform`, and the equivalent TX getters. Handles are integers or
single raw bytes, as passed by the tracker. Transforms are immutable tuples
`(qw, qx, qy, qz, x, y, z, error)`, or `"MISSING"`/`"DISABLED"`.

Commands supported: `INIT:`, `PHSR:01/02/03`, `PINIT:<hex handle>`,
`PENA:<hex handle>D`, `TSTART:`, `TSTOP:`, `BX:0801`, `TX:0801`.
Unsupported commands raise `NotImplementedError`; invalid state/handles raise
`ValueError`. This subset deliberately excludes ROM upload, port allocation,
serial settings and network transport.

Playback is reserved explicitly:

```python
NDITracker({
    "tracker type": "simulator",
    "simulation": {"mode": "playback", "file": "session.ndirec"},
})
```

This currently raises `NotImplementedError` at construction. It never silently
falls back to circular data. Later, `sources.create_source()` can return a
playback source implementing `start()` and `sample(elapsed, tool_index)` with
the same tuple/status contract. File format, recording, seeking and end-of-file
policies are intentionally unimplemented; tracker changes are not required to
select that source. A future playback implementation can extend the source
contract if those controls need it.

## Development checks

```bash
python -m pip install '.[test,lint]'
python -m pytest -q
python -m pylint --reports=n --score=n ndicapi_sim tests
```

The tests use controlled clocks and seeded randomness, with no sleeps, hardware,
ROM file access or tracker-package dependency. CI checks Linux and Windows on
Python 3.11 through 3.15, matching the tracker CI matrix. Tracker integration
belongs in the tracker repository.
