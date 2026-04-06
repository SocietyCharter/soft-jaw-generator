# Soft Jaw Generator

Generates matched soft jaw pairs for milling vises from any STEP file.

This is a jaw-aware vise rework — the generator splits grip geometry by jaw ownership instead of subtracting the same cutter into both halves, eliminating the fan/unwrapped debug shapes produced by the earlier approach.

---

## What's New in v3

- Grip geometry is now split by **jaw ownership** (left/right) rather than shared subtraction
- Part is clipped to a **top grip slab only** — no full-part subtraction artifacts
- Each jaw's owned region is swept outward along jaw motion to reduce lock risk
- New parameters: `seam_clearance`, `sweep_steps`
- OpenGL viewer with color-coded debug visualization:
  - **Gray** — jaw blocks
  - **Red** — part
  - **Blue / Green** — left / right cutters
  - **Orange / Yellow** — left / right owned grip regions

---

## Output Files

| File | Description |
|---|---|
| `jaw_left.step` | Left jaw half |
| `jaw_right.step` | Right jaw half |
| `grip_body_debug.step` | Combined grip body (debug) |
| `left_owned_debug.step` | Left jaw owned grip region |
| `right_owned_debug.step` | Right jaw owned grip region |
| `left_cutter_debug.step` | Left cutter body |
| `right_cutter_debug.step` | Right cutter body |

---

## GUI Controls

| Control | Description |
|---|---|
| Rotate X / Y / Z | Part orientation — sets the angle the pocket is cut at |
| Grip Depth % | How deep the jaws hold the part (40% default) |
| Mount Height | Jaw stock height below part datum |
| Stock Margin | Overhang beyond part footprint per side |
| Clearance | Gap between pocket wall and part surface |
| Draft Angle | Pocket wall taper — prevents part from locking |
| Seam Clearance | Gap at the jaw split line |
| Sweep Steps | Resolution of anti-lock sweep envelope |

### Good Starting Values

| Parameter | Range |
|---|---|
| Clearance | `0.10` – `0.25` |
| Draft Angle | `0.5` – `1.5°` |
| Seam Clearance | `0.00` – `0.20` |
| Sweep Steps | `10` – `16` |

---

## Usage

### GUI

```bash
source venv/bin/activate
python3 soft_jaw_gui_opengl.py
```

### CLI

```bash
python3 soft_jaw_gen_v3.py \
  --input part.step \
  --output-dir ./output \
  --grip-depth 16 \
  --clearance 0.15 \
  --draft-angle 1.0 \
  --seam-clearance 0.10 \
  --sweep-steps 12 \
  --orient 0,0,0
```

> **Tip:** If the part orientation looks wrong, rotate it until the clamp zone sits near the top of the gray jaw blocks. The program only cuts the top grip slab.

---

## Requirements

- Python 3.10+
- CadQuery 2.4+
- PyQt5
- pyqtgraph (OpenGL viewer)
- PyOpenGL
- numpy
- numpy-stl

---

## Install — Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Or use the included script:

```bash
bash install_linux.sh
```

## Install — Windows

CadQuery's OCP backend doesn't install cleanly via pip on Windows. Use conda (Miniforge recommended):

```powershell
# 1. Install Miniforge: https://github.com/conda-forge/miniforge/releases/latest
#    Download Miniforge3-Windows-x86_64.exe and run it

# 2. Open Miniforge Prompt, then:
conda install -c conda-forge cadquery
pip install PyQt5 pyqtgraph PyOpenGL numpy numpy-stl

# 3. Run the GUI
python soft_jaw_gui_opengl.py
```

---

## Honest Limitations

- Clearance and draft are approximate — not a full OCC normal-offset cavity.
- Anti-lock sweep is a directional envelope approximation, not a mathematical proof of removability.
- Currently targets **2-jaw mill vises**. 3-jaw chuck support is the next architecture step — not included.

---

## Files

| File | Description |
|---|---|
| `soft_jaw_gen_v3.py` | Core geometry engine |
| `soft_jaw_gui_opengl.py` | PyQt5 + pyqtgraph OpenGL GUI |
| `requirements.txt` | Python dependencies |
| `install_linux.sh` | Linux/macOS venv setup script |
