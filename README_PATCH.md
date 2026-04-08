# Soft Jaw Generator patch set — jaw-aware vise rework

This is a drop-in replacement for the earlier patch.

## What changed

- The generator now splits the grip geometry by jaw ownership instead of subtracting the same cutter into both halves.
- The part is clipped to a top grip slab only.
- Each jaw's owned region is swept outward along jaw motion to reduce lock risk.
- Added `seam_clearance` and `sweep_steps` parameters.
- The OpenGL viewer now shows:
  - gray: jaws
  - red: part
  - blue/green: left/right cutters
  - orange/yellow: left/right owned grip regions

## Files exported

- `jaw_left.step`
- `jaw_right.step`
- `grip_body_debug.step`
- `left_owned_debug.step`
- `right_owned_debug.step`
- `left_cutter_debug.step`
- `right_cutter_debug.step`

## Honest limitations

- Clearance/draft are still approximate, not a full OCC normal-offset cavity.
- Anti-lock is approximate. This is a directional sweep envelope, not a mathematical proof of removability.
- This build is aimed at a 2-jaw mill vise first. 3-jaw chuck logic is the next architecture step, not included here.

## Good starting values

- Clearance: `0.10` to `0.25`
- Draft angle: `0.5` to `1.5`
- Seam clearance: `0.00` to `0.20`
- Sweep steps: `10` to `16`

## Replace these files in your project

- `soft_jaw_gen_v3.py`
- `soft_jaw_gui_opengl.py`
- `README_PATCH.md`

The dependency files were not materially changed.
