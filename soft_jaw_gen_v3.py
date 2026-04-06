#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass
from typing import Optional, Tuple

import cadquery as cq


@dataclass
class JawBuildResult:
    part_positioned: cq.Workplane
    grip_body: cq.Workplane
    left_owned: cq.Workplane
    right_owned: cq.Workplane
    left_cutter: cq.Workplane
    right_cutter: cq.Workplane
    grip_cutter: cq.Workplane
    jaw_left: cq.Workplane
    jaw_right: cq.Workplane
    stock_x: float
    stock_y: float
    mount_height: float
    grip_depth: float
    seam_clearance: float


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Soft Jaw Generator v3 — direct split-jaw negative",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", required=True, help="Input STEP file path")
    p.add_argument("--output-dir", default="", help="Output dir (default: same as input)")
    p.add_argument("--clearance", type=float, default=0.25, help="Approx cavity clearance in mm")
    p.add_argument("--relief-angle", type=float, default=3.0, help="Knife relief angle at split line (degrees)")
    p.add_argument("--stock-margin", type=float, default=15.0, help="Jaw stock overhang beyond part bbox per side (mm)")
    p.add_argument("--mount-height", type=float, default=20.0, help="Jaw mounting block height below part datum (mm)")
    p.add_argument("--grip-depth", type=float, default=None, help="How deep the pocket grips the part (mm). Default: 40%% of part height")
    p.add_argument("--orient", default="0,0,0", help="Part rotation rx,ry,rz degrees")
    p.add_argument("--draft-angle", type=float, default=1.0, help="Approx release angle used in the clearance growth model")
    p.add_argument("--seam-clearance", type=float, default=0.0, help="Gap centered on the jaw split plane in mm")
    return p.parse_args()


def load_step(path: str) -> cq.Workplane:
    try:
        shape = cq.importers.importStep(path)
        if shape is None:
            raise ValueError("importStep returned None")
        return shape
    except Exception as e:
        print(f"ERROR: Cannot load STEP '{path}': {e}", file=sys.stderr)
        sys.exit(1)


def get_bbox(shape: cq.Workplane):
    return shape.val().BoundingBox()


def orient_part(shape: cq.Workplane, rx: float, ry: float, rz: float) -> cq.Workplane:
    bb = get_bbox(shape)
    cx = (bb.xmin + bb.xmax) / 2.0
    cy = (bb.ymin + bb.ymax) / 2.0
    cz = (bb.zmin + bb.zmax) / 2.0

    if rx:
        shape = shape.rotate((cx, cy, cz), (cx + 1, cy, cz), rx)
    if ry:
        shape = shape.rotate((cx, cy, cz), (cx, cy + 1, cz), ry)
    if rz:
        shape = shape.rotate((cx, cy, cz), (cx, cy, cz + 1), rz)
    return shape


def center_on_z(shape: cq.Workplane) -> cq.Workplane:
    bb = get_bbox(shape)
    cx = (bb.xmin + bb.xmax) / 2.0
    cy = (bb.ymin + bb.ymax) / 2.0
    return shape.translate((-cx, -cy, -bb.zmin))


def _shape_from_val(val) -> cq.Workplane:
    return cq.Workplane("XY").newObject([val])


def _iter_vals(shape: cq.Workplane):
    try:
        vals = list(shape.vals())
        if vals:
            return vals
    except Exception:
        pass
    try:
        v = shape.val()
        return [v] if v is not None else []
    except Exception:
        return []


