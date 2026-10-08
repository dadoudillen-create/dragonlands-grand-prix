"""Skyrim Special Edition NIF writer (20.2.0.7, user version 12, BS version 100): static BSTriShape model.

Vertex layout matches vanilla SE static meshes (e.g. elderscrollfurled.nif): descriptor 0x0001b00000650407 ->
28-byte vertices: position float3 + bitangent.x float, UV half2, normal ubyte3 + bitangent.y, tangent ubyte3 +
bitangent.z. Node/shader/texture-set blocks are the same as Skyrim LE (see skynif.py).
"""
import struct

import numpy as np

from skynif import Nif

BS_VERSION_SE = 100
VERTEX_DESC = 0x0001B00000650407


def _ubyte(v):
    return np.clip(np.round((v + 1.0) * 127.5), 0, 255).astype(np.uint8)


class NifSE(Nif):
    def tri_shape_se(self, idx, name, shader, verts, normals, tangents, bitangents, uvs, tris):
        n, nt = len(verts), len(tris)
        assert n <= 65535 and nt <= 65535
        center = (verts.min(0) + verts.max(0)) / 2
        radius = float(np.linalg.norm(verts - center, axis=1).max())
        vd = np.zeros(n, dtype=[("pos", "<f4", 3), ("bx", "<f4"), ("uv", "<f2", 2), ("nrm", "u1", 3), ("by", "u1"),
                                ("tan", "u1", 3), ("bz", "u1")])
        vd["pos"] = verts; vd["bx"] = bitangents[:, 0]; vd["uv"] = uvs
        vd["nrm"] = _ubyte(normals); vd["by"] = _ubyte(bitangents[:, 1])
        vd["tan"] = _ubyte(tangents); vd["bz"] = _ubyte(bitangents[:, 2])
        assert vd.itemsize == 28
        body = self.av_object(name)
        body += struct.pack("<3ff", *center, radius)                  # bounding sphere
        body += struct.pack("<iii", -1, shader, -1)                   # skin, shader, alpha
        body += struct.pack("<QHHI", VERTEX_DESC, nt, n, n * 28 + nt * 6)
        body += vd.tobytes() + tris.astype("<u2").tobytes()
        body += struct.pack("<I", 0)                                  # particle data size
        self.set(idx, body)

    def write(self, path, roots=(0,)):
        import skynif
        old = skynif.BS_VERSION
        skynif.BS_VERSION = BS_VERSION_SE
        try:
            super().write(path, roots)
        finally:
            skynif.BS_VERSION = old


def build_static_se(path, shapes, z_offset=0.0):
    nif = NifSE()
    root = nif.add("BSFadeNode")
    children = []
    for s in shapes:
        shape = nif.add("BSTriShape"); shader = nif.add("BSLightingShaderProperty"); texset = nif.add("BSShaderTextureSet")
        verts = s["verts"] + np.array([0, 0, z_offset], dtype=np.float32)
        nif.tri_shape_se(shape, s["name"], shader, verts, s["normals"], s["tangents"], s["bitangents"], s["uvs"], s["tris"])
        nif.lighting_shader(shader, texset)
        nif.texture_set(texset, s["textures"])
        children.append(shape)
    nif.node(root, "DLGP_Car", children)
    nif.write(path)
