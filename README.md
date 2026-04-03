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

## Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install cadquery PyQt5
```

## Output

- `jaw_left.step` — left jaw half
- `jaw_right.step` — right jaw half
- `jaw_preview_gui.png` — Blender render of assembly