def _union_vals(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    out = _shape_from_val(vals[0])
    for v in vals[1:]:
        try:
            out = out.union(_shape_from_val(v))
        except Exception:
            pass
    return out


def nonempty(shape: cq.Workplane, tol: float = 1e-6) -> bool:
    try:
        bb = get_bbox(shape)
        return (bb.xmax - bb.xmin) > tol and (bb.ymax - bb.ymin) > tol and (bb.zmax - bb.zmin) > tol
    except Exception:
        return False


def robust_intersect(shape: cq.Workplane, tool: cq.Workplane) -> cq.Workplane:
    try:
        direct = shape.intersect(tool)
        if nonempty(direct):
            return direct
    except Exception:
        pass

    hits = []
    for sv in _iter_vals(shape):
        try:
            piece = _shape_from_val(sv).intersect(tool)
            if nonempty(piece):
                hits.extend(_iter_vals(piece))
        except Exception:
            continue

    unioned = _union_vals(hits)
    if unioned is not None and nonempty(unioned):
        return unioned

    return cq.Workplane("XY")


def clip_with_box(shape: cq.Workplane, xlen: float, ylen: float, zlen: float, center: Tuple[float, float, float]) -> cq.Workplane:
    box = cq.Workplane("XY").box(xlen, ylen, zlen).translate(center)
    return robust_intersect(shape, box)


def _scale_shape_uniform_about_center(shape: cq.Workplane, factor: float) -> cq.Workplane:
    bb = get_bbox(shape)
    cx = (bb.xmin + bb.xmax) / 2.0
    cy = (bb.ymin + bb.ymax) / 2.0
    cz = (bb.zmin + bb.zmax) / 2.0

    moved = shape.translate((-cx, -cy, -cz))
    scaled_val = moved.val().scale(max(float(factor), 1.0))
    scaled = _shape_from_val(scaled_val)
    return scaled.translate((cx, cy, cz))


def make_jaw_stock(stock_x: float, stock_y: float, mount_height: float) -> Tuple[cq.Workplane, cq.Workplane]:
    half_y = stock_y / 2.0
    jaw_left = cq.Workplane("XY").box(stock_x, half_y, mount_height).translate((0, -(half_y / 2.0), mount_height / 2.0))
    jaw_right = cq.Workplane("XY").box(stock_x, half_y, mount_height).translate((0, +(half_y / 2.0), mount_height / 2.0))
    return jaw_left, jaw_right


def make_grip_body(part_for_cut: cq.Workplane, grip_depth: float) -> cq.Workplane:
    bb = get_bbox(part_for_cut)
    part_w = max((bb.xmax - bb.xmin) + 400.0, 5.0)
    part_d = max((bb.ymax - bb.ymin) + 400.0, 5.0)
    eps = max(0.02, grip_depth * 0.002)

    z_bottom = bb.zmin - eps
    z_top = bb.zmin + grip_depth + eps
    z_mid = (z_top + z_bottom) / 2.0
    z_len = max(z_top - z_bottom, eps * 2.0)

    grip_zone = cq.Workplane("XY").box(part_w, part_d, z_len).translate((0, 0, z_mid))
    grip_body = robust_intersect(part_for_cut, grip_zone)
    if nonempty(grip_body):
        return grip_body

    raise ValueError("Grip-zone intersection produced an empty body")


def apply_clearance_and_draft(shape: cq.Workplane, clearance: float, draft_angle_deg: float) -> cq.Workplane:
    bb = get_bbox(shape)
    dx = max(bb.xmax - bb.xmin, 1e-6)
    dy = max(bb.ymax - bb.ymin, 1e-6)
    dz = max(bb.zmax - bb.zmin, 1e-6)

    expand = max(0.0, clearance) + max(0.0, dz * math.tan(math.radians(max(0.0, draft_angle_deg))))
    target_x = dx + 2.0 * expand
    target_y = dy + 2.0 * expand
    factor = max(target_x / dx, target_y / dy, 1.0)

    grown = _scale_shape_uniform_about_center(shape, factor)
    center = ((bb.xmin + bb.xmax) / 2.0, (bb.ymin + bb.ymax) / 2.0, (bb.zmin + bb.zmax) / 2.0)
    clipped = clip_with_box(grown, target_x + 20.0, target_y + 20.0, dz + 0.01, center)
    if not nonempty(clipped):
        return shape
    return clipped


def make_owned_region(grip_body: cq.Workplane, side: str, seam_clearance: float) -> cq.Workplane:
    bb = get_bbox(grip_body)
    xlen = (bb.xmax - bb.xmin) + 200.0
    zlen = (bb.zmax - bb.zmin) + 20.0
    ymin = bb.ymin - 100.0
    ymax = bb.ymax + 100.0

    seam_half = max(0.0, seam_clearance) / 2.0

    if side == "left":
        owner_ymax = -seam_half
        if owner_ymax <= ymin:
            owner_ymax = (bb.ymin + bb.ymax) / 2.0
        ylen = max(owner_ymax - ymin, 0.5)
        cy = ymin + ylen / 2.0
    else:
        owner_ymin = seam_half
        if ymax <= owner_ymin:
            owner_ymin = (bb.ymin + bb.ymax) / 2.0
        ylen = max(ymax - owner_ymin, 0.5)
        cy = owner_ymin + ylen / 2.0

    owner_box = cq.Workplane("XY").box(xlen, ylen, zlen).translate((0, cy, (bb.zmin + bb.zmax) / 2.0))
    owned = robust_intersect(grip_body, owner_box)
    if not nonempty(owned):
        raise ValueError(f"{side} jaw owns no grip geometry. Reduce seam clearance or re-orient the part.")
    return owned


def extend_cutter_for_clean_boolean(owned: cq.Workplane, side: str, seam_clearance: float = 0.0, pad: float = 0.2) -> cq.Workplane:
    """
    Keep the cutter honest: use the actual owned geometry, just extend it
    a hair toward the seam so the boolean cuts cleanly.

    No sweep. No unwrapped envelope.
    """
    bb = get_bbox(owned)
    xlen = (bb.xmax - bb.xmin) + 2.0
    zlen = (bb.zmax - bb.zmin) + 2.0

    if side == "left":
        y_min = bb.ymin - pad
        y_max = bb.ymax + pad
    else:
        y_min = bb.ymin - pad
        y_max = bb.ymax + pad

    ylen = max(y_max - y_min, 0.5)
    cy = (y_min + y_max) / 2.0

    trim_box = cq.Workplane("XY").box(xlen, ylen, zlen).translate((0, cy, (bb.zmin + bb.zmax) / 2.0))
    cutter = robust_intersect(owned, trim_box)
    if not nonempty(cutter):
        return owned
    return cutter


def add_knife_relief(jaw: cq.Workplane, split_z: float, relief_angle_deg: float, jaw_width: float, jaw_depth: float, side: str) -> cq.Workplane:
    if relief_angle_deg <= 0:
        return jaw

    try:
        relief_depth = jaw_depth * 0.12
        relief_height = relief_depth * math.tan(math.radians(relief_angle_deg))

        if side == "left":
            pf = 0.0
            pts = [(pf, split_z), (pf - relief_depth, split_z), (pf, split_z + relief_height)]
        else:
            pf = 0.0
            pts = [(pf, split_z), (pf + relief_depth, split_z), (pf, split_z + relief_height)]

        wedge = cq.Workplane("YZ").polyline(pts).close().extrude(jaw_width / 2.0, both=True)
        return jaw.cut(wedge)
    except Exception:
        return jaw


def add_bolt_holes(jaw: cq.Workplane, stock_x: float, stock_y: float, hole_diam_mm: float = 6.5) -> cq.Workplane:
    try:
        ox, oy = stock_x / 3.0, stock_y / 6.0
        return jaw.faces("<Z").workplane().pushPoints([(ox, oy), (-ox, oy), (ox, -oy), (-ox, -oy)]).circle(hole_diam_mm / 2.0).cutThruAll()
    except Exception:
        return jaw


def build_jaws(
    input_path: str,
    clearance: float = 0.25,
    relief_angle: float = 3.0,
    stock_margin: float = 15.0,
    mount_height: float = 20.0,
    grip_depth: Optional[float] = None,
    orient: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    draft_angle: float = 1.0,
    seam_clearance: float = 0.0,
) -> JawBuildResult:
    part = load_step(input_path)
    rx, ry, rz = orient
    if rx or ry or rz:
        part = orient_part(part, rx, ry, rz)
    part = center_on_z(part)

    bb = get_bbox(part)
    pdx = bb.xmax - bb.xmin
    pdy = bb.ymax - bb.ymin
    pdz = bb.zmax - bb.zmin

    if grip_depth is None:
        grip_depth = max(0.1, pdz * 0.40)
    grip_depth = min(grip_depth, pdz)

    stock_x = pdx + 2.0 * stock_margin
    stock_y = pdy + 2.0 * stock_margin

    jaw_left_stock, jaw_right_stock = make_jaw_stock(stock_x, stock_y, mount_height)

    part_for_cut = part.translate((0, 0, mount_height))

    grip_body = make_grip_body(part_for_cut, grip_depth)
    grip_body = apply_clearance_and_draft(grip_body, clearance=clearance, draft_angle_deg=draft_angle)

    left_owned = make_owned_region(grip_body, side="left", seam_clearance=seam_clearance)
    right_owned = make_owned_region(grip_body, side="right", seam_clearance=seam_clearance)

    left_cutter = extend_cutter_for_clean_boolean(left_owned, side="left", seam_clearance=seam_clearance)
    right_cutter = extend_cutter_for_clean_boolean(right_owned, side="right", seam_clearance=seam_clearance)

    jaw_left = jaw_left_stock.cut(left_cutter)
    jaw_right = jaw_right_stock.cut(right_cutter)

    jaw_left = add_knife_relief(jaw_left, mount_height, relief_angle, stock_x, stock_y / 2.0, "left")
    jaw_right = add_knife_relief(jaw_right, mount_height, relief_angle, stock_x, stock_y / 2.0, "right")

    jaw_left = add_bolt_holes(jaw_left, stock_x, stock_y)
    jaw_right = add_bolt_holes(jaw_right, stock_x, stock_y)

    part_positioned = part_for_cut
    grip_cutter = left_cutter.union(right_cutter)

    return JawBuildResult(
        part_positioned=part_positioned,
        grip_body=grip_body,
        left_owned=left_owned,
        right_owned=right_owned,
        left_cutter=left_cutter,
        right_cutter=right_cutter,
        grip_cutter=grip_cutter,
        jaw_left=jaw_left,
        jaw_right=jaw_right,
        stock_x=stock_x,
        stock_y=stock_y,
        mount_height=mount_height,
        grip_depth=grip_depth,
        seam_clearance=seam_clearance,
    )


def safe_export(shape: cq.Workplane, path: str, label: str) -> bool:
    try:
        vol = shape.val().Volume()
        if vol <= 0:
            print(f"WARNING: {label} has zero/negative volume — skipping.")
            return False
        cq.exporters.export(shape, path)
        print(f"{label}: {path}")
        return True
    except Exception as e:
        print(f"WARNING: export failed for {label}: {e}")
        return False


def main() -> None:
    args = parse_args()
    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        print(f"ERROR: Not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = os.path.abspath(args.output_dir) if args.output_dir else os.path.dirname(input_path)
    os.makedirs(out_dir, exist_ok=True)

    try:
        orient = tuple(float(x) for x in args.orient.split(","))
        if len(orient) != 3:
            raise ValueError
    except Exception:
        print("ERROR: --orient must be rx,ry,rz e.g. 0,0,90", file=sys.stderr)
        sys.exit(1)

    result = build_jaws(
        input_path=input_path,
        clearance=args.clearance,
        relief_angle=args.relief_angle,
        stock_margin=args.stock_margin,
        mount_height=args.mount_height,
        grip_depth=args.grip_depth,
        orient=orient,
        draft_angle=args.draft_angle,
        seam_clearance=args.seam_clearance,
    )

    safe_export(result.jaw_left, os.path.join(out_dir, "jaw_left.step"), "jaw_left")
    safe_export(result.jaw_right, os.path.join(out_dir, "jaw_right.step"), "jaw_right")
    safe_export(result.grip_body, os.path.join(out_dir, "grip_body_debug.step"), "grip_body_debug")
    safe_export(result.left_owned, os.path.join(out_dir, "left_owned_debug.step"), "left_owned_debug")
    safe_export(result.right_owned, os.path.join(out_dir, "right_owned_debug.step"), "right_owned_debug")
    safe_export(result.left_cutter, os.path.join(out_dir, "left_cutter_debug.step"), "left_cutter_debug")
    safe_export(result.right_cutter, os.path.join(out_dir, "right_cutter_debug.step"), "right_cutter_debug")
    safe_export(result.grip_cutter, os.path.join(out_dir, "grip_cutter_debug.step"), "grip_cutter_debug")

    print("Done.")


if __name__ == "__main__":
    main()
