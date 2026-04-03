#!/usr/bin/env python3
"""
soft_jaw_gen_v2.py — Soft Jaw Generator v2

Generates a matched soft jaw pair for a milling vise from any input STEP file.

Key design principle:
  Soft jaws grip only the LOWER portion of the part (grip_depth).
  The remainder of the part is exposed above the jaw face for machining.
  Jaw stock sits below the part. The split plane is at the bottom of the part.

Geometry layout (Z axis, side view):
  
  z = part_height + mount_height   ← top of part (fully exposed, machining happens here)
  z = mount_height + grip_depth    ← part top surface of pocket (grip line)
  z = mount_height                 ← jaw top face / part datum / split plane
  z = 0                            ← bottom of jaw stock (bolts to vise bed)

Usage:
  python3 soft_jaw_gen_v2.py --input part.step [options]
"""
import argparse
import math
import os
import sys
import subprocess
import tempfile

import cadquery as cq


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Soft Jaw Generator v2",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument("--input",        required=True,         help="Input STEP file path")
    p.add_argument("--output-dir",   default="",            help="Output dir (default: same as input)")
    p.add_argument("--clearance",    type=float, default=0.3, help="Pocket clearance in mm")
    p.add_argument("--relief-angle", type=float, default=3.0, help="Knife relief angle at split line (degrees)")
    p.add_argument("--stock-margin", type=float, default=15.0, help="Jaw stock overhang beyond part bbox per side (mm)")
    p.add_argument("--mount-height", type=float, default=20.0, help="Jaw mounting block height below part datum (mm)")
    p.add_argument("--grip-depth",   type=float, default=None,
                   help="How deep the pocket grips the part (mm). Default: 40%% of part height")
    p.add_argument("--orient",       default="0,0,0",       help="Part rotation rx,ry,rz degrees")
    p.add_argument("--preview",      default=True, action=argparse.BooleanOptionalAction,
                   help="Render Blender preview")
    p.add_argument("--preview-out",  default="",            help="Preview PNG path")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def load_step(path):
    try:
        shape = cq.importers.importStep(path)
        if shape is None:
            raise ValueError("importStep returned None")
        return shape
    except Exception as e:
        print(f"ERROR: Cannot load STEP '{path}': {e}", file=sys.stderr)
        sys.exit(1)


def get_bbox(shape):
    return shape.val().BoundingBox()


def orient_part(shape, rx, ry, rz):
    bb = get_bbox(shape)
    cx = (bb.xmin + bb.xmax) / 2
    cy = (bb.ymin + bb.ymax) / 2
    cz = (bb.zmin + bb.zmax) / 2
    if rx != 0:
        shape = shape.rotate((cx, cy, cz), (cx + 1, cy, cz), rx)
    if ry != 0:
        shape = shape.rotate((cx, cy, cz), (cx, cy + 1, cz), ry)
    if rz != 0:
        shape = shape.rotate((cx, cy, cz), (cx, cy, cz + 1), rz)
    return shape


def center_on_z(shape):
    """Center XY at origin, bottom face on Z=0."""
    bb = get_bbox(shape)
    cx = (bb.xmin + bb.xmax) / 2
    cy = (bb.ymin + bb.ymax) / 2
    return shape.translate((-cx, -cy, -bb.zmin))


# ---------------------------------------------------------------------------
# Jaw construction
# ---------------------------------------------------------------------------

def make_jaw_stock(stock_x, stock_y, mount_height):
    """
    Returns (jaw_left, jaw_right) — two separate blocks split along the Y axis.
    Each block is stock_x wide, stock_y/2 deep, mount_height tall.
    The pocket face of each jaw is the inner face (facing Y=0).
    jaw_left  sits at negative Y (y = -stock_y/2 to 0)
    jaw_right sits at positive Y (y = 0 to +stock_y/2)
    They are separated by a small gap (1mm) for the vise to close.
    """
    half_y = stock_y / 2
    jaw_left = (
        cq.Workplane("XY")
        .box(stock_x, half_y, mount_height)
        .translate((0, -(half_y / 2), mount_height / 2))
    )
    jaw_right = (
        cq.Workplane("XY")
        .box(stock_x, half_y, mount_height)
        .translate((0, +(half_y / 2), mount_height / 2))
    )
    return jaw_left, jaw_right


