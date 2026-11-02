# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Regular use: install straight from GitHub (see README's Installation section)
pip install git+https://github.com/FTEickemeyer/eqe-gui.git

# Development: editable install from a local clone
pip install -e .

# Run the application
eqe
# (or: python -m eqe -- both work)

# Run with simulated instruments (no hardware required)
# Set simulation mode via the Session panel in the GUI, or pass instruments from simulated.py

# Run the automated test suite (stdlib unittest, no pytest dependency)
python -m unittest discover -s tests -v
```

`tests/test_hardware_roles.py` covers the measurement engine, controller, and instrument
role/factory layer against fakes — no real hardware involved. There is no GUI test
suite; when verifying GUI-facing changes, run the app (simulation mode for a first
pass) and manually confirm scan, live, and calibration modes work end-to-end. For
changes touching instrument drivers or timing-sensitive behavior, also verify on real
hardware before considering the change done — always confirm with the user first that
the GUI is closed (COM port conflicts are real and silent).

---

## Architecture

```
GUI (PySide6)               src/eqe/app/
  → Controller              src/eqe/core/controller.py       # threaded orchestration, callback dispatch
    → Measurement Engine    src/eqe/core/measurement_engine.py  # measurement logic, loop strategies
      → Instruments         src/eqe/core/instruments/        # role-based instrument abstraction layer
