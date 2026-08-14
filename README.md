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
- **Calibration measurement** — produces the incident-beam calibration a regular scan
  needs (see [Calibration](#calibration))
- **Simulation mode** — runs the full GUI/measurement pipeline against simulated
  instruments, no hardware required (useful for development or demos)

See [CLAUDE.md](CLAUDE.md) for the internal architecture (GUI → controller →
measurement engine → instruments) and the active development roadmap. For a
step-by-step guide to actually running measurements (aimed at lab users, not
developers), see the printable
[User Manual](docs/EQE_GUI_User_Manual.docx).

## Requirements

- Windows (the monochromator/SMU drivers assume Windows serial/GPIB stacks)
- Python >= 3.10
- For real measurements: a Keithley 2000 + 2400 (or 2600) reachable via PyVISA/serial,
  a VISA runtime installed for PyVISA to talk to them (e.g. NI-VISA), and an Oriel
  Cornerstone130 monochromator on a serial port. Simulation mode needs none of this.

## Installation

### For regular use (a new Windows account on the lab PC, a colleague's machine, etc.)

This is a normal pip package — install it straight from GitHub, no manual clone
needed:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install git+https://github.com/FTEickemeyer/eqe-gui.git
```

That pulls in every dependency (PySide6, numpy, pandas, matplotlib, PyVISA,
pyserial, PyYAML, and `fte-analysis-libraries`) automatically — no separate
`requirements.txt` step needed. It also installs an `eqe` command, so you can just
run:

```bash
eqe
```

from anywhere the venv is active. (`python -m eqe` still works too.) To upgrade to
the latest version later, run the same `pip install git+...` command again, or add
`--upgrade`.

> **Gotcha:** a venv is not relocatable by copying files. `.venv/Scripts/activate.bat`
> and `.venv/pyvenv.cfg` bake in the *absolute path* the venv was created at. If you
> ever copy a venv folder to a different path or a different Windows user account,
> `activate` will silently put the *old* location's `Scripts` folder on `PATH`, and
> `where python`/`where eqe` will resolve to the old account's interpreter even while
> your prompt correctly shows the new folder. Fix: create a fresh venv in the new
> location/account (`python -m venv .venv`) and `pip install` into that — never copy
> an existing `.venv` between accounts or machines.

### For development (working on the code itself)

```bash
git clone https://github.com/FTEickemeyer/eqe-gui.git
cd eqe-gui
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

`pip install -e .` resolves the `eqe` package to your local checkout in editable
mode, so code changes take effect immediately without reinstalling — same
dependency list as above, from `pyproject.toml`. (`requirements.txt` is a pinned
snapshot of a known-working environment, kept for reference/reproducibility; it's
not needed for a normal install.)

## Configuration

Most of the time **no configuration is needed** — `config_default.yaml` (shipped
with the package) already has paths that work for any account (they use `~`, i.e.
your own home directory) and instrument ports that match this lab's PC. Just install
and run.

Create a `config_local.yaml` only if you want to override something — e.g. share
calibration files across colleagues' accounts instead of each keeping their own, pin
a specific incident-beam calibration file, or point at different instrument ports on
a different PC. Two locations are checked, in this order:

| Location | When to use it |
|---|---|
| `~/.eqe/config_local.yaml` (i.e. `C:\Users\<you>\.eqe\config_local.yaml`) | **Recommended for a normal pip install.** Works regardless of where the package ended up on disk. |
| `config_local.yaml` next to `config_default.yaml` inside the installed package | Only reachable for an editable dev install (`pip install -e .` from a source checkout) — kept for backward compatibility with that workflow. |

Whichever one exists is used (the first one wins if both do); see
`config/load_config.py`. Start from the template:

```bash
mkdir %USERPROFILE%\.eqe
copy src\eqe\config\config_local_example.yaml %USERPROFILE%\.eqe\config_local.yaml
```

(For a real pip install rather than a dev checkout, grab
[`config_local_example.yaml`](src/eqe/config/config_local_example.yaml) from GitHub
instead of `src\...`, since there's no local clone to copy it from.) Then edit it —
see the comments in the template for what's worth overriding and why. Values in
`config_local.yaml` override the matching keys in `config_default.yaml`; anything you
don't set falls back to the default.

## Running

```bash
eqe
```

(or `python -m eqe` — both work; see [Installation](#installation).)

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
   `SiXXXXX_IPCE_<source>.csv`). This lives inside the package itself, so it's a code
   change — a maintainer needs to add the file and cut a new release/commit for a
   pip-installed colleague to pick it up (`pip install --upgrade git+...`).
2. Point `calibration.reference_cell_file` at that new filename — in
   `config_default.yaml` if this is now the standing default, or in your
   `config_local.yaml` (see [Configuration](#configuration)) to override it locally
   only.
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
