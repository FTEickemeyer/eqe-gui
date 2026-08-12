# eqe-gui

A PySide6 desktop application for measuring External Quantum Efficiency (EQE) / IPCE
of photovoltaic devices. It drives a Keithley SMU and an Oriel Cornerstone130
monochromator to sweep wavelength (or hold a fixed wavelength) while reading cell and
reference-diode current, then computes calibrated EQE against a reference cell and an
incident-beam calibration.

## What it does

- **EQE Scan** — sweeps wavelength, computes calibrated EQE, plots live as it measures
- **Live Monitoring** — holds a fixed wavelength and streams EQE/current vs. time
- **Electrical Control** — applies SMU bias voltage with compliance current limiting
- **Simulation mode** — runs the full GUI/measurement pipeline against simulated
  instruments, no hardware required (useful for development or demos)

See [CLAUDE.md](CLAUDE.md) for the internal architecture (GUI → controller →
measurement engine → instruments) and the active development roadmap.

## Requirements

- Windows (the monochromator/SMU drivers assume Windows serial/GPIB stacks)
- Python >= 3.10
- For real measurements: a Keithley SMU reachable via GPIB (PyVISA) and an Oriel
  Cornerstone130 monochromator on a serial port. Simulation mode needs neither.

## Installation

```bash
git clone https://github.com/FTEickemeyer/eqe-gui.git
cd eqe-gui
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
pip install -e .
```

The `pip install -e .` step is required even though `requirements.txt` also lists an
editable install of this repo — that entry points at a specific GitHub commit and
will *not* pick up your local checkout. Running `pip install -e .` afterward makes
sure the `eqe` package resolves to the code in your working directory rather than a
fetched copy.

> **Gotcha:** if you ever copy this project folder (or its `.venv`) to a different
> path or a different Windows user account, the editable install remembers the *old*
> absolute path and Python will silently keep importing from there. Symptoms are
> import errors that reference a path you don't recognize, or a running app that
> reads/writes files in someone else's user folder. Fix: re-run `pip install -e .`
> from the new location.

## Configuration — do this on every new machine/account

Settings live in two layered YAML files under `src/eqe/config/`:

| File | Purpose | Tracked in git? |
|---|---|---|
| `config_default.yaml` | Repo-wide defaults (paths use `~`, generic instrument addresses) | Yes |
| `config_local.yaml` | Your machine's real paths, instrument addresses, active calibration file | **No — gitignored** |

`config_local.yaml` does not exist after a fresh clone. Create it by copying the
template and filling in values for your account:

```bash
cp src/eqe/config/config_local_example.yaml src/eqe/config/config_local.yaml
```

Then edit it:

```yaml
paths:
  measurements_dir: C:/Users/<you>/Documents/EQE/measurements
  calibrations_dir: C:/Users/<you>/Documents/EQE/calibrations
  logs_dir: C:/Users/<you>/AppData/Local/eqe/logs

calibration:
  active_incident_beam_file: <name-of-your-current-incident-beam-calibration>.csv
```

Values in `config_local.yaml` override the matching keys in `config_default.yaml`
(see `load_config.py`); anything you don't set there falls back to the default.

Because this file is gitignored, **it will never travel with the repo** — every new
checkout, machine, or user account needs its own copy with paths that actually exist
for that account. Skipping this step doesn't crash the app outright, but it will
read/write measurement and calibration data under whatever path is currently in
`config_local.yaml`, which may belong to a different user entirely.

## Running

```bash
python -m eqe
```

To run without hardware, enable simulation mode from the **Session** panel in the
GUI — this swaps in `SimulatedSMU`/`SimulatedMonochromator` and lets you exercise
scan mode, live mode, and saving without any instrument connected.

## Calibration

- The reference-cell IPCE curve ships with the repo
  (`src/eqe/resources/calibration_defaults/`) and is set via
  `calibration.reference_cell_file`.
- The **incident-beam calibration** (`calibration.active_incident_beam_file`) is
  machine/setup-specific — it's a measurement you produce yourself and must live in
  `calibrations_dir`. There is no default; scans will fail with a clear
  `FileNotFoundError` until this is set correctly.

## Project layout

```
GUI (PySide6)               src/eqe/app/
  → Controller              src/eqe/core/controller.py
    → Measurement Engine    src/eqe/core/measurement_engine.py
      → Instruments         src/eqe/core/instruments/
```

Full file map, callback architecture, and hard constraints for contributors are in
[CLAUDE.md](CLAUDE.md).
