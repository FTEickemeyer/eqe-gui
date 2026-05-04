# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (activate venv first)
pip install -r requirements.txt

# Run the application
python -m eqe

# Run with simulated instruments (no hardware required)
# Set simulation mode via the Session panel in the GUI, or pass instruments from simulated.py
```

There are currently no automated tests. When verifying changes, run the app in simulation mode and manually confirm scan + live modes work end-to-end.

---

## Architecture

```
GUI (PySide6)               src/eqe/app/
  → Controller              src/eqe/core/controller.py       # threaded orchestration, callback dispatch
    → Measurement Engine    src/eqe/core/measurement_engine.py  # measurement logic, loop strategies
      → Instruments         src/eqe/core/instruments/        # SMU + monochromator abstraction layer
```

**Core abstraction:** the measurement engine supports interchangeable loop strategies:
- Wavelength loop → scan mode (`perform_measurement`) — EQE vs wavelength
- Time loop → live mode (`perform_live_monitoring`) — EQE vs time

This abstraction must be preserved as new modes are added.

### Key files

| Layer | File | Key class / function |
|---|---|---|
| GUI | `app/mainwindow_qt.py` | `MainWindow` — collects params, dispatches callbacks, updates plots |
| GUI | `app/qt_models.py` | Mode constants, per-mode panel visibility rules |
| GUI | `app/state.py` | `AppState` — mutable GUI state |
| Controller | `core/controller.py` | `MeasurementController` — threading, stop flag, instrument lifecycle |
| Engine | `core/measurement_engine.py` | `perform_measurement`, `perform_live_monitoring` |
| Params | `core/models.py` | `MeasurementParams` dataclass |
| Instruments | `core/instruments/smu.py` | `SMU` — Keithley via PyVISA / Lua TSP (do not modify) |
| Instruments | `core/instruments/monochromator.py` | `Cornerstone130` — Oriel via serial |
| Instruments | `core/instruments/simulated.py` | `SimulatedSMU`, `SimulatedMonochromator` |
| Instruments | `core/instruments/factory.py` | `initialize_system()` — real or simulated based on config |
| Config | `config/load_config.py` | `load_config()` — merges default + local YAML |
| Analysis | `analysis/calibration.py` | `open_calibration()` — loads reference cell & incident beam data |
| I/O | `io/data_io.py` | `save_data()` — writes result CSV |

### Callback architecture

The measurement engine communicates with the GUI exclusively via callbacks passed into `run_measurement_async`. Never call GUI methods directly from the engine or controller threads.

Callbacks: `on_live_update`, `on_point_acquired`, `on_status`, `on_done`, `on_error`, `on_finished`

`MainWindow` connects these to Qt signals (`point_acquired_signal`) to safely update widgets from the background thread.

### Configuration

`src/eqe/config/config_default.yaml` holds all defaults (instrument addresses, paths, measurement parameters). Override locally with `config_local.yaml` (same directory, git-ignored). Key fields: `instruments.mono_port`, `instruments.smu_address`, `calibration.active_incident_beam_file`, `paths.*`.

---

## Hard Constraints

These rules are non-negotiable. Apply them to every change, in every file.

- **DO NOT modify the SMU / TSP layer.** This code is stable and hardware-validated.
- **Maintain strict GUI / backend separation.** The backend must remain GUI-agnostic.
- **Reuse the existing callback architecture** for all thread-safe GUI updates.
- **Prefer minimal-diff, incremental changes.** Do not refactor unrelated code.
- **Do not reconnect instruments** unless explicitly asked. The instrument layer is designed
  for persistent connections.

---

## Current Capabilities

| Mode | Description | Status |
|---|---|---|
| EQE Scan | Wavelength sweep, calibrated EQE, live plot | ✅ Stable |
| Live Monitoring | Fixed-wavelength continuous acquisition | ✅ Working, needs cleanup |
| Electrical Control | SMU bias voltage + compliance | ✅ Stable |

---

## Active Development Priorities

Work through this roadmap **in order**. Do not skip ahead.

1. **Clean up live mode architecture**
   - Create a dedicated time-domain data model (do not reuse `_wavelengths`)
   - Separate live mode plot infrastructure from scan mode
   - Remove integrated current readout from live mode UI

2. **Live data logging**
   - Optional CSV logging of: `time_s`, `wavelength_nm`, `EQE`, `cell_current_A`,
     `ref_current_A`, `bias_voltage`, `compliance_current`

3. **Acquisition settings panel**
   - GUI inputs: fixed wavelength, averaging/update rate, optional max duration

4. **Modulation control** (hardware abstraction layer)

5. **Lock-in readout** (signal extraction)

6. **Background illumination control**

7. **Lock-in EQE workflow** (combining 4–6)

---

## Instrument Mocking

Instrument mocks are **partially implemented**. Before running or testing any
measurement logic:

- Confirm which instruments have mock classes available
- Use mocks for all unit and integration tests
- Do not assume hardware is present unless explicitly stated
- Flag any new instrument interactions that lack a corresponding mock

**Priority:** expand mock coverage before implementing lock-in or modulation features,
since those introduce new hardware dependencies.

---

## Testing Guidelines

- Test measurement logic against mock instruments, not real hardware
- After any change to the measurement engine or controller, verify that:
  - Scan mode still completes a full wavelength sweep
  - Live mode starts, streams data, and stops cleanly
  - Callbacks fire correctly and do not block the GUI thread
- Do not modify tests to make them pass — fix the code instead

---

## Version Control

- Committing directly to `main`
- Write clear, descriptive commit messages referencing the roadmap step
  (e.g., `Live mode: introduce dedicated time-domain data buffer`)
- Commit working states only — do not commit broken or half-refactored code

---

## Code Style

- Python 3.x, PySide6 for GUI
- Follow existing naming conventions in each module
- Keep instrument, engine, controller, and GUI layers in separate files/modules
- New measurement parameters belong in the engine or controller — never hardcoded in the GUI
- Type hints encouraged for new code; do not add them retroactively to stable modules

---

## What NOT to Do

- Do not introduce new dependencies without flagging them first
- Do not merge scan-mode and live-mode data structures
- Do not call GUI methods from background threads — use callbacks/signals
- Do not add reconnection logic to the instrument layer
- Do not refactor stable modules (SMU/TSP) while implementing new features
