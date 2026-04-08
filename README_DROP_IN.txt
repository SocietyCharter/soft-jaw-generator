DROP-IN REPLACEMENT NOTES

What this set does:
- Uses a top grip slab only, not the full part.
- Splits the grip body into left/right ownership.
- Cuts each jaw with its own owned body.
- Removes the earlier sweep/envelope behavior that made the weird fan/unwrapped debug shapes.
- Keeps a combined grip_cutter field for compatibility.

What this set does NOT do yet:
- full anti-lock pull-direction validation
- true offset-surface cavity generation
- 3-jaw chuck / turn mode

Files to overwrite in your project folder:
- soft_jaw_gen_v3.py
- soft_jaw_gui_opengl.py

Suggested first test settings:
- seam clearance: 0.00
- clearance: 0.10 to 0.25
- draft angle: 0.5 to 1.0
- grip depth: just enough to capture the clamp zone

If the part orientation is wrong:
- rotate it until the real clamp zone is near the top of the gray jaw blocks
- the program only cuts the top grip slab
