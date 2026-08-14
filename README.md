# eqe-gui

A PySide6 desktop application for measuring External Quantum Efficiency (EQE) / IPCE
of photovoltaic devices. It drives a Keithley SMU and an Oriel Cornerstone130
monochromator to sweep wavelength (or hold a fixed wavelength) while reading cell
current alongside an internal reference-diode current, then computes calibrated EQE
against an incident-beam calibration (itself produced periodically using a separate,
external Si71889 reference cell — see [Calibration](#calibration)).

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

`pip install -e .` is the step that makes the `eqe` package resolve to the code in
your local checkout, in editable mode (uses `pyproject.toml`). `requirements.txt`
covers everything else (pinned third-party dependencies).

> **Gotcha:** a venv is not relocatable by copying files. `.venv/Scripts/activate.bat`
> and `.venv/pyvenv.cfg` bake in the *absolute path* the venv was created at. If you
> ever copy this project folder (or its `.venv`) to a different path or a different
> Windows user account, `activate` will silently put the *old* location's `Scripts`
> folder on `PATH`, and `where python` will resolve to the old account's interpreter
> even while your prompt correctly shows the new folder. Symptoms: `where python`
> pointing at someone else's profile, or import errors/tracebacks referencing a path
> you don't recognize. Fix: delete `.venv` and recreate it from scratch in the new
> location (`python -m venv .venv`), then repeat the `pip install` steps above —
> don't copy an existing `.venv` between accounts or machines.

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

### Advanced Acquisition Settings

**Stabilization time** (default 100 ms) is how long the measurement waits after the
monochromator moves to a new wavelength, before taking a reading — giving the
cell's photocurrent time to settle. It applies after every wavelength move in both
scan mode and live mode (including wavelength changes made mid-run from the
Wavelength setting panel). All settings in this panel are recorded in the metadata
header of saved files.

## Calibration

Two different reference cells are involved, and they should never be confused:

- **Internal reference cell** ("Siref"/"intSiref" in the code) — built into the
  system, monitors the monochromatic light via a beamsplitter, and is read
  continuously for *every* measurement (scan, live, or calibration).
- **External Si71889 reference cell** — a separate, physically swappable cell with
  its own certified IPCE curve, temporarily installed in the sample position only
  while running a calibration measurement.

Config keys for each:

- The Si71889 cell's certified IPCE curve ships with the repo
  (`src/eqe/resources/calibration_defaults/71889_L_IPCE_NIST.csv`) and is set via
  `calibration.reference_cell_file`.
- The **incident-beam calibration** (`calibration.active_incident_beam_file`) is
  machine/setup-specific — it's a measurement you produce yourself (see below) and
  must live in `calibrations_dir`. Left unset (the default), the **most recently
  produced** `incbeamcurr_*.csv` in `calibrations_dir` is used automatically — set
  it to a specific filename only if you want to pin a particular calibration instead
  of always using the latest one. Either way, scans will fail with a clear
  `FileNotFoundError` if no matching file can be found. The GUI logs which file it
  picked ("Using incident-beam calibration: ...") at the start of every measurement,
  and records its filename in the saved file's metadata header (`# Calibration:`
  section) so it stays traceable even after a newer calibration is produced later.

### Running a calibration measurement

The incident-beam calibration is produced by scanning with the **Si71889** cell
installed instead of the sample (the internal reference cell stays in place and is
read as usual):

1. Physically install the Si71889 reference cell (the one matching
   `calibration.reference_cell_file`) in place of the sample.
2. Check **"Calibration measurement"** in the Calibration / Saving panel. This also
   sets the Start/Stop wavelength fields to 350/1170 nm to reflect the range that
   will actually be scanned — a calibration scan always covers the full 350–1170 nm
   range regardless of what's in those fields.
3. Start a scan (Standard EQE mode).
4. Click **Save** once it finishes. This writes both the usual measurement file
   (raw internal-reference/Si71889 currents only, no EQE) and a new
   `incbeamcurr_*.csv` into `calibrations_dir`.
5. That's it — the new file becomes the active calibration automatically (the most
   recently produced `incbeamcurr_*.csv` is always used, see above), unless
   `calibration.active_incident_beam_file` is pinned to something else.

### Switching to a different external reference cell

`calibration.reference_cell_file` and `calibration.active_incident_beam_file` cover
two different things — the Si71889 cell's own certified IPCE curve vs. a calibration
*derived* from measuring with it — so replacing the physical external reference cell
means updating both:

1. Get the new cell's certified IPCE curve into the same two-column format as
   `71889_L_IPCE_NIST.csv` (`Wavelength (nm), IPCE (%)`), and save it into
   `src/eqe/resources/calibration_defaults/`, named after the new cell (e.g.
   `SiXXXXX_IPCE_<source>.csv`).
2. Point `calibration.reference_cell_file` at that new filename — in
   `config_default.yaml` if this is now the standing default, or in your (gitignored)
   `config_local.yaml` to override it locally only.
3. Run a new calibration measurement (see above) with the new cell physically
   installed. Use the new cell's ID as the sample name (e.g. `SiXXXXX`) so the
   generated `incbeamcurr_SiXXXXX_*.csv` filename stays self-describing. Saving it
   makes it the active calibration automatically (it's now the latest).

This does **not** involve the internal reference cell in any way -- that one is a
fixed part of the instrument, not something you swap or reconfigure.

## Project layout

```
GUI (PySide6)               src/eqe/app/
  → Controller              src/eqe/core/controller.py
    → Measurement Engine    src/eqe/core/measurement_engine.py
      → Instruments         src/eqe/core/instruments/
```

Full file map, callback architecture, and hard constraints for contributors are in
[CLAUDE.md](CLAUDE.md).
