# Soft Jaw Generator

Generates matched soft jaw pairs for milling vises from any STEP file.

## Features

- CadQuery geometry engine
- Left/right jaw split for vise mounting
- Drafted pocket walls (anti-lock taper)
- Knife relief chamfer at split line
- M6 bolt holes for vise bed mounting
- Blender Cycles preview render
- PyQt5 GUI with live controls

## GUI Controls

| Control | Description |
|---|---|
| Rotate X/Y/Z | Part orientation — sets the angle the pocket is cut at |
| Grip Depth % | How deep the jaws hold the part (40% default) |
| Mount Height | Jaw stock height below part datum |
| Stock Margin | Overhang beyond part footprint per side |
| Clearance | Gap between pocket wall and part surface |
| Draft Angle | Pocket wall taper — prevents part from locking |
| Relief Angle | Knife chamfer at split line |

## Usage

### GUI
```bash
source venv/bin/activate
python3 soft_jaw_gui.py
```

### CLI
```bash
python3 soft_jaw_gen_v2.py \
  --input part.step \
  --output-dir ./output \
  --grip-depth 16 \
  --relief-angle 3.0 \
  --orient 0,0,0
```

## Requirements

- Python 3.10+
- CadQuery 2.x
- PyQt5
- Blender (for preview rendering)

## Install — Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Install — Windows

CadQuery's OCP backend doesn't install cleanly via pip on Windows.
Use conda (Miniforge recommended):

```powershell
# 1. Install Miniforge: https://github.com/conda-forge/miniforge/releases/latest
#    Download Miniforge3-Windows-x86_64.exe and run it

# 2. Open Miniforge Prompt, then:
conda install -c conda-forge cadquery
pip install PyQt5

# 3. Run the GUI
python soft_jaw_gui.py
```

Or if you prefer a one-liner to clone and set up:
```powershell
git clone https://github.com/SocietyCharter/soft-jaw-generator.git
cd soft-jaw-generator
conda install -c conda-forge cadquery
pip install PyQt5
python soft_jaw_gui.py
```

## Output

- `jaw_left.step` — left jaw half
- `jaw_right.step` — right jaw half
- `jaw_preview_gui.png` — Blender render of assembly
