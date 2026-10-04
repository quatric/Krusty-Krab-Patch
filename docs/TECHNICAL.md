# How the patch works

The game wraps the Wii Remote SDK (KPAD) in its own device layer,
`bReadPhysicalInputDevices()`, which runs once per frame: `KPADRead` for the four
channels, `WPADProbe` per channel to learn what is plugged in, then `bPadCopy` to
turn the newest sample into the pad records the rest of the engine reads. It
understands a Wii Remote with or without a Nunchuk and nothing else.

Two hooks sit inside that function, so everything downstream (button channels,
the stick, the motion detectors that read the accelerometer history) is unchanged
and sees a Wii Remote with a Nunchuk:

| Hook | Where | What it does |
| --- | --- | --- |
| KPAD | after `KPADRead`, before the sample count is stored | a Classic Controller's samples are rewritten as Nunchuk samples; with no Wii Remote and a GameCube pad on the same port, three fresh samples are written |
| PROBE | after `WPADProbe` | a Classic Controller is reported as a Nunchuk; a pad on a channel with no Wii Remote makes the probe succeed with a Nunchuk |

The game links the SI library but not PAD, so nothing polls the pads:
`poll_all()` in `src/pad/kkpad.c` drives the Serial Interface's auto-poller
itself. The motion gestures the game asks for (swinging the remote, shaking the
Nunchuk, thrusting down) are played back as accelerometer samples when their
button goes down.

Each hook is a branch to a small trampoline in the injected section at
`0x80001820`; the hook's variables live at `0x80005C00`, in zero padding of the
retail DOL. Addresses are found per release by `tools/anchors.py`, which checks
the bytes at every site before anything is patched. `tools/gen_prebuilt.py`
compiles `src/pad/` with devkitPPC into `tools/prebuilt/`, and `tools/patcher.py`
applies the result.
