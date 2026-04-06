#!/usr/bin/env python3
"""
PyQt5 + pyqtgraph OpenGL viewer for the split-jaw soft jaw generator.

Drop-in replacement for the earlier GUI. Keeps the same basic workflow,
adds seam clearance, and can preview split debug bodies when present.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from dataclasses import dataclass
from typing import Optional

import cadquery as cq
import numpy as np
from stl import mesh as stl_mesh
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import pyqtgraph.opengl as gl

import soft_jaw_gen_v3 as jaw_gen


@dataclass
class ViewerPayload:
    part_stl: str
    left_stl: str
    right_stl: str
    cutter_stl: str
    left_cutter_stl: str
    right_cutter_stl: str
    left_owned_stl: str
    right_owned_stl: str
    output_dir: str


class GenerateWorker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    def run(self):
        try:
            p = self.params
            self.status.emit("Generating split-jaw negative from part solid…")

            result = jaw_gen.build_jaws(
                input_path=p["input"],
                clearance=p["clearance"],
                relief_angle=p["relief_angle"],
                stock_margin=p["stock_margin"],
                mount_height=p["mount_height"],
                grip_depth=p["grip_depth"],
                orient=(p["rx"], p["ry"], p["rz"]),
                draft_angle=p["draft_angle"],
                seam_clearance=p["seam_clearance"],
            )

            out_dir = p["output_dir"] or os.path.dirname(p["input"])
            os.makedirs(out_dir, exist_ok=True)

            self.status.emit("Exporting STEP files…")
            cq.exporters.export(result.jaw_left, os.path.join(out_dir, "jaw_left.step"))
            cq.exporters.export(result.jaw_right, os.path.join(out_dir, "jaw_right.step"))
            cq.exporters.export(result.grip_cutter, os.path.join(out_dir, "grip_cutter_debug.step"))
            cq.exporters.export(result.left_cutter, os.path.join(out_dir, "left_cutter_debug.step"))
            cq.exporters.export(result.right_cutter, os.path.join(out_dir, "right_cutter_debug.step"))
            cq.exporters.export(result.left_owned, os.path.join(out_dir, "left_owned_debug.step"))
            cq.exporters.export(result.right_owned, os.path.join(out_dir, "right_owned_debug.step"))

            self.status.emit("Preparing OpenGL meshes…")
            tmpdir = tempfile.mkdtemp(prefix="softjaw_gl_")
            part_stl = os.path.join(tmpdir, "part.stl")
            left_stl = os.path.join(tmpdir, "jaw_left.stl")
            right_stl = os.path.join(tmpdir, "jaw_right.stl")
            cutter_stl = os.path.join(tmpdir, "grip_cutter.stl")
            left_cutter_stl = os.path.join(tmpdir, "left_cutter.stl")
            right_cutter_stl = os.path.join(tmpdir, "right_cutter.stl")
            left_owned_stl = os.path.join(tmpdir, "left_owned.stl")
            right_owned_stl = os.path.join(tmpdir, "right_owned.stl")

            cq.exporters.export(result.part_positioned, part_stl, exportType="STL")
            cq.exporters.export(result.jaw_left, left_stl, exportType="STL")
            cq.exporters.export(result.jaw_right, right_stl, exportType="STL")
            cq.exporters.export(result.grip_cutter, cutter_stl, exportType="STL")
            cq.exporters.export(result.left_cutter, left_cutter_stl, exportType="STL")
            cq.exporters.export(result.right_cutter, right_cutter_stl, exportType="STL")
            cq.exporters.export(result.left_owned, left_owned_stl, exportType="STL")
            cq.exporters.export(result.right_owned, right_owned_stl, exportType="STL")

            self.done.emit(
                ViewerPayload(
                    part_stl=part_stl,
                    left_stl=left_stl,
                    right_stl=right_stl,
                    cutter_stl=cutter_stl,
                    left_cutter_stl=left_cutter_stl,
                    right_cutter_stl=right_cutter_stl,
                    left_owned_stl=left_owned_stl,
                    right_owned_stl=right_owned_stl,
                    output_dir=out_dir,
                )
            )
        except Exception as e:
            self.failed.emit(f"{e}\n\n{traceback.format_exc()}")


class GLViewer(gl.GLViewWidget):
    def __init__(self):
        super().__init__()
        self.setCameraPosition(distance=250, elevation=22, azimuth=-35)
        self.setBackgroundColor((18, 20, 24))
        self._items = []
        self._add_grid()

    def _add_grid(self):
        grid = gl.GLGridItem()
        grid.scale(10, 10, 1)
        grid.translate(0, 0, 0)
        self.addItem(grid)
        self._items.append(grid)

    def clear_meshes(self):
        for item in list(self._items)[1:]:
            try:
                self.removeItem(item)
            except Exception:
                pass
            self._items.remove(item)

    def _mesh_from_stl(self, path: str) -> np.ndarray:
        data = stl_mesh.Mesh.from_file(path)
        return np.array(data.vectors, dtype=float)

    def add_stl(self, path: str, color=(0.7, 0.7, 0.75, 1.0), smooth=False):
        verts = self._mesh_from_stl(path)
        item = gl.GLMeshItem(
            vertexes=verts,
            drawEdges=True,
            drawFaces=True,
            smooth=smooth,
            shader="shaded",
            color=color,
        )
        self.addItem(item)
        self._items.append(item)
        return item

    def load_payload(self, payload: ViewerPayload):
        self.clear_meshes()
        self.add_stl(payload.left_stl, color=(0.72, 0.74, 0.78, 1.0))
        self.add_stl(payload.right_stl, color=(0.72, 0.74, 0.78, 1.0))
        self.add_stl(payload.part_stl, color=(0.85, 0.25, 0.25, 0.45))
        self.add_stl(payload.left_cutter_stl, color=(0.25, 0.45, 0.95, 0.22))
        self.add_stl(payload.right_cutter_stl, color=(0.25, 0.85, 0.35, 0.22))
        self.add_stl(payload.left_owned_stl, color=(1.00, 0.70, 0.10, 0.18))
        self.add_stl(payload.right_owned_stl, color=(1.00, 0.95, 0.10, 0.18))


class SoftJawGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Soft Jaw Generator — OpenGL")
        self.resize(1400, 860)
        self.input_path: Optional[str] = None
        self.output_dir: Optional[str] = None
        self.worker: Optional[GenerateWorker] = None
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        control_panel = QWidget()
        controls = QVBoxLayout(control_panel)
        controls.setSpacing(8)
        control_panel.setFixedWidth(380)

        io_box = QGroupBox("Input / Output")
        io_layout = QVBoxLayout(io_box)
        self.file_label = QLabel("No STEP file loaded")
        self.file_label.setWordWrap(True)
        self.out_label = QLabel("Output: same folder as input")
        self.out_label.setWordWrap(True)
        load_btn = QPushButton("Load STEP File…")
        load_btn.clicked.connect(self._load_file)
        out_btn = QPushButton("Set Output Folder…")
        out_btn.clicked.connect(self._set_output_dir)
        io_layout.addWidget(self.file_label)
        io_layout.addWidget(load_btn)
        io_layout.addWidget(self.out_label)
        io_layout.addWidget(out_btn)
        controls.addWidget(io_box)

        orient_box = QGroupBox("Orientation")
        orient_layout = QFormLayout(orient_box)
        self.rx = self._dspin(-180, 180, 0.0, 1.0)
        self.ry = self._dspin(-180, 180, 0.0, 1.0)
        self.rz = self._dspin(-180, 180, 0.0, 1.0)
        orient_layout.addRow("Rotate X", self.rx)
        orient_layout.addRow("Rotate Y", self.ry)
        orient_layout.addRow("Rotate Z", self.rz)
        controls.addWidget(orient_box)

        jaw_box = QGroupBox("Jaw Parameters")
        jaw_layout = QFormLayout(jaw_box)
        self.mount_height = self._dspin(2, 200, 20.0, 0.5)
        self.grip_depth = self._dspin(0.1, 500, 12.0, 0.5)
        self.stock_margin = self._dspin(0, 150, 15.0, 0.5)
        self.clearance = self._dspin(0, 3, 0.25, 0.05)
        self.draft_angle = self._dspin(0, 8, 1.0, 0.1)
        self.relief_angle = self._dspin(0, 20, 3.0, 0.25)
        self.seam_clearance = self._dspin(0, 5, 0.0, 0.05)
        jaw_layout.addRow("Mount height", self.mount_height)
        jaw_layout.addRow("Grip depth", self.grip_depth)
        jaw_layout.addRow("Stock margin", self.stock_margin)
        jaw_layout.addRow("Clearance", self.clearance)
        jaw_layout.addRow("Draft angle", self.draft_angle)
        jaw_layout.addRow("Relief angle", self.relief_angle)
        jaw_layout.addRow("Seam clearance", self.seam_clearance)
        controls.addWidget(jaw_box)

        self.status_label = QLabel("Load a STEP file to begin.")
        self.status_label.setWordWrap(True)
        controls.addWidget(self.status_label)

        self.generate_btn = QPushButton("Generate / Preview")
        self.generate_btn.clicked.connect(self._generate)
        controls.addWidget(self.generate_btn)
        controls.addStretch(1)

        self.viewer = GLViewer()
        info_box = QLabel(
            "Gray = jaws\n"
            "Red = positioned part\n"
            "Blue/Green = left/right cutters\n"
            "Orange/Yellow = left/right owned grip regions"
        )
        info_box.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(self.viewer, 1)
        right_layout.addWidget(info_box)

        layout.addWidget(control_panel)
        layout.addWidget(right_panel, 1)

    def _dspin(self, lo, hi, val, step):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(3 if step < 0.1 else 2)
        w.setSingleStep(step)
        w.setValue(val)
        return w

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open STEP", "", "STEP Files (*.step *.stp)")
        if not path:
            return
        self.input_path = path
        self.file_label.setText(path)
        self.status_label.setText("STEP loaded. Ready to generate.")

    def _set_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not path:
            return
        self.output_dir = path
        self.out_label.setText(f"Output: {path}")

    def _generate(self):
        if not self.input_path:
            QMessageBox.warning(self, "No file", "Load a STEP file first.")
            return

        params = {
            "input": self.input_path,
            "output_dir": self.output_dir,
            "rx": self.rx.value(),
            "ry": self.ry.value(),
            "rz": self.rz.value(),
            "mount_height": self.mount_height.value(),
            "grip_depth": self.grip_depth.value(),
            "stock_margin": self.stock_margin.value(),
            "clearance": self.clearance.value(),
            "draft_angle": self.draft_angle.value(),
            "relief_angle": self.relief_angle.value(),
            "seam_clearance": self.seam_clearance.value(),
        }

        self.generate_btn.setEnabled(False)
        self.status_label.setText("Working…")
        self.worker = GenerateWorker(params)
        self.worker.status.connect(self.status_label.setText)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_done(self, payload: ViewerPayload):
        self.viewer.load_payload(payload)
        self.generate_btn.setEnabled(True)
        self.status_label.setText(f"Done. STEP files written to: {payload.output_dir}")

    def _on_failed(self, msg: str):
        self.generate_btn.setEnabled(True)
        self.status_label.setText("Generation failed.")
        QMessageBox.critical(self, "Generation failed", msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SoftJawGUI()
    win.show()
    sys.exit(app.exec_())