def cut_pocket(jaw_stock, part, grip_depth, clearance, draft_angle_deg=1.5):
    """
    Cut the part profile into jaw_stock, gripping only the bottom grip_depth.
    
    Anti-lock: pocket walls are drafted outward by draft_angle_deg (default 1.5°)
    so the part releases cleanly when the vise opens — it won't wedge.
    Clearance inflates the pocket footprint uniformly.
    """
    bb = get_bbox(part)
    pdx = (bb.xmax - bb.xmin) + 2 * clearance
    pdy = (bb.ymax - bb.ymin) + 2 * clearance

    # Draft: pocket is slightly wider at the top (jaw face) than at the bottom
    # draft_expand = grip_depth * tan(draft_angle)
    draft_expand = grip_depth * math.tan(math.radians(draft_angle_deg))

    # Build a tapered pocket cutter via loft:
    #   bottom face (at z = mount_height - grip_depth): pdx x pdy
    #   top face    (at z = mount_height):               pdx+2*de x pdy+2*de
    # This means the part can always be lifted straight out — no lock.
    try:
        bottom_w, bottom_d = pdx, pdy
        top_w,    top_d    = pdx + 2 * draft_expand, pdy + 2 * draft_expand
        pocket = (
            cq.Workplane("XY")
            .workplane(offset=0)
            .rect(top_w, top_d)
            .workplane(offset=-grip_depth)
            .rect(bottom_w, bottom_d)
            .loft()
            .translate((0, 0, 0))  # caller positions via part_for_cut
        )
    except Exception:
        pocket = None

    # Fallback: simple rectangular pocket
    if pocket is None:
        pocket = (
            cq.Workplane("XY")
            .box(pdx + draft_expand, pdy + draft_expand, grip_depth)
            .translate((0, 0, 0))
        )

    try:
        result = jaw_stock.cut(pocket)
        if result.val().Volume() < jaw_stock.val().Volume():
            return result
    except Exception as e:
        print(f"WARNING: pocket cut failed: {e}")
    return jaw_stock


def add_knife_relief(jaw, split_z, relief_angle_deg, jaw_width, jaw_depth):
    """
    Chamfer the pocket-face corner at the split line (jaw top face).
    Prevents the jaw edge from biting into the part as the vise closes.

    Triangle cross-section (YZ plane), extruded full jaw width (X):
      pt1: pocket face at split      (y = -jaw_depth/2, z = split_z)
      pt2: inset from pocket face    (y = -jaw_depth/2 + relief_depth, z = split_z)
      pt3: above split on pock face  (y = -jaw_depth/2, z = split_z + relief_height)
    """
    if relief_angle_deg <= 0:
        return jaw
    try:
        relief_depth  = jaw_depth * 0.12
        relief_height = relief_depth * math.tan(math.radians(relief_angle_deg))
        pf = -jaw_depth / 2

        pts = [
            (pf,                  split_z),
            (pf + relief_depth,   split_z),
            (pf,                  split_z + relief_height),
        ]
        wedge = (
            cq.Workplane("YZ")
            .polyline(pts)
            .close()
            .extrude(jaw_width / 2, both=True)
        )
        return jaw.cut(wedge)
    except Exception as e:
        print(f"WARNING: knife relief failed: {e}")
        return jaw


def add_bolt_holes(jaw, stock_x, stock_y, hole_diam_mm=6.5):
    """
    4× M6 clearance through-holes for mounting to vise bed.
    Pattern: ±stock_x/3, ±stock_y/3 centered on jaw.
    """
    try:
        ox, oy = stock_x / 3, stock_y / 3
        return (
            jaw
            .faces(">Z").workplane()
            .pushPoints([(ox, oy), (-ox, oy), (ox, -oy), (-ox, -oy)])
            .circle(hole_diam_mm / 2)
            .cutThruAll()
        )
    except Exception as e:
        print(f"WARNING: bolt holes failed: {e}")
        return jaw


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def safe_export(shape, path, label):
    try:
        vol = shape.val().Volume()
        if vol <= 0:
            print(f"WARNING: {label} has zero/negative volume — skipping.")
            return False
        cq.exporters.export(shape, path)
        print(f"  {label}: {path} ({os.path.getsize(path)//1024}KB)")
        return True
    except Exception as e:
        print(f"WARNING: export failed for {label}: {e}")
        return False


def export_stl(shape, path):
    cq.exporters.export(shape, path, exportType="STL")


# ---------------------------------------------------------------------------
# Blender preview
# ---------------------------------------------------------------------------

