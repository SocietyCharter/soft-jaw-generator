# Soft Jaw Generator

Soft Jaw Generator builds soft-jaw vise geometry from an input STEP model using CadQuery, then previews the result in a PyQt5 + OpenGL desktop UI.

This revision refactors the generator around split-jaw ownership so each jaw is cut from its own derived grip region instead of subtracting one shared cutter into both halves.

## What it does

- Imports a STEP part model
- Reorients the part with X/Y/Z rotation controls
- Builds left and right vise jaws as separate bodies
- Clips the grip region to a top holding slab instead of using the full part volume
- Applies approximate clearance and draft growth
- Splits grip ownership across the jaw seam
- Sweeps each jaw cutter outward along jaw motion to reduce lock risk
- Exports left/right jaw STEP files
- Previews jaws, part, and optional debug geometry in an OpenGL viewer

## What changed in this update

- Reworked the generator to use jaw-specific owned regions
- Added `seam_clearance` control
- Added `sweep_steps` control
- Improved split-jaw debug visualization in the GUI
- Added Windows PowerShell launcher support for a project-local Conda environment
- Cleaned repo hygiene to exclude local envs and transient files

## Output files

Primary exports:
- `jaw_left.step`
- `jaw_right.step`

Optional debug exports:
- `grip_cutter_debug.step`
- `left_cutter_debug.step`
- `right_cutter_debug.step`
- `left_owned_debug.step`
- `right_owned_debug.step`

## Current limitations

- Clearance and draft are still approximate, not a true OCC normal-offset cavity
- Anti-lock behavior is approximate, based on a directional sweep envelope
- Current workflow is aimed at a 2-jaw mill vise
- Complex part profiling is not yet a true contour-following cavity strategy
- No machining accessibility analysis yet
- No 3-jaw chuck / turning mode yet
- No multi-part fixture mode yet

## Recommended starting values

- Clearance: `0.10` to `0.25`
- Draft angle: `0.5` to `1.5`
- Seam clearance: `0.00` to `0.20`
- Sweep steps: `10` to `16`
- Grip depth: just enough to capture the clamp zone

## Requirements

- Python 3.10+
- CadQuery / OCP backend
- PyQt5
- pyqtgraph
- PyOpenGL
- numpy
- numpy-stl

Dependencies are listed in `requirements.txt`.

## Linux install

```bash
chmod +x install_linux.sh
./install_linux.sh
```

Then run:

```bash
source venv/bin/activate
python soft_jaw_gui_opengl.py
```

## Windows launch

Use the included PowerShell launcher:

```powershell
./launch_soft_jaw_gui.ps1
```

What it does:
- locates an existing Conda install
- creates a project-local `.conda-env`
- installs missing requirements if needed
- launches the GUI

## CLI usage

```bash
python soft_jaw_gen_v3.py --input /path/to/part.step --output-dir ./output
```

Common parameters:
- `--clearance`
- `--relief-angle`
- `--stock-margin`
- `--mount-height`
- `--holding-height`
- `--part-z-offset`
- `--orient rx,ry,rz`
- `--draft-angle`
- `--seam-clearance`
- `--sweep-steps`

## GUI usage notes

- Load a STEP file
- Rotate until the real clamp zone is near the top of the gray jaw blocks
- Adjust holding height, clearance, draft, and seam clearance
- Preview first, then export STEP
- Enable debug export when you want to inspect owned regions and cutters

## Repo hygiene

Ignored local artifacts include:
- `.venv/`
- `.conda-env/`
- `__pycache__/`
- `.codex_import_check.py`

## Status

This is a working split-jaw vise-focused refactor with better ownership logic and debug visibility, but it is not yet a finished production cavity engine for arbitrary fixturing cases.