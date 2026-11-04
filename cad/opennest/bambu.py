# SPDX-License-Identifier: CERN-OHL-P-2.0
"""Write a Bambu Studio project for the H2D from the template settings and a new mesh."""
import io
import json
import re
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw

from . import spec as s
from .plan import Plan

OBJECT_PART = "3D/Objects/object_4.model"
BLOCK_SEAM = "8"  # Bambu's code for a whole triangle painted as a seam blocker
FILAMENT_RGB = np.array((0x00, 0x86, 0xD6))


def _pocket_facing(mesh, plan: Plan, seat_z: float):
    """Triangles on the tab faces a plate can touch, so no seam bump sits where the plate runs."""
    c, n = mesh.triangles_center, mesh.face_normals
    x, y = np.abs(c[:, 0]), np.abs(c[:, 1])
    corner = (x >= plan.pocket_x / 2 - 0.05) & (n[:, 0] * np.sign(c[:, 0]) < -0.2)
    side = (y >= plan.pocket_y / 2 - 0.1) & (x > s.SIDE_TAB_X[0] - 0.1) & (x < s.SIDE_TAB_X[1] + 0.1) & (n[:, 1] * np.sign(c[:, 1]) < -0.2)
    return (c[:, 2] > seat_z) & (corner | side)


def _object_model(head: str, mesh, blocked) -> str:
    lines = [head]
    lines += [f'     <vertex x="{x:.9g}" y="{y:.9g}" z="{z:.9g}"/>' for x, y, z in mesh.vertices]
    lines.append("    </vertices>\n    <triangles>")
    lines += [f'     <triangle v1="{a}" v2="{b}" v3="{c}"' + (f' paint_seam="{BLOCK_SEAM}"' if off else "") + "/>" for (a, b, c), off in zip(mesh.faces, blocked)]
    lines.append("    </triangles>\n   </mesh>\n  </object>\n </resources>\n <build/>\n</model>\n")
    return "\n".join(lines)


def _thumbnail(mesh, view, up, size: int) -> bytes:
    """Flat-shaded orthographic picture of the plate, painted back to front."""
    view = np.asarray(view, float) / np.linalg.norm(view)
    right = np.cross(view, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, view)
    tris = mesh.triangles
    u, v, depth = tris @ right, tris @ true_up, tris @ view
    span = max(np.ptp(u), np.ptp(v)) * 1.06
    scale = size / span
    px = (u - (u.max() + u.min() - span) / 2) * scale
    py = ((v.max() + v.min() + span) / 2 - v) * scale
    light = np.array([-0.45, -0.55, 1.0])
    light /= np.linalg.norm(light)
    shade = 0.45 + 0.55 * np.clip(mesh.face_normals @ light, 0, 1)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for i in np.argsort(-depth.mean(axis=1)):
        rgb = tuple(int(c) for c in FILAMENT_RGB * shade[i])
        draw.polygon(list(zip(px[i], py[i])), fill=(*rgb, 255))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def write_project(plan: Plan, stl_path: Path, out_path: Path) -> None:
    with zipfile.ZipFile(s.BAMBU_TEMPLATE) as z:
        names = z.namelist()
        parts = {n: z.read(n) for n in names}
    mesh = trimesh.load_mesh(stl_path)
    mesh.merge_vertices(digits_vertex=4)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    if not (mesh.is_watertight and mesh.is_winding_consistent):
        raise RuntimeError("the mesh is not watertight, so no Bambu project was written")
    lift = s.TOP / 2
    mesh.apply_translation((0, 0, -lift))  # the project keeps the mesh centred on Z and its build item lifts it onto the bed
    blocked = _pocket_facing(mesh, plan, s.SEAT - lift)
    template = parts[OBJECT_PART].decode()
    parts[OBJECT_PART] = _object_model(template[: template.index("<vertices>") + len("<vertices>")], mesh, blocked).encode()
    settings = parts["Metadata/model_settings.config"].decode().replace("NEST_NAME", "nest")
    parts["Metadata/model_settings.config"] = re.sub(r'face_count="\d+"', f'face_count="{len(mesh.faces)}"', settings).encode()
    plate = json.loads(parts["Metadata/plate_1.json"])
    plate["bbox_objects"][0]["name"] = "nest.stl"
    parts["Metadata/plate_1.json"] = json.dumps(plate).encode()
    root = parts["3D/3dmodel.model"].decode()
    parts["3D/3dmodel.model"] = re.sub(r'(<metadata name="ModificationDate">)[^<]*', rf"\g<1>{date.today().isoformat()}", root).encode()
    iso = _thumbnail(mesh, (-0.45, 0.65, -0.6), (0, 0, 1), 512)
    parts["Metadata/plate_1.png"] = iso
    parts["Metadata/plate_no_light_1.png"] = iso
    parts["Metadata/plate_1_small.png"] = _thumbnail(mesh, (-0.45, 0.65, -0.6), (0, 0, 1), 128)
    parts["Metadata/top_1.png"] = _thumbnail(mesh, (0, 0, -1), (0, 1, 0), 512)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.writestr(name, parts[name])


def write_plain_3mf(stl_path: Path, out_path: Path) -> None:
    trimesh.load_mesh(stl_path).export(out_path, file_type="3mf")
