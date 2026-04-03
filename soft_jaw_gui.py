#!/usr/bin/env python3
"""
Soft Jaw Generator — GUI
PyQt5 wrapper around soft_jaw_gen_v2 geometry engine.

Controls:
  - Load STEP file
  - Part rotation (rx, ry, rz) — sets the angle the pocket is cut at
  - Cut depth (grip %)
  - Split line Z position
  - Relief angle (knife relief at split face)
  - Draft angle (anti-lock taper on pocket walls)
  - Clearance
  - Generate → re-renders Blender preview
  - Export STEP files
"""
import os
import sys
import math
import subprocess
import tempfile
import traceback

# Add our generator to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cadquery as cq
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFileDialog,
    QSlider, QDoubleSpinBox, QSpinBox,
    QGroupBox, QSizePolicy, QMessageBox,
    QScrollArea, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont


# ── Worker thread so GUI doesn't freeze during generation ──────────────────

class GenerateWorker(QThread):
    done    = pyqtSignal(str)   # preview png path
    failed  = pyqtSignal(str)   # error message
    status  = pyqtSignal(str)   # progress text

    def __init__(self, params):
        super().__init__()
        self.params = params

    def run(self):
        try:
            p = self.params
            self.status.emit("Loading STEP…")

            import soft_jaw_gen_v2 as jaw_gen

            part = jaw_gen.load_step(p['input'])
            rx, ry, rz = p['rx'], p['ry'], p['rz']
            if rx or ry or rz:
                part = jaw_gen.orient_part(part, rx, ry, rz)
            part = jaw_gen.center_on_z(part)

            bb       = jaw_gen.get_bbox(part)
            pdx      = bb.xmax - bb.xmin
            pdy      = bb.ymax - bb.ymin
            pdz      = bb.zmax - bb.zmin

            mount_h     = p['mount_height']
            grip_depth  = pdz * p['grip_pct'] / 100.0
            stock_x     = pdx + 2 * p['stock_margin']
            stock_y     = pdy + 2 * p['stock_margin']
            clearance   = p['clearance']
            relief_ang  = p['relief_angle']
            draft_ang   = p['draft_angle']

            self.status.emit("Building jaw stock…")
            jaw_left_stock, jaw_right_stock = jaw_gen.make_jaw_stock(stock_x, stock_y, mount_h)

            part_for_cut = part.translate((0, 0, mount_h - grip_depth))

            def cut_jaw(stock):
                bb2 = jaw_gen.get_bbox(part_for_cut)
                pdx2 = (bb2.xmax - bb2.xmin) + 2 * clearance
                pdy2 = (bb2.ymax - bb2.ymin) + 2 * clearance
                draft_expand = grip_depth * math.tan(math.radians(draft_ang))
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
                    self.status.emit(f"Pocket cut warning: {e}")
                return stock

            self.status.emit("Cutting pockets…")
            jaw_left  = cut_jaw(jaw_left_stock)
            jaw_right = cut_jaw(jaw_right_stock)

            if relief_ang > 0:
                self.status.emit("Adding knife relief…")
                jaw_left  = jaw_gen.add_knife_relief(jaw_left,  mount_h, relief_ang, stock_x, stock_y / 2)
                jaw_right = jaw_gen.add_knife_relief(jaw_right, mount_h, relief_ang, stock_x, stock_y / 2)

            self.status.emit("Adding bolt holes…")
            jaw_left  = jaw_gen.add_bolt_holes(jaw_left,  stock_x, stock_y / 2)
            jaw_right = jaw_gen.add_bolt_holes(jaw_right, stock_x, stock_y / 2)

            self.status.emit("Exporting STLs…")
            out_dir = p['output_dir']
            os.makedirs(out_dir, exist_ok=True)

            part_positioned = part.translate((0, 0, mount_h))

            with tempfile.TemporaryDirectory() as tmpdir:
                part_stl  = os.path.join(tmpdir, "part.stl")
                left_stl  = os.path.join(tmpdir, "jaw_left.stl")
                right_stl = os.path.join(tmpdir, "jaw_right.stl")
                cq.exporters.export(part_positioned, part_stl, exportType="STL")
                cq.exporters.export(jaw_left,  left_stl,  exportType="STL")
                cq.exporters.export(jaw_right, right_stl, exportType="STL")

                preview_out = os.path.join(out_dir, "jaw_preview_gui.png")
                self.status.emit("Rendering preview…")
                self._render(part_stl, left_stl, right_stl, preview_out, mount_h, pdz, grip_depth)

            # Also save STEP
            cq.exporters.export(jaw_left,  os.path.join(out_dir, "jaw_left.step"))
            cq.exporters.export(jaw_right, os.path.join(out_dir, "jaw_right.step"))

            self.done.emit(preview_out)

        except Exception as e:
            self.failed.emit(f"{e}\n\n{traceback.format_exc()}")

    def _render(self, part_stl, left_stl, right_stl, preview_out, mount_h, pdz, grip_depth):
        blender = self._find_blender()
        if not blender:
            self.status.emit("Blender not found — skipping preview.")
            return

        expose_h = pdz - grip_depth
        # Camera distance scales with geometry
        cam_dist = max(300, (pdz + mount_h) * 5)

        script = f"""
import bpy, math

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

def import_stl(path, name, rgb, alpha=1.0):
    bpy.ops.wm.stl_import(filepath=path)
    obj = bpy.context.selected_objects[0]
    obj.name = name
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (rgb[0]/255, rgb[1]/255, rgb[2]/255, 1)
        bsdf.inputs['Roughness'].default_value = 0.25
        bsdf.inputs['Metallic'].default_value = 0.8
        bsdf.inputs['Alpha'].default_value = alpha
    mat.blend_method = 'BLEND' if alpha < 1 else 'OPAQUE'
    if obj.data.materials: obj.data.materials[0] = mat
    else: obj.data.materials.append(mat)
    return obj

# Part — semi-transparent red so you can see jaw pocket
p = import_stl(r'{part_stl}', 'Part', (220, 60, 60), alpha=0.55)

# Jaws — solid aluminium-ish, offset apart so you can see the pocket
jl = import_stl(r'{left_stl}',  'JawLeft',  (160, 165, 175))
jr = import_stl(r'{right_stl}', 'JawRight', (160, 165, 175))
jl.location.y = -6
jr.location.y =  6

# Floor plane
bpy.ops.mesh.primitive_plane_add(size=600, location=(0, 0, -1))
floor = bpy.context.object
floor.name = 'Floor'
floor_mat = bpy.data.materials.new(name='Floor')
floor_mat.use_nodes = True
bsdf_f = floor_mat.node_tree.nodes.get('Principled BSDF')
if bsdf_f:
    bsdf_f.inputs['Base Color'].default_value = (0.06, 0.06, 0.08, 1)
    bsdf_f.inputs['Roughness'].default_value = 0.9
floor.data.materials.append(floor_mat)

# Camera — front-quarter, high enough to see full assembly
bpy.ops.object.camera_add(location=(0, -{cam_dist}, {cam_dist*0.7}))
cam = bpy.context.object
cam.rotation_euler = (math.radians(48), 0, 0)
bpy.context.scene.camera = cam

# World
bpy.context.scene.world.use_nodes = True
bg = bpy.context.scene.world.node_tree.nodes.get('Background')
if bg: bg.inputs['Color'].default_value = (0.05, 0.05, 0.07, 1)

# Key light
bpy.ops.object.light_add(type='SUN', location=(200, -200, 400))
bpy.context.object.data.energy = 5
bpy.context.object.rotation_euler = (math.radians(40), 0, math.radians(25))

# Fill light
bpy.ops.object.light_add(type='AREA', location=(-150, 100, 200))
bpy.context.object.data.energy = 800
bpy.context.object.data.size = 120

# Render
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.samples = 128
bpy.context.scene.cycles.use_denoising = True
bpy.context.scene.render.resolution_x = 1280
bpy.context.scene.render.resolution_y = 960
bpy.context.scene.render.filepath = r'{preview_out}'
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
print('PREVIEW_DONE:{preview_out}')
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(script)
            script_path = f.name

        try:
            r = subprocess.run(
                [blender, '--background', '--python', script_path],
                capture_output=True, text=True, timeout=300
            )
            if r.returncode != 0:
                self.status.emit(f"Blender warning (code {r.returncode})")
        except subprocess.TimeoutExpired:
            self.status.emit("Blender timed out.")
        finally:
            os.unlink(script_path)

    def _find_blender(self):
        for c in ['blender', '/usr/bin/blender', '/usr/local/bin/blender', '/snap/bin/blender']:
            try:
                r = subprocess.run([c, '--version'], capture_output=True, timeout=5)
                if r.returncode == 0:
                    return c
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None


# ── Main Window ────────────────────────────────────────────────────────────

class SoftJawGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Soft Jaw Generator")
        self.setMinimumSize(1100, 750)
        self.input_path  = None
        self.output_dir  = None
        self.worker      = None
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setSpacing(8)

        # ── Left: controls ──────────────────────────────────────────────
        ctrl_scroll = QScrollArea()
        ctrl_scroll.setWidgetResizable(True)
        ctrl_scroll.setFixedWidth(320)
        ctrl_scroll.setFrameShape(QFrame.NoFrame)
        ctrl_widget = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_widget)
        ctrl_layout.setSpacing(6)
        ctrl_scroll.setWidget(ctrl_widget)

        # File section
        file_box = QGroupBox("Input / Output")
        fl = QVBoxLayout(file_box)
        self.file_label = QLabel("No file loaded")
        self.file_label.setWordWrap(True)
        fl.addWidget(self.file_label)
        btn_load = QPushButton("Load STEP File…")
        btn_load.clicked.connect(self._load_file)
        fl.addWidget(btn_load)
        self.outdir_label = QLabel("Output: same folder as input")
        self.outdir_label.setWordWrap(True)
        fl.addWidget(self.outdir_label)
        btn_outdir = QPushButton("Set Output Folder…")
        btn_outdir.clicked.connect(self._set_outdir)
        fl.addWidget(btn_outdir)
        ctrl_layout.addWidget(file_box)

        # Part orientation
        orient_box = QGroupBox("Part Orientation (degrees)")
        ol = QGridLayout(orient_box)
        self.rx = self._spin(ol, "Rotate X:", 0, 0, -180, 180, 1.0,
            tip="Tilt part forward/back. Changes which face becomes the grip surface.")
        self.ry = self._spin(ol, "Rotate Y:", 1, 0, -180, 180, 1.0,
            tip="Tilt part left/right.")
        self.rz = self._spin(ol, "Rotate Z:", 2, 0, -180, 180, 1.0,
            tip="Spin part around vertical axis.")
        ctrl_layout.addWidget(orient_box)

        # Jaw geometry
        jaw_box = QGroupBox("Jaw Geometry")
        jl = QGridLayout(jaw_box)
        self.grip_pct = self._spin(jl, "Grip Depth %:", 0, 0, 5, 80, 40,
            tip="What % of part height the pocket grips. 40% is typical.")
        self.mount_h = self._spin(jl, "Mount Height mm:", 1, 0, 5, 100, 20,
            tip="Height of jaw stock below the part datum.")
        self.stock_margin = self._spin(jl, "Stock Margin mm:", 2, 0, 5, 50, 15,
            tip="How far jaw stock extends beyond part footprint per side.")
        self.clearance = self._spin(jl, "Clearance mm:", 3, 0, 0.0, 2.0, 0.3,
            tip="Gap between pocket wall and part surface.", step=0.05, decimals=2)
        ctrl_layout.addWidget(jaw_box)

        # Anti-lock / relief
        al_box = QGroupBox("Anti-Lock & Relief")
        al = QGridLayout(al_box)
        self.draft_angle = self._spin(al, "Draft Angle °:", 0, 0, 0.0, 8.0, 1.5,
            tip="Pocket wall taper — prevents part from locking in jaws. 1–3° typical.",
            step=0.5, decimals=1)
        self.relief_angle = self._spin(al, "Relief Angle °:", 1, 0, 0.0, 10.0, 3.0,
            tip="Knife chamfer at split line — stops jaw edge digging in.",
            step=0.5, decimals=1)
        ctrl_layout.addWidget(al_box)

        # Buttons
        self.btn_generate = QPushButton("▶  Generate + Preview")
        self.btn_generate.setMinimumHeight(40)
        bold = QFont(); bold.setBold(True)
        self.btn_generate.setFont(bold)
        self.btn_generate.clicked.connect(self._generate)
        ctrl_layout.addWidget(self.btn_generate)

        self.btn_export = QPushButton("Export STEP Files")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export)
        ctrl_layout.addWidget(self.btn_export)

        self.status_label = QLabel("Load a STEP file to begin.")
        self.status_label.setWordWrap(True)
        ctrl_layout.addWidget(self.status_label)

        ctrl_layout.addStretch()
        root_layout.addWidget(ctrl_scroll)

        # ── Right: viewport ─────────────────────────────────────────────
        vp_box = QGroupBox("Preview")
        vp_layout = QVBoxLayout(vp_box)
        self.preview = QLabel("Preview will appear here after generation.")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setMinimumSize(600, 500)
        self.preview.setStyleSheet("background: #111; color: #888; border: 1px solid #333;")
        vp_layout.addWidget(self.preview)
        root_layout.addWidget(vp_box, stretch=1)

    def _spin(self, grid, label, row, col, vmin, vmax, default,
              tip="", step=1.0, decimals=0):
        lbl = QLabel(label)
        lbl.setToolTip(tip)
        if decimals > 0:
            w = QDoubleSpinBox()
            w.setDecimals(decimals)
            w.setSingleStep(step)
        else:
            w = QSpinBox()
            w.setSingleStep(int(step))
        w.setMinimum(vmin)
        w.setMaximum(vmax)
        w.setValue(default)
        w.setToolTip(tip)
        grid.addWidget(lbl, row, col)
        grid.addWidget(w,   row, col + 1)
        return w

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load STEP File", "", "STEP Files (*.step *.stp)")
        if path:
            self.input_path = path
            self.file_label.setText(os.path.basename(path))
            self.output_dir = os.path.dirname(path)
            self.outdir_label.setText(f"Output: {self.output_dir}")
            self.status_label.setText("File loaded. Adjust parameters and hit Generate.")

    def _set_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if d:
            self.output_dir = d
            self.outdir_label.setText(f"Output: {d}")

    def _gather_params(self):
        return {
            'input':        self.input_path,
            'output_dir':   self.output_dir or os.path.dirname(self.input_path),
            'rx':           float(self.rx.value()),
            'ry':           float(self.ry.value()),
            'rz':           float(self.rz.value()),
            'grip_pct':     float(self.grip_pct.value()),
            'mount_height': float(self.mount_h.value()),
            'stock_margin': float(self.stock_margin.value()),
            'clearance':    float(self.clearance.value()),
            'draft_angle':  float(self.draft_angle.value()),
            'relief_angle': float(self.relief_angle.value()),
        }

    def _generate(self):
        if not self.input_path:
            QMessageBox.warning(self, "No File", "Load a STEP file first.")
            return
        if self.worker and self.worker.isRunning():
            return

        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Generating…")
        self.status_label.setText("Starting…")

        self.worker = GenerateWorker(self._gather_params())
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.status.connect(self.status_label.setText)
        self.worker.start()

    def _on_done(self, png_path):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("▶  Generate + Preview")
        self.btn_export.setEnabled(True)
        self.status_label.setText("Done. Adjust and regenerate anytime.")
        if os.path.exists(png_path):
            pix = QPixmap(png_path)
            self.preview.setPixmap(
                pix.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.preview.setText("Render complete — preview file not found.")

    def _on_failed(self, msg):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("▶  Generate + Preview")
        self.status_label.setText("Error — see details.")
        QMessageBox.critical(self, "Generation Failed", msg[:1000])

    def _export(self):
        if not self.output_dir:
            return
        left  = os.path.join(self.output_dir, "jaw_left.step")
        right = os.path.join(self.output_dir, "jaw_right.step")
        if os.path.exists(left) and os.path.exists(right):
            QMessageBox.information(
                self, "Exported",
                f"STEP files saved:\n  {left}\n  {right}"
            )
        else:
            QMessageBox.warning(self, "Not Ready", "Generate jaws first.")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-scale preview on window resize if a pixmap is set
        pix = self.preview.pixmap()
        if pix and not pix.isNull():
            self.preview.setPixmap(
                pix.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = SoftJawGUI()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