```

**Core abstraction:** the measurement engine supports interchangeable loop strategies:
- Wavelength loop → scan mode (`perform_measurement`) — EQE vs wavelength
- Time loop → live mode (`perform_live_monitoring`) — EQE vs time

This abstraction must be preserved as new modes are added.

**Instrument abstraction:** the engine never assumes a particular instrument model —
only the `CurrentMeter` / `BiasCurrentMeter` role API (`core/instruments/roles.py`). A
`MeasurementHardware` dataclass bundles `reference_meter`, `test_meter`, and
`monochromator`; `core/instruments/factory.py` builds the right concrete drivers for
whichever `instruments.active_profile` is configured (currently `keithley2000_2400`;
`keithley2600` — the original single-SMU, dual-channel hardware — is kept as a fallback
profile). Switching hardware setups means changing config, not code.

### Key files

| Layer | File | Key class / function |
|---|---|---|
| GUI | `app/mainwindow_qt.py` | `MainWindow` — collects params, dispatches callbacks, updates plots |
| GUI | `app/qt_models.py` | Mode constants, per-mode panel visibility rules (`MODE_SECTIONS`) |
| GUI | `app/state.py` | `AppState` — mutable GUI state |
| GUI | `app/widgets/*.py` | One widget per panel (scan, wavelength setting, bias, calibration, advanced acquisition, live numeric readout, log, session, metadata, MMF dialog + its plot) |
| Controller | `core/controller.py` | `MeasurementController` — threading, stop flag, instrument lifecycle |
| Engine | `core/measurement_engine.py` | `perform_measurement`, `perform_live_monitoring` |
| Params | `core/models.py` | `MeasurementParams` dataclass, mode constants (canonical; GUI re-exports from here) |
| Instruments | `core/instruments/roles.py` | `CurrentMeter`, `BiasCurrentMeter` ABCs, `MeasurementHardware` |
| Instruments | `core/instruments/factory.py` | `build_hardware()`, `initialize_system()` — real or simulated based on config |
| Instruments | `core/instruments/keithley2000.py`, `keithley2400.py` | Current hardware: reference + test-cell/bias meters |
| Instruments | `core/instruments/smu.py` | `SMU` — Keithley 2600 via PyVISA / Lua TSP (do not modify) |
| Instruments | `core/instruments/dual_channel.py` | Adapts a shared-connection dual-channel SMU (2600, or `SimulatedSMU`) to the two-meter role API |
| Instruments | `core/instruments/monochromator.py` | `Cornerstone130` — Oriel via serial |
| Instruments | `core/instruments/simulated.py` | `SimulatedSMU`, `SimulatedMonochromator` |
| Config | `config/load_config.py` | `load_config()` — merges default + local YAML; see Configuration below |
| Analysis | `analysis/calibration.py` | `open_calibration()` — loads the two calibration inputs; `find_latest_incident_beam_file()` |
| Analysis | `analysis/mmf.py` | `compute_mmf()` — spectral Mismatch Factor calculation; `load_eqe_spectrum()`/`load_lamp_spectrum()`, `default_ref_cell_file()`/`default_lamp_spectrum_file()` |
| I/O | `io/data_io.py` | `save_data()`, `build_measurement_header()` — writes result CSV + metadata header; `save_mmf_result()` — writes an MMF result's summary/plot/data files |

### Callback architecture

The measurement engine communicates with the GUI exclusively via callbacks passed into `run_measurement_async`. Never call GUI methods directly from the engine or controller threads.

Callbacks: `on_live_update`, `on_point_acquired`, `on_status`, `on_done`, `on_error`, `on_finished`

`MainWindow` connects these to Qt signals (`point_acquired_signal`, `calibration_point_signal`, the generic `_dispatch_signal`) to safely update widgets from the background thread — see `_dispatch_to_gui`/`_run_on_gui_thread`.

### Configuration

`src/eqe/config/config_default.yaml` (shipped with the package) holds defaults — paths
use `~`, and instrument addresses match this lab's PC, so a fresh install typically
needs no further configuration. Override locally with a `config_local.yaml`; two
locations are checked (first one that exists wins) — see `load_config.get_local_config_path()`:

1. `~/.eqe/config_local.yaml` — recommended, works for any install method.
2. `config_local.yaml` next to `config_default.yaml` inside the installed package —
   only reachable for an editable dev install (`pip install -e .`); kept for backward
   compatibility.

Key fields: `instruments.active_profile` + `instruments.profiles.*`, `calibration.active_incident_beam_file` (optional — auto-selects the latest `incbeamcurr_*.csv` when unset), `calibration.reference_cell_file`, `paths.*`.

### Packaging

This is a real pip package (`pyproject.toml`): dependencies, the `eqe` gui-script
entry point (`eqe.app.gui_qt:main` — `gui-scripts`, not `console_scripts`, so the
installed `eqe.exe` is a windowed launcher and never pops up a console window on
Windows; see `gui_qt.py`'s `_redirect_stdio_for_windowed_launch` for the
stdout/stderr fallback that requires), and non-`.py` runtime resources
(`config/config_default.yaml`, `config/config_local_example.yaml`,
`resources/calibration_defaults/*.csv`, `app/assets/*.ico`) are all declared there. Every
package directory needs an `__init__.py` (even data-only ones like
`resources/calibration_defaults/`) or `setuptools.packages.find` won't discover it and
a real (non-editable) install will silently be missing files — this has bitten this
project before; if you add a new subpackage, add the `__init__.py` in the same
commit. `config_local.yaml` must never end up in a build (it's personal, gitignored) —
it's excluded via `tool.setuptools.exclude-package-data`, not just by omission from
`package-data`, since setuptools can otherwise still pick up a file that's merely
present on disk at build time. `requirements.txt` is a pinned snapshot of a known-good
environment, kept for reference — `pyproject.toml` is authoritative for what actually
gets installed.

---

## Hard Constraints

These rules are non-negotiable. Apply them to every change, in every file.

- **DO NOT modify the SMU / TSP layer** (`core/instruments/smu.py`). This code is stable and hardware-validated.
- **Maintain strict GUI / backend separation.** The backend must remain GUI-agnostic.
- **Reuse the existing callback architecture** for all thread-safe GUI updates.
- **Prefer minimal-diff, incremental changes.** Do not refactor unrelated code.
- **Do not reconnect instruments** unless explicitly asked. The instrument layer is designed
  for persistent connections.
- **Never confuse the two reference cells.** The *internal* reference cell
  ("Siref"/"intSiref" in code/data) is built into the system and read continuously via
  `reference_meter` for every measurement. The *external* Si71889 reference cell is a
  separate, physically swappable cell with its own certified IPCE curve, installed in
  the sample position only during a calibration measurement. Getting these swapped in
  a variable name, comment, saved-file column, or GUI label is a real, previously-made
  mistake with real consequences (a wrong calibration silently corrupts every EQE scan
  that uses it) — when touching calibration code or text, grep for the other spelling
  and double check which cell a given line actually means.
- **Never sign-correct currents in software (no `abs()` on `Current cell (A)` /
  `Current ref (A)` anywhere).** Correctness depends on wiring discipline instead: the
  external Si71889, the internal reference cell, and any DUT's test-cell reading must
  all be wired to the same polarity convention (positive), by physical convention, not
  code. If that slips, an unbiased EQE scan computes negative and
  `measurement_engine.py`'s 0-200% sanity clamp floors it to 0% *with a logged
  warning* — that's the intended signal to go check wiring, not a bug to route around
  in software. An `abs()`-based auto-correction was tried here and reverted: it masked
  genuine wiring mistakes and broke the same-cell-after-its-own-calibration
  self-consistency check (measuring the Si71889 again right after calibrating with it
  should reproduce ~its own IPCE curve, not silently "work" regardless of sign). See
  `save_data()` in `io/data_io.py` and `_negative_ipce_warning()` in
  `core/measurement_engine.py`.

---

## Current Capabilities

| Mode | Description | Status |
|---|---|---|
| EQE Scan | Wavelength sweep, calibrated EQE, live plot | ✅ Stable, verified on real hardware |
| Live Monitoring (Live EQE) | Fixed-wavelength continuous acquisition, changeable mid-run, real time-series save | ✅ Stable, verified on real hardware |
| Electrical Control | SMU bias voltage + compliance, always reset to 0 V when a measurement ends | ✅ Stable |
| Calibration measurement | Produces a new incident-beam calibration from the external Si71889 cell; admin-only (see Admin mode below) | ✅ Stable, verified on real hardware |
| Advanced Acquisition Settings | Stabilization time; reference-meter mode (direct current vs. voltage-across-shunt) + shunt resistance; hidden entirely unless admin mode is unlocked, recorded in saved metadata | ✅ Stable, verified on real hardware |
| MMF (Mismatch Factor) | Standalone dialog (MMF button, session panel): picks a DUT EQE file + a reference-cell EQE file + a lamp spectrum file, computes the spectral mismatch factor and Jsc against AM1.5GT, plots all four spectra, saves a summary/plot/data-CSV trio | ✅ Implemented 2026-08-19, not yet verified on real hardware/lab files beyond this repo's own saved files |
| Lock-in EQE / Lock-in Live EQE | Modulated-light EQE workflow | 🚧 Not implemented; menu entries admin-only |
| Manual shutter control | Shutter checkbox (session panel) opens/closes the monochromator by hand once instruments are connected (a side effect of Start -- no separate connect step); disabled during any measurement so it can't race with the engine's own shutter control, re-synced on start/start-fail/finish. `_on_start()` always forces it open right after connecting -- including the very first Start of a session, the only point a connection is ever made -- regardless of whatever it was left at | ✅ Implemented 2026-11-02, not yet verified on real hardware |

### Admin mode

Calibration measurement, editing Advanced Acquisition Settings, Simulation mode, and
the not-yet-implemented Lock-in modes are gated by `SessionPanel.is_admin()` (added
2026-11-02, replacing a hardcoded `_DEVELOPER_USERS = {"felix"}` username check) --
unlocked for the rest of the session via the "Admin" checkbox + a PIN
(`session.admin_pin`, `config_default.yaml`, deliberately `null` there since that
file is shipped/public; set in your own gitignored `config_local.yaml`). Not tied to
any particular person's name, not persisted across launches. See
`session_panel.py`'s `_on_admin_toggled()`/`admin_changed` signal and
`mainwindow_qt.py`'s `update_mode_visibility()`.

---

## Active Development Priorities

Work through this roadmap **in order**. Do not skip ahead.

Done (kept here for context, not to be redone): live mode has its own time-domain data
buffers and plot infra separate from scan mode; live-mode CSV logging of time/
wavelength/EQE/currents; an Advanced Acquisition Settings panel exists (stabilization
time, reference-meter mode/shunt resistance — extend it, don't replace it, for future
acquisition parameters), admin-only to edit (see Admin mode above); reference-cell and
test-cell currents are now read simultaneously (added 2026-08-19, see
`measurement_engine._measure_simultaneously` and `CurrentMeter.settle()` in
`instruments/roles.py`) instead of sequentially, so a fluctuating Xenon lamp affects
both readings the same way and mostly cancels out of the EQE ratio — the Keithley 2400
test meter's NPLC/samples now match the Keithley 2000 reference meter's (both NPLC=5,
one reading) so the two integrate over the same duration too; extend both instruments'
config together if either changes. `Keithley2000` also has its own `settle()` now
(added 2026-08-19): a reference-meter dark-current reading taken immediately after
`configure_current_measurement()` — which every real Start click calls — right after a
prior scan just finished, was confirmed on real hardware to be wildly wrong (~140-170nA
off from a true ~2-3nA dark level, settling back to normal from the very next reading
onward). `mainwindow_qt.py`'s dark-current recapture calls `settle()` right after
reconfiguring, before trusting the "real" reading — same pattern as the 2400's
autorange settle(), just triggered by a function/range reconfigure instead of a signal
jump. This was the actual cause of a real, previously mysterious "calibration measures
fine, but the EQE scan right after doesn't match" bug that looked at first like a bad
calibration measurement. `_on_start()` now also rejects a second Start click
immediately (added 2026-11-02) if `controller.is_measuring` is already true, and
disables the Start button for a run's duration (re-enabled in
`on_measurement_finished()`) — confirmed on real hardware that without this, a
double-click during Live Monitoring let the second click's setup code (reconfiguring
the reference meter, recapturing dark current) run real serial I/O on the same shared
instrument connection the first, still-running measurement thread was actively using;
the two threads' concurrent reads/writes desynced the monochromator's request/response
framing and crashed with an unrelated-looking `ValueError` from a garbled reply, after
which the serial connection was left in a bad state. `run_measurement_async()`'s own
"already running" `RuntimeError` guard still exists but fires too late on its own —
after that hardware I/O already happened — so the real fix had to be earlier, in the
GUI. That double-click race turned out to be only one way to trigger a worse,
pre-existing problem confirmed the same evening on real hardware: once the Cornerstone
130 gave back one empty or garbled reply (also seen from a single, non-concurrent
Start — a flaky write/cable issue is enough on its own), nothing resynced the serial
stream afterward, so every later command kept reading stale leftover bytes (e.g. a
prior shutter command's own echoed text, `'SHUTTER C'`) and kept crashing with an
unrelated-looking `ValueError`, for the rest of that session. Fixed in
`monochromator.py` (not `smu.py` — the Keithley driver untouched): `Cornerstone130.
write()` now flushes the input buffer (`reset_input_buffer()`) before every send, so
stale bytes from an earlier hiccup can't bleed into the next command instead of
accumulating forever; `command()`/`query()` retry once on an empty reply; and a new
`_query_numeric()` helper (used by `grating`/`filter_wheel_position`/`outport`/
`slit_width`/`position`) retries once more if the reply parses as garbage even though
it wasn't empty. Exhausting both retries raises `MonochromatorCommError` instead of a
bare `ValueError`, so a genuine hardware failure reads clearly as one. See
`tests/test_monochromator.py` (a `FakeSerialPort` test double scripts replies — no
real hardware involved) for the exact failure modes this covers.

Note: the reference meter's "Current (direct)"/"Voltage (shunt)" mode (see
keithley2000.py's `mode`) is a *software* setting that must match the instrument's
*physical* wiring — the GUI panel doesn't move any wires. As of 2026-08-14 the
reference cell is wired for voltage-shunt sensing (Input HI/LO terminals); the old
direct-current wiring (AMPS/INPUT LO) is disconnected, so "Current (direct)" won't
read anything meaningful until it's physically reconnected too (see README's Advanced
Acquisition Settings section).

1. **Modulation control** (hardware abstraction layer)

2. **Lock-in readout** (signal extraction)

3. **Background illumination control**

4. **Lock-in EQE workflow** (combining 1–3)

---

## Instrument Mocking

The role abstraction (`CurrentMeter`/`BiasCurrentMeter`) makes mocking straightforward:
`tests/test_hardware_roles.py` defines fakes (`FakeCurrentMeter`, `FakeBiasCurrentMeter`,
`FakeMonochromator`, and purpose-built variants like `OutputRequiredBiasCurrentMeter`,
`ExplodingBiasCurrentMeter`) that implement the role API without touching real
hardware, and exercises `perform_measurement`/`perform_live_monitoring` against them.
Use the same pattern for new engine-level tests.

For the GUI, `simulate=True` (Session panel checkbox) swaps in `SimulatedSMU` +
`SimulatedMonochromator` regardless of `active_profile` — it does not simulate
per-driver quirks of the Keithley 2000/2400 specifically, only the generic dual-channel
role behavior. If you add a new instrument driver, give it (or its role wrapper)
equivalent test-fake coverage before relying on it in engine/controller-level tests.

**Priority:** expand mock coverage before implementing lock-in or modulation features,
since those introduce new hardware dependencies.

---

## Testing Guidelines

- `python -m unittest discover -s tests -v` must pass before considering any
  engine/controller/instrument-layer change done.
- Test measurement logic against mock instruments (see Instrument Mocking above), not real hardware.
- After any change to the measurement engine or controller, verify that:
  - Scan mode still completes a full wavelength sweep
  - Live mode starts, streams data, changes wavelength mid-run, and stops cleanly
  - Callbacks fire correctly and do not block the GUI thread
  - Bias resets to 0 V and the monochromator returns to 550 nm when a measurement ends, including on error
- For changes touching real instrument drivers, timing, or anything that's hard to
  fully exercise with fakes, also verify on real hardware — always ask the user to
  confirm the GUI is closed first, and clean up any test-tagged files/folders you
  create afterward.
- Do not modify tests to make them pass — fix the code instead.

---

## Version Control

- Development on this GUI rewrite happened on `feature/pyside6-gui`, merged into `main`
  once the app reached feature parity and was verified end-to-end on real hardware.
  Going forward, commit directly to `main` for normal incremental work; use a feature
  branch again for another sizeable, multi-session effort.
- Write clear, descriptive commit messages explaining what changed and why.
- Commit working states only — do not commit broken or half-refactored code.
- **Bump `version` in `pyproject.toml` on every push that changes installed
  behavior** (i.e. anything under `src/`, `pyproject.toml` itself, or shipped
  package data — not doc-only or test-only changes). A patch bump
  (`0.2.0` → `0.2.1`) is enough for routine fixes; bump minor for a
  user-facing feature or behavior change. Do this in the same commit as the
  change, not a separate one.
  **Why:** colleagues install via `pip install git+https://github.com/FTEickemeyer/eqe-gui.git`
  (see README's Installation section) and upgrade via
  `pip install --upgrade git+...`. Without a version bump, pip can decide the
  already-installed version still "satisfies" the requirement and skip
  reinstalling even though the code on GitHub has moved on — this has
  already caused a colleague's upgrade to silently do nothing. A version
  bump is what makes `--upgrade` actually detect and pull the new commit.

---

## Code Style

- Python 3.x, PySide6 for GUI
- Follow existing naming conventions in each module
- Keep instrument, engine, controller, and GUI layers in separate files/modules
- New measurement parameters belong in the engine or controller — never hardcoded in the GUI
- Type hints encouraged for new code; do not add them retroactively to stable modules

---

## What NOT to Do

- Do not introduce new dependencies without flagging them first (and add them to `pyproject.toml`'s `dependencies`, not just `requirements.txt`)
- Do not merge scan-mode and live-mode data structures
- Do not call GUI methods from background threads — use callbacks/signals
- Do not add reconnection logic to the instrument layer
- Do not refactor stable modules (SMU/TSP) while implementing new features
- Do not confuse the internal reference cell with the external Si71889 reference cell (see Hard Constraints)
- Do not add a new package directory without an `__init__.py` (see Packaging) — it will build and run fine locally (editable install) while silently breaking a real install