def find_blender():
    for c in ["blender", "/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender"]:
        try:
            r = subprocess.run([c, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def render_preview(part_stl, lower_stl, upper_stl, preview_out):
    blender = find_blender()
    if not blender:
        print("WARNING: Blender not found — skipping preview.")
        return

    lines = [
        "import bpy, math",
        "bpy.ops.object.select_all(action='SELECT')",
        "bpy.ops.object.delete()",
        "",
        "def import_stl(path, name, rgb, z_off=0):",
        "    bpy.ops.wm.stl_import(filepath=path)",
        "    obj = bpy.context.selected_objects[0]",
        "    obj.name = name",
        "    obj.location.z += z_off",
        "    mat = bpy.data.materials.new(name=name)",
        "    mat.use_nodes = True",
        "    bsdf = mat.node_tree.nodes.get('Principled BSDF')",
        "    if bsdf:",
        "        bsdf.inputs['Base Color'].default_value = (rgb[0]/255, rgb[1]/255, rgb[2]/255, 1)",
        "        bsdf.inputs['Roughness'].default_value = 0.25",
        "        bsdf.inputs['Metallic'].default_value = 0.8",
        "    if obj.data.materials: obj.data.materials[0] = mat",
        "    else: obj.data.materials.append(mat)",
        "    return obj",
        "",
        # Part sits above jaws, exposed — render it slightly translucent red
        f"p = import_stl(r'{part_stl}', 'Part', (220, 60, 60))",
        "p_mat = p.data.materials[0]",
        "p_mat.blend_method = 'BLEND'",
        "bsdf2 = p_mat.node_tree.nodes.get('Principled BSDF')",
        "if bsdf2: bsdf2.inputs['Alpha'].default_value = 0.6",
        # Jaws split on Y — left jaw offset -Y, right jaw offset +Y, small gap for clarity
        f"jl = import_stl(r'{lower_stl}', 'JawLeft',  (140, 140, 155))",
        "jl.location.y = -5",
        f"jr = import_stl(r'{upper_stl}', 'JawRight', (140, 140, 155))",
        "jr.location.y = 5",
        "",
        "# Camera — pulled far back, high angle, looking down at full assembly",
        "# Shows both jaw halves open with part seated between them",
        "bpy.ops.object.camera_add(location=(0, -350, 280))",
        "cam = bpy.context.object",
        "cam.rotation_euler = (math.radians(52), 0, 0)",
        "bpy.context.scene.camera = cam",
        "",
        "# World background",
        "bpy.context.scene.world.use_nodes = True",
        "bg = bpy.context.scene.world.node_tree.nodes.get('Background')",
        "if bg: bg.inputs['Color'].default_value = (0.08, 0.08, 0.1, 1)",
        "",
        "# Lights",
        "bpy.ops.object.light_add(type='SUN', location=(300, 200, 400))",
        "bpy.context.object.data.energy = 4",
        "bpy.context.object.rotation_euler = (math.radians(45), 0, math.radians(30))",
        "bpy.ops.object.light_add(type='AREA', location=(-100, -200, 150))",
        "bpy.context.object.data.energy = 600",
        "bpy.context.object.data.size = 80",
        "",
        "# Render",
        "bpy.context.scene.render.engine = 'CYCLES'",
        "bpy.context.scene.cycles.samples = 96",
        "bpy.context.scene.cycles.use_denoising = False",
        "bpy.context.scene.render.film_transparent = False",
        "bpy.context.scene.render.resolution_x = 1280",
        "bpy.context.scene.render.resolution_y = 960",
        f"bpy.context.scene.render.filepath = r'{preview_out}'",
        "bpy.context.scene.render.image_settings.file_format = 'PNG'",
        "bpy.ops.render.render(write_still=True)",
        f"print('Preview: {preview_out}')",
    ]

    script = "\n".join(lines)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        print("  Rendering with Blender...")
        r = subprocess.run(
            [blender, "--background", "--python", script_path],
            capture_output=True, text=True, timeout=240
        )
        if r.returncode == 0 and os.path.exists(preview_out):
            print(f"  Preview: {preview_out} ({os.path.getsize(preview_out)//1024}KB)")
        else:
            print(f"WARNING: Blender failed (code {r.returncode})")
            if r.stderr:
                print(r.stderr[-600:])
    except subprocess.TimeoutExpired:
        print("WARNING: Blender timed out.")
    finally:
        os.unlink(script_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        print(f"ERROR: Not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = os.path.abspath(args.output_dir) if args.output_dir else os.path.dirname(input_path)
    os.makedirs(out_dir, exist_ok=True)

    try:
        rx, ry, rz = [float(x) for x in args.orient.split(",")]
    except Exception:
        print("ERROR: --orient must be rx,ry,rz e.g. 0,0,0", file=sys.stderr)
        sys.exit(1)

    print("\n=== Soft Jaw Generator v2 ===")
    print(f"Input:        {input_path}")

    # Load and orient
    part = load_step(input_path)
    if rx != 0 or ry != 0 or rz != 0:
        part = orient_part(part, rx, ry, rz)
    part = center_on_z(part)

    bb = get_bbox(part)
    pdx = bb.xmax - bb.xmin
    pdy = bb.ymax - bb.ymin
    pdz = bb.zmax - bb.zmin
    print(f"Part bbox:    {pdx:.1f} x {pdy:.1f} x {pdz:.1f} mm")

    # Grip and mount geometry
    grip_depth  = args.grip_depth if args.grip_depth else round(pdz * 0.40, 1)
    mount_h     = args.mount_height
    stock_x     = pdx + 2 * args.stock_margin
    stock_y     = pdy + 2 * args.stock_margin
    split_z     = mount_h   # jaw top face = part datum = split plane
    expose_h    = pdz - grip_depth   # how much of part sticks up above jaw face

    print(f"Grip depth:   {grip_depth:.1f} mm  ({grip_depth/pdz*100:.0f}% of part height)")
    print(f"Exposed:      {expose_h:.1f} mm above jaw face")
    print(f"Mount height: {mount_h:.1f} mm")
    print(f"Jaw stock:    {stock_x:.1f} x {stock_y:.1f} x {mount_h:.1f} mm")
    print(f"Clearance:    {args.clearance} mm")
    print(f"Relief angle: {args.relief_angle}°")
    print(f"Orient:       rx={rx} ry={ry} rz={rz}")

    # Part is at Z=0 to Z=pdz (sits on jaw top face)
    # Jaw stock is at Z=0 down to Z=-mount_h
    # Shift part and jaw stock so jaw stock bottom is at Z=0
    #   jaw stock: Z=0 to Z=mount_h
    #   part datum: Z=mount_h
    #   part: Z=mount_h to Z=mount_h+pdz

    part_positioned = part.translate((0, 0, mount_h))

    # Shift part for cut positioning
    part_for_cut = part.translate((0, 0, mount_h - grip_depth))

    # Build left and right jaw halves (split on Y axis)
    jaw_left_stock, jaw_right_stock = make_jaw_stock(stock_x, stock_y, mount_h)

    # Cut pockets into each jaw half
    # The pocket cutter needs the mount_height to position correctly
    # Patch cut_pocket to receive mount_h via a wrapper
    def cut_jaw(stock):
        bb2 = get_bbox(part_for_cut)
        pdx2 = (bb2.xmax - bb2.xmin) + 2 * args.clearance
        pdy2 = (bb2.ymax - bb2.ymin) + 2 * args.clearance
        draft_expand = grip_depth * math.tan(math.radians(1.5))
        # Simple drafted pocket box positioned at jaw top face
        pocket = (
            cq.Workplane("XY")
            .box(pdx2 + draft_expand, pdy2 + draft_expand, grip_depth)
            .translate((0, 0, mount_h - grip_depth / 2))
        )
        try:
            result = stock.cut(pocket)
            if result.val().Volume() < stock.val().Volume():
                return result
        except Exception as e:
            print(f"WARNING: pocket cut failed: {e}")
        return stock

    print("Cutting pockets...")
    jaw_left  = cut_jaw(jaw_left_stock)
    jaw_right = cut_jaw(jaw_right_stock)

    # Knife relief and bolt holes on each jaw
    if args.relief_angle > 0:
        print("Adding knife relief...")
        jaw_left  = add_knife_relief(jaw_left,  mount_h, args.relief_angle, stock_x, stock_y / 2)
        jaw_right = add_knife_relief(jaw_right, mount_h, args.relief_angle, stock_x, stock_y / 2)

    print("Adding bolt holes...")
    jaw_left  = add_bolt_holes(jaw_left,  stock_x, stock_y / 2)
    jaw_right = add_bolt_holes(jaw_right, stock_x, stock_y / 2)

    print("\nExporting STEP files...")
    lower_path = os.path.join(out_dir, "jaw_left.step")
    upper_path = os.path.join(out_dir, "jaw_right.step")
    safe_export(jaw_left,  lower_path, "jaw_left")
    safe_export(jaw_right, upper_path, "jaw_right")

    if args.preview:
        preview_out = args.preview_out or os.path.join(out_dir, "jaw_preview.png")
        print("\nExporting STLs for preview...")
        with tempfile.TemporaryDirectory() as tmpdir:
            part_stl  = os.path.join(tmpdir, "part.stl")
            lower_stl = os.path.join(tmpdir, "jaw_left.stl")
            upper_stl = os.path.join(tmpdir, "jaw_right.stl")
            export_stl(part_positioned, part_stl)
            export_stl(jaw_left,  lower_stl)
            export_stl(jaw_right, upper_stl)
            render_preview(part_stl, lower_stl, upper_stl, preview_out)

    print("\n=== Done ===")
    print(f"Part exposed for machining: {expose_h:.1f}mm above jaw face")


if __name__ == "__main__":
    main()
