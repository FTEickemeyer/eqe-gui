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
- **MMF (Mismatch Factor)** — standalone tool computing the spectral mismatch
  correction factor and AM1.5-equivalent Jsc from a DUT/reference-cell EQE pair and a
  lamp spectrum (see [MMF (Mismatch Factor)](#mmf-mismatch-factor))
- **Simulation mode** — runs the full GUI/measurement pipeline against simulated
  instruments, no hardware required (useful for development or demos)
- **Manual shutter control** — open/close the monochromator's shutter by hand outside
  of a measurement (see [Connecting instruments and the manual shutter
  control](#connecting-instruments-and-the-manual-shutter-control))

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

`eqe` is a windowed command — running it never opens a console/terminal window
alongside the GUI, so it's safe to launch from a desktop shortcut or the Start menu
(right-click `.venv\Scripts\eqe.exe` → Send to → Desktop). If the GUI ever seems to
fail to start with no visible error, check `%USERPROFILE%\.eqe\eqe_gui.log` — with no
console to print diagnostics to, that's where they go instead. (`python -m eqe` keeps
printing to whatever terminal you launched it from, as before.) See
[Logging](#logging) for the full breakdown of both log files, including the one that
mirrors everything shown in the GUI's own Status/Log panel.

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
a specific incident-beam calibration file, point at different instrument ports on
a different PC, or set the admin PIN (see [Admin mode](#admin-mode) — there is no
default, so admin mode does nothing on a fresh install until this is set). Two
locations are checked, in this order:

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

(or `python -m eqe` — both work; see [Installation](#installation).) `eqe` opens
straight to the GUI window, with no console window — see the note at the end of
[Installation](#installation) if you need to check its log for a startup problem.

To run without hardware, enable simulation mode from the **Session** panel in the
GUI — this swaps in `SimulatedSMU`/`SimulatedMonochromator` and lets you exercise
scan mode, live mode, and saving without any instrument connected.

### Connecting instruments and the manual shutter control

Clicking **Start** connects the instruments automatically if they aren't already —
there's no separate step needed for a normal measurement. The **Connect** button
exists for one specific case: using **Shutter open** (both next to Start/Stop) to
open or close the monochromator's shutter by hand, independently of any measurement,
e.g. to check alignment before running a scan. Shutter open is greyed out until
instruments are connected (via Connect, or implicitly by Start) and automatically
greys out again for the duration of any measurement — the measurement engine takes
full control of the shutter while it's running (closed between wavelength moves,
open for each reading), so the manual control can never fight it; it re-enables once
the measurement finishes, reflecting whatever the shutter's actual state is left at.

### Admin mode

Calibration measurement and editing Advanced Acquisition Settings are admin-only.
Check **"Admin"** (next to the User field) and enter the PIN (`session.admin_pin` in
`config_local.yaml` — see [Configuration](#configuration); there's no default PIN,
so this does nothing until someone sets one) to unlock both for the rest of that
session. Unchecking it needs no PIN. This is deliberately not tied to any particular
person's name — anyone who knows the PIN can act as admin, and it isn't remembered
between launches.

### Advanced Acquisition Settings

This panel is hidden entirely unless admin mode is unlocked (see above) — a wrong
value here, especially the reference meter settings below, silently affects every
measurement that follows, so there's no reason for most users to see or touch it. All
settings in this panel are recorded in the metadata header of saved files regardless
of who last changed them.

**Stabilization time** (default 100 ms) is how long the measurement waits after the
monochromator moves to a new wavelength, before taking a reading — giving the
cell's photocurrent time to settle. It applies after every wavelength move in both
scan mode and live mode (including wavelength changes made mid-run from the
Wavelength setting panel).

**Reference meter mode** controls how the Keithley 2000 senses the internal
reference cell's signal:

- **Voltage (shunt resistor)** — the default, matching the lab's wiring as of
  2026-08-14. The reference cell's photocurrent is read as a voltage drop across a
  known external shunt resistor (**Shunt resistance**, default 1987 Ω as of
  2026-11-02, previously 598 Ω) wired to the instrument's Input HI/LO terminals, then
  converted back to an equivalent current.
  This exists because the Keithley 2000's DC current function only has one,
  oversized range (10 mA) — far larger than this reference cell's actual signal
  (~10s of nA to a few µA) — giving poor resolution; DC voltage ranges go much
  lower, giving far better resolution for a weak signal like this one.
- **Current (direct)** — the original setup: the reference cell's current is read
  directly on the instrument's DC current function.

> **This is a software *and* hardware setting — they must match.** Switching the
> dropdown alone does not move any wires. As of 2026-08-14 the reference cell is
> wired to the Input HI/LO terminals for the shunt-resistor method; the AMPS/current
> input the old "Current (direct)" mode expects is no longer connected, so selecting
> "Current (direct)" without first rewiring back to the AMPS/INPUT LO terminals
> (INPUTS selector set to FRONT) will read near-zero noise, not the real signal. To
> go back to direct current sensing, physically rewire the reference cell to the
> AMPS/INPUT LO terminals *and* switch the dropdown to "Current (direct)" — either
> alone, without the other, is wrong.

## Logging

Two separate log files, both written under **your own Windows user account** — they
are not shared between colleagues' accounts or machines, so diagnosing an issue a
colleague hit means getting the file(s) from *their* account, not yours.

| File | Location | What it contains |
|---|---|---|
| Status/Log history | `%USERPROFILE%\AppData\Local\eqe\logs\eqe_YYYY-MM-DD.log` (`paths.logs_dir` in config — see [Configuration](#configuration)) | Every message ever shown in the GUI's Status/Log panel (measurement start/finish, saves, warnings, errors) — mirrored to disk as it's appended to the panel, via `LogPanel`'s `message_logged` signal (see `_persist_log_message()` in `mainwindow_qt.py`). |
| Crash/startup log | `%USERPROFILE%\.eqe\eqe_gui.log` | Raw `print()` output and unhandled tracebacks only — this is where diagnostics land when the windowed launcher has no console to print to (see `gui_qt.py`'s `_redirect_stdio_for_windowed_launch`). Useful mainly if the GUI fails to start at all, before the Status/Log panel even exists. |

Notes:

- The Status/Log file is **one file per calendar day**, appended across every session
  launched that day; a new file starts automatically the next day. The crash log is a
  single ever-growing file (no daily split).
- Both are plain append-only text files — safe to delete anytime, individually or the
  whole folder. The program just creates a fresh one the next time it writes; nothing
  is lost by deleting an old one.
- There is no automatic rotation/cleanup — old daily files accumulate until someone
  deletes them.
- If you want a *shared* location (e.g. so logs land somewhere a colleague or admin
  can check without asking each user for their file), point `paths.logs_dir` at a
  shared/network path in `config_local.yaml` — see [Configuration](#configuration).

### Turning the application log off

The Status/Log history (and the structured measurement entries `append_to_log()`
writes) can be turned off entirely via `config_local.yaml`:

```yaml
logging:
  enabled: false
```

The log is **on by default** (`logging.enabled: true`); set this to `false` only if you
have a specific reason not to persist it (disk space, privacy, etc.). This does **not** affect
the separate crash/startup log (`eqe_gui.log`) — that one always stays on, since the
windowed launcher depends on it having somewhere to send diagnostics when there's no
console to print to. See [`config_local_example.yaml`](src/eqe/config/config_local_example.yaml)
for a ready-to-uncomment example.

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

## MMF (Mismatch Factor)

A solar simulator's spectrum never exactly matches AM1.5G, which biases a device's
short-circuit current measured under it. The **MMF** button (top-right, next to About)
opens a dialog that computes the standard spectral mismatch correction factor from
three EQE-vs-wavelength inputs:

- **DUT EQE file** — any of this app's own saved `EQE_*.csv` scan files. Always
  defaults to the most recently *saved* EQE scan this session (blank if none yet) —
  re-opening the MMF dialog after measuring something new updates it again, even if
  the dialog was already open. Browse to pick a different one, including from a
  previous session.
- **Reference cell EQE file** — a reference cell's own EQE curve, picked from
  `paths.mmf_data_dir`'s `EQE_ref_cells/` subfolder. Defaults to the most recently
  modified file there.
- **Lamp spectrum file** — the solar simulator's own measured spectral photon flux,
  picked from `paths.mmf_data_dir`'s `PF_lamp_spectra/` subfolder (`Wavelength (nm),
  Spectral photon flux (1/[s m2 nm])`). Defaults to whichever file has `OrielIV` in its
  name (this lab's naming convention for that measurement).

`paths.mmf_data_dir` defaults to `~/Documents/EQE/MMF_data` (both subfolders are
created automatically if missing) — override it in `config_local.yaml` like any other
path (see [Configuration](#configuration)) if you want it somewhere else, e.g. a
shared folder for a curated set of reference-cell/lamp files.

Click **Run** to compute it. The graph shows all four spectra together, resampled onto
the overlap of the three input files' own wavelength ranges (never extrapolated beyond
what any of them actually measured) — DUT and reference-cell EQE on the left axis
(the DUT curve's legend label is its own device/sample name), the lamp and AM1.5GT
spectra on the right axis (fixed 0-1.1 scale), each normalized to 1 at 680 nm
(`analysis/mmf.py`'s `NORMALIZE_AT_NM`) so you can visually compare the simulator's
spectral shape against true sunlight. The Results section shows the mismatch factor
itself and the DUT's AM1.5-equivalent integrated current.

Click **Save** to write three files, all named `MMF_<cell name>_date<date>_time<time>`,
into the **same folder as the DUT EQE file** — so an MMF result stays alongside the
specific scan it was computed from, wherever that happens to live:

- `....csv` — a summary: the three input files used, the integration range, the
  mismatch factor, and the DUT's integrated current under AM1.5.
- `....png` — the graph.
- `..._data.csv` — the full data behind the graph (the common wavelength grid and all
  four resampled curves).

The cell name in the filename comes from the DUT file's own `# Sample name:` metadata
line if present, falling back to parsing it out of the filename, then to the bare
filename as a last resort.

## Project layout

```
GUI (PySide6)               src/eqe/app/
  → Controller              src/eqe/core/controller.py
    → Measurement Engine    src/eqe/core/measurement_engine.py
      → Instruments         src/eqe/core/instruments/
```

Full file map, callback architecture, and hard constraints for contributors are in
[CLAUDE.md](CLAUDE.md).
