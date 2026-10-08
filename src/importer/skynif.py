"""Minimal Skyrim LE NIF writer (20.2.0.7, user version 12, BS version 83).

Writes a static model: BSFadeNode root -> NiTriShape children, each with NiTriShapeData,
BSLightingShaderProperty and BSShaderTextureSet. Layout follows niftools nif.xml for Skyrim LE.
"""
import struct

import numpy as np

VERSION = 0x14020007
USER_VERSION = 12
BS_VERSION = 83


def sized(s):
    b = s.encode("ascii")
    return struct.pack("<I", len(b)) + b


def export_string(s):
    b = s.encode("ascii") + b"\0"
    return struct.pack("<B", len(b)) + b


class Nif:
    def __init__(self):
        self.blocks = []  # (type, bytes-builder)
        self.strings = []

    def string(self, s):
        if s is None:
            return struct.pack("<i", -1)
        if s not in self.strings:
            self.strings.append(s)
        return struct.pack("<i", self.strings.index(s))

    def add(self, type_name):
        self.blocks.append([type_name, b""])
        return len(self.blocks) - 1

    def set(self, idx, data):
        self.blocks[idx][1] = data

    # --- block bodies -------------------------------------------------------------------
    def object_net(self, name):
        return self.string(name) + struct.pack("<I", 0) + struct.pack("<i", -1)  # extra data, controller

    def av_object(self, name, flags=14):
        rot = np.eye(3, dtype="<f4").tobytes()
        return (self.object_net(name) + struct.pack("<I", flags) + struct.pack("<3f", 0, 0, 0) + rot +
                struct.pack("<f", 1.0) + struct.pack("<i", -1))  # no collision object

    def node(self, idx, name, children):
        self.set(idx, self.av_object(name) + struct.pack("<I", len(children)) +
                 b"".join(struct.pack("<i", c) for c in children) + struct.pack("<I", 0))

    def tri_shape(self, idx, name, data, shader):
        body = self.av_object(name)
        body += struct.pack("<ii", data, -1)                 # data, skin instance
        body += struct.pack("<IiB", 0, -1, 0)               # material data: 0 materials, active -1, dirty
        body += struct.pack("<ii", shader, -1)              # shader property, alpha property
        self.set(idx, body)

    def tri_shape_data(self, idx, verts, normals, tangents, bitangents, uvs, tris):
        n = len(verts)
        assert n <= 65535 and len(tris) <= 65535
        center = (verts.min(0) + verts.max(0)) / 2
        radius = float(np.linalg.norm(verts - center, axis=1).max())
        body = struct.pack("<i", 0)                          # group id
        body += struct.pack("<HBB", n, 0, 0)                 # num vertices, keep, compress flags
        body += struct.pack("<B", 1) + verts.astype("<f4").tobytes()
        body += struct.pack("<H", 0x1001)                    # BS data flags: has UV + tangents (as vanilla)
        body += struct.pack("<I", 0)                         # material CRC (BSVER > 34)
        body += struct.pack("<B", 1) + normals.astype("<f4").tobytes()
        body += tangents.astype("<f4").tobytes() + bitangents.astype("<f4").tobytes()
        body += struct.pack("<3ff", *center, radius)
        body += struct.pack("<B", 0)                         # no vertex colours
        body += uvs.astype("<f4").tobytes()
        body += struct.pack("<H", 0x4000)                    # consistency: CT_STATIC
        body += struct.pack("<i", -1)                        # additional data
        body += struct.pack("<H", len(tris))                 # num triangles
        body += struct.pack("<IB", len(tris) * 3, 1) + tris.astype("<u2").tobytes()
        body += struct.pack("<H", 0)                         # match groups
        self.set(idx, body)

    def lighting_shader(self, idx, texset, glossiness=80.0, spec=1.0):
        body = struct.pack("<I", 0)                          # skyrim shader type: default
        body += self.object_net(None)
        body += struct.pack("<II", 0x82400301, 0x00008001)   # SLSF1 (specular, shadows, zbuffer test), SLSF2 (zwrite)
        body += struct.pack("<2f2f", 0, 0, 1, 1)             # uv offset, uv scale
        body += struct.pack("<i", texset)
        body += struct.pack("<3ff", 0, 0, 0, 0)              # emissive colour, multiple
        body += struct.pack("<I", 3)                         # texture clamp: wrap s/t
        body += struct.pack("<fff", 1.0, 0.0, glossiness)    # alpha, refraction, glossiness
        body += struct.pack("<3ff", 1, 1, 1, spec)           # specular colour, strength
        body += struct.pack("<ff", 0.3, 2.0)                 # lighting effect 1, 2
        self.set(idx, body)

    def texture_set(self, idx, textures):
        tex = (list(textures) + [""] * 9)[:9]
        self.set(idx, struct.pack("<i", 9) + b"".join(sized(t) for t in tex))

    # --- file ---------------------------------------------------------------------------
    def write(self, path, roots=(0,)):
        types = []
        for t, _ in self.blocks:
            if t not in types:
                types.append(t)
        h = b"Gamebryo File Format, Version 20.2.0.7\n"
        h += struct.pack("<IBII", VERSION, 1, USER_VERSION, len(self.blocks))
        h += struct.pack("<I", BS_VERSION) + export_string("DragonlandsGP") + export_string("") + export_string("")
        h += struct.pack("<H", len(types)) + b"".join(sized(t) for t in types)
        h += b"".join(struct.pack("<H", types.index(t)) for t, _ in self.blocks)
        h += b"".join(struct.pack("<I", len(b)) for _, b in self.blocks)
        h += struct.pack("<II", len(self.strings), max([len(s) for s in self.strings] or [0]))
        h += b"".join(sized(s) for s in self.strings)
        h += struct.pack("<I", 0)                            # groups
        body = b"".join(b for _, b in self.blocks)
        foot = struct.pack("<I", len(roots)) + b"".join(struct.pack("<i", r) for r in roots)
        with open(path, "wb") as f:
            f.write(h + body + foot)


def build_static(path, shapes):
    """shapes: list of dict(name, verts, normals, tangents, bitangents [N,3], uvs[N,2], tris[M,3], textures)."""
    nif = Nif()
    root = nif.add("BSFadeNode")
    children = []
    for s in shapes:
        shape = nif.add("NiTriShape"); data = nif.add("NiTriShapeData")
        shader = nif.add("BSLightingShaderProperty"); texset = nif.add("BSShaderTextureSet")
        nif.tri_shape(shape, s["name"], data, shader)
        nif.tri_shape_data(data, s["verts"], s["normals"], s["tangents"], s["bitangents"], s["uvs"], s["tris"])
        nif.lighting_shader(shader, texset)
        nif.texture_set(texset, s["textures"])
        children.append(shape)
    nif.node(root, "DLGP_Car", children)
    nif.write(path)


# --- skinned (rigid to one skeleton bone) ---------------------------------------------------------------------
SLSF1_SKINNED = 0x2
IDENTITY_TRANSFORM = np.eye(3, dtype="<f4").tobytes() + struct.pack("<3ff", 0, 0, 0, 1.0)


class SkinnedNif(Nif):
    def dismember(self, idx, data, partition, root, bone):
        body = struct.pack("<iiiI", data, partition, root, 1) + struct.pack("<i", bone)
        body += struct.pack("<I", 1) + struct.pack("<hH", 257, 30)   # one partition, as vanilla horse.nif
        self.set(idx, body)

    def skin_data(self, idx, nverts, center, radius):
        body = IDENTITY_TRANSFORM + struct.pack("<IB", 1, 1)         # one bone, has vertex weights
        body += IDENTITY_TRANSFORM + struct.pack("<3ff", *center, radius)
        body += struct.pack("<H", nverts)
        body += b"".join(struct.pack("<Hf", i, 1.0) for i in range(nverts))
        self.set(idx, body)

    def skin_partition(self, idx, nverts, tris):
        body = struct.pack("<I", 1)
        body += struct.pack("<5H", nverts, len(tris), 1, 0, 4)       # verts, tris, bones, strips, weights/vertex
        body += struct.pack("<H", 0)                                  # bones[0] = skin bone 0
        body += struct.pack("<B", 1) + np.arange(nverts, dtype="<u2").tobytes()  # vertex map (identity)
        w = np.zeros((nverts, 4), "<f4"); w[:, 0] = 1.0
        body += struct.pack("<B", 1) + w.tobytes()                    # vertex weights
        body += struct.pack("<B", 1) + tris.astype("<u2").tobytes()   # has faces, triangles
        body += struct.pack("<B", 1) + np.zeros((nverts, 4), "u1").tobytes()  # bone indices
        body += struct.pack("<BB", 0, 0)                              # LOD level, global VB
        self.set(idx, body)

    def skinned_shape(self, idx, name, data, skin, shader):
        body = self.av_object(name)
        body += struct.pack("<ii", data, skin)
        body += struct.pack("<IiB", 0, -1, 0)
        body += struct.pack("<ii", shader, -1)
        self.set(idx, body)


def build_skinned(path, shapes, bone_name, z_offset=0.0):
    """Car rigidly skinned to one bone of an actor skeleton (e.g. 'NPC Root [Root]' of the horse)."""
    nif = SkinnedNif()
    root = nif.add("NiNode")
    bone = nif.add("NiNode")
    children = [bone]
    for s in shapes:
        verts = s["verts"] + np.array([0, 0, z_offset], dtype=np.float32)
        center = (verts.min(0) + verts.max(0)) / 2
        radius = float(np.linalg.norm(verts - center, axis=1).max())
        shape = nif.add("NiTriShape"); data = nif.add("NiTriShapeData")
        skin = nif.add("BSDismemberSkinInstance"); sdata = nif.add("NiSkinData"); part = nif.add("NiSkinPartition")
        shader = nif.add("BSLightingShaderProperty"); texset = nif.add("BSShaderTextureSet")
        nif.skinned_shape(shape, s["name"], data, skin, shader)
        nif.tri_shape_data(data, verts, s["normals"], s["tangents"], s["bitangents"], s["uvs"], s["tris"])
        nif.dismember(skin, sdata, part, root, bone)
        nif.skin_data(sdata, len(verts), center, radius)
        nif.skin_partition(part, len(verts), s["tris"])
        nif.lighting_shader(shader, texset)
        sh = bytearray(nif.blocks[shader][1])
        sf1_at = 4 + 4 + 4 + 4                                        # shader type, name, extra count, controller
        struct.pack_into("<I", sh, sf1_at, struct.unpack_from("<I", sh, sf1_at)[0] | SLSF1_SKINNED)
        nif.set(shader, bytes(sh))
        nif.texture_set(texset, s["textures"])
        children.append(shape)
    nif.set(bone, nif.av_object(bone_name) + struct.pack("<II", 0, 0))
    nif.node(root, "DLGP_CarMount", children)
    nif.write(path)
