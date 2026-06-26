"""UDG PC .bnc -> .obj extractor.

Handles the "simple" geometry format (a flat run of 48-byte face records), which
covers a large share of props/characters (~267 clean in the first archive). The
"complex" format (records interleaved with the vertex groups) is documented and
validated in docs/FORMAT.md but its per-model parameter detection is still WIP, so
those models may export partial/messy meshes for now.

Format (reverse-engineered, validated vs The Models Resource ground truth):
  - optional 16-byte wrapper (magic ac 65 12 fe) then 'PSCa' data
  - vertex: 16-byte stride = [4-byte marker][3x float32 position]; axis -> (x, z, -y)
  - face record: 48 bytes; first 3 uint32 = triangle (indices into the submesh vtx buffer),
                 uint32 at +16 == 9 (count of trailing per-corner uint16 strip data)
  - UVs: a 40-byte-strided record array starts right after the face records; each face's
         record index is strip[1] (the uint16 at face_record+22), so recoff = base + X*40.
         Each record holds 3 per-corner (u,v); V is flipped (obj_v = 1 - file_v). Shared
         records (X reused) handle duplicate faces for free. Emits an .obj + .mtl.
  - geometry is laid out as submeshes: a vertex run followed by its 48-byte face records
"""
import struct, sys, os, re

def u32(d, o): return struct.unpack_from('<I', d, o)[0]
def u16(d, o): return struct.unpack_from('<H', d, o)[0]
def f32(d, o): return struct.unpack_from('<f', d, o)[0]

def find_descriptor(d):
    """First node descriptor: uint16 vcount, uint16 fcount, then 00 ff ff ff.
    Its vcount is the authoritative vertex count for the (main) node."""
    for o in range(0, len(d) - 8):
        if d[o+4:o+8] == b'\x00\xff\xff\xff' and 0 < u16(d, o) < 8000 and 0 < u16(d, o+2) < 8000:
            return o
    return None

def psca_blob(data):
    if data[:4] == b'\xac\x65\x12\xfe':       # wrapper -> skip 16 bytes
        return data[16:]
    return data

def is_marker(m):
    # vertex slots begin with uint32 "00 0X 00 00"; X is a per-submesh id that
    # increments (0x100, 0x200, 0x300 ...), so a change in value = a new submesh.
    return 0 < m < 0x10000 and m % 256 == 0

def _good_pos(d, o):
    p = [f32(d, o+4), f32(d, o+8), f32(d, o+12)]
    return all(abs(v) < 1e3 for v in p) and any(p)

def find_vertex_runs(d):
    """contiguous runs of 16-byte vertex records sharing one submesh marker."""
    runs = []
    o = 0
    N = len(d)
    while o + 16 <= N:
        m = u32(d, o)
        if is_marker(m) and _good_pos(d, o):
            start = o; cnt = 0
            while o + 16 <= N and u32(d, o) == m and _good_pos(d, o):
                cnt += 1; o += 16
            if cnt >= 3:
                runs.append((start, cnt))
        else:
            o += 4
    return runs

def _rec_to_tris(d, o, nv, out):
    """one 48-byte record -> triangle (a,b,c) [+ (a,c,d) if d is a distinct quad corner]."""
    a, b, c, e = u32(d, o), u32(d, o+4), u32(d, o+8), u32(d, o+12)
    if a < nv and b < nv and c < nv and len({a, b, c}) == 3:
        out.append((a, b, c))
        if e not in (a, b, c) and e < nv:
            out.append((a, c, e))

def _is_face_rec(d, o, nv):
    a, b, c, e = u32(d, o), u32(d, o+4), u32(d, o+8), u32(d, o+12)
    return (max(a, b, c) < nv and len({a, b, c}) == 3 and b'\xff\xff' in d[o+16:o+48])

def _face_block(d, nv, vend, fcount):
    """Offset where the `fcount` 48-byte face records begin. Simple models keep
    them contiguously at `vend`; complex/skinned models store them as a separate
    block elsewhere (located as the longest run of valid records, plus any
    small-gap preceding run). Returns None if no records found."""
    N = len(d)
    valid = sum(1 for i in range(fcount)
                if vend + i*48 + 48 <= N and _is_face_rec(d, vend + i*48, nv))
    if fcount and _is_face_rec(d, vend, nv) and valid / fcount > 0.9:
        return vend                                     # truly contiguous at vend
    runs, o = [], vend
    while o + 48 <= N:
        if _is_face_rec(d, o, nv):
            s = o; c = 0
            while o + 48 <= N and _is_face_rec(d, o, nv):
                c += 1; o += 48
            if c >= 8:
                runs.append((s, c))
        else:
            o += 4
    if not runs:
        return None
    start = max(runs, key=lambda r: r[1])[0]
    changed = True
    while changed:                                      # chain in small-gap preceding runs
        changed = False
        for s, c in runs:
            if 0 < start - (s + c*48) <= 64:
                start = s; changed = True
    return start

def _iter_face_recs(d, nv, start, fcount):
    """Yield the offset of each of `fcount` 48-byte face records from `start`,
    tolerating small gaps between sub-blocks."""
    N, o, n = len(d), start, 0
    while o + 48 <= N and n < fcount:
        if _is_face_rec(d, o, nv):
            yield o; o += 48; n += 1
        else:
            o += 4

def find_faces(d, nv, vend, fcount):
    """Triangles for `fcount` face records. Each record's first four uint32 are
    a,b,c,d -> triangle (a,b,c) plus (a,c,d) when d is a distinct quad corner."""
    out = []
    start = _face_block(d, nv, vend, fcount)
    if start is None:
        return out
    for ro in _iter_face_recs(d, nv, start, fcount):
        _rec_to_tris(d, ro, nv, out)
    return out

def _faces_end(d, vcount, vend):
    """End of the contiguous 48-byte face-record block (start of UV data)."""
    o = vend
    while o + 48 <= len(d):
        if _is_face_rec(d, o, vcount):
            o += 48
        else:
            break
    return o

def _is_uv(d, o):
    u, v = f32(d, o), f32(d, o+4)
    return u == u and v == v and 0.0 <= u <= 1.001 and 0.0 <= v <= 1.001

def _strict_uv(d, o):
    # strictly-interior pair: rejects (0,0) padding, dim markers (256/128) and the
    # 4-byte-misaligned (0, u) reads that would shift the record base.
    u, v = f32(d, o), f32(d, o+4)
    return u == u and v == v and 0.005 < u < 0.999 and 0.005 < v < 0.999

def _find_uv_base(d, fend):
    """The UV records are a 40-byte-strided array; find record 0 = first triplet
    of three strictly-interior (u,v) pairs after the face records (skips the
    (0,0)/dim header)."""
    o = fend
    while o + 24 <= len(d):
        if _strict_uv(d, o) and _strict_uv(d, o+8) and _strict_uv(d, o+16):
            return o
        o += 4
    return None

def _rec_uvs(d, base, X):
    """UVs for a face = the 40-byte record at base + X*40 (X = strip[1]).
    Three per-corner (u,v); V is file-flipped to OBJ convention."""
    o = base + X*40
    if o + 24 > len(d):
        return None
    uv = [(f32(d, o+k*8), 1.0 - f32(d, o+k*8+4)) for k in range(3)]
    if not all(_is_uv(d, o+k*8) for k in range(3)):
        return None
    return uv

def _find_bone_base(d, vlimit):
    """Skinned characters store the vertices in bone-LOCAL space; to un-fold them
    each vertex is offset by its bone's world bind-position. Those positions are a
    Vector3[] array — locate it by the spine signature: 6 consecutive entries
    (WAIST..HEAD) with strictly increasing height (file Z) and centered on X.
    Returns the array offset, or None for non-skinned props."""
    m = re.search(rb'NULL\x00', d)
    limit = min(m.start() if m else vlimit, vlimit)
    o = 0x40
    while o + 6*12 <= limit:
        zs = [f32(d, o+k*12+8) for k in range(6)]
        xs = [f32(d, o+k*12) for k in range(6)]
        if (all(v == v for v in zs+xs)
                and all(zs[k+1] > zs[k] + 0.02 for k in range(5))
                and (zs[5] - zs[0]) > 0.35
                and all(abs(x) < 0.12 for x in xs) and zs[0] > 0.05):
            return o
        o += 4
    return None

def _bone_positions(d, base):
    """Read the contiguous Vector3 bind-position array starting at `base`."""
    out, o = [], base
    while o + 12 <= len(d):
        x, y, z = f32(d, o), f32(d, o+4), f32(d, o+8)
        if x == x and y == y and z == z and max(abs(x), abs(y), abs(z)) < 8:
            out.append((x, y, z)); o += 12
        else:
            break
    return out

def extract(path, out_path, scale=100.0):
    d = psca_blob(open(path, 'rb').read())
    desc = find_descriptor(d)
    runs = find_vertex_runs(d)
    verts_all, tris = [], []          # tris: ((a,b,c), uv3 | None)
    if desc is not None and runs:
        # The (main node's) vertices are a single contiguous block of exactly
        # `vcount` 16-byte records, starting at the first vertex run. Read exactly
        # that many (the descriptor count is authoritative; the heuristic run
        # splitter over/under-counts). Face records then index globally into it.
        vcount = u16(d, desc)
        fcount = u16(d, desc+2)
        geom = min(s for s, _ in runs)
        vcount = min(vcount, max(0, (len(d) - geom) // 16))   # never read past the buffer
        # Skinned characters: offset each vertex by its bone's bind position (the
        # vertex marker's 2nd byte is the bone index; the array skips nodes 0,1 =
        # NULL/RESERVE, hence index-2). Props have no skeleton -> read positions as-is.
        bbase = _find_bone_base(d, geom)
        bones = _bone_positions(d, bbase) if bbase is not None else None
        if bones:
            verts_all = []
            for i in range(vcount):
                vo = geom + i*16
                bi = ((u32(d, vo) >> 8) & 0xff) - 2
                bx, by, bz = bones[bi] if 0 <= bi < len(bones) else (0.0, 0.0, 0.0)
                verts_all.append((f32(d, vo+4)+bx, f32(d, vo+12)+bz, -(f32(d, vo+8)+by)))
        else:
            verts_all = [(f32(d, geom+i*16+4), f32(d, geom+i*16+12), -f32(d, geom+i*16+8))
                         for i in range(vcount)]
        vend = geom + vcount*16
        # Locate the face-record block (vend for simple models, a separate block
        # for complex/skinned ones). Read each record's UV pointer (strip[1]) for
        # per-corner UVs; the UV records follow the face block.
        fstart = _face_block(d, vcount, vend, fcount)
        recs = list(_iter_face_recs(d, vcount, fstart, fcount)) if fstart is not None else []
        base = _find_uv_base(d, (recs[-1] + 48) if recs else vend)
        if recs and base is not None:
            for ro in recs:
                a, b, c, e = u32(d, ro), u32(d, ro+4), u32(d, ro+8), u32(d, ro+12)
                if not (a < vcount and b < vcount and c < vcount and len({a, b, c}) == 3
                        and all(_finite_v(verts_all[i]) for i in (a, b, c))):
                    continue
                uv = _rec_uvs(d, base, u16(d, ro+22))
                tris.append(((a, b, c), uv))
                if e not in (a, b, c) and e < vcount and _finite_v(verts_all[e]):
                    # quad's second triangle reuses the shared corners' UVs
                    tris.append(((a, c, e), [uv[0], uv[2], uv[2]] if uv else None))
        else:
            for t in find_faces(d, vcount, vend, fcount):
                if all(_finite_v(verts_all[i]) for i in t):
                    tris.append((t, None))
    has_uv = any(uv for _, uv in tris)
    stem = os.path.splitext(os.path.basename(out_path))[0]
    vt_lines, face_lines, vti = [], [], 1
    for (a, b, c), uv in tris:
        if uv:
            for u, v in uv:
                vt_lines.append(f"vt {u:.5f} {v:.5f}")
            face_lines.append(f"f {a+1}/{vti} {b+1}/{vti+1} {c+1}/{vti+2}")
            vti += 3
        else:
            face_lines.append(f"f {a+1} {b+1} {c+1}")
    with open(out_path, 'w') as fp:
        if has_uv:
            fp.write(f"mtllib {stem}.mtl\n")
        for x, y, z in verts_all:
            fp.write(f"v {x*scale:.5f} {y*scale:.5f} {z*scale:.5f}\n")
        if vt_lines:
            fp.write("\n".join(vt_lines) + "\n")
        if has_uv:
            fp.write("usemtl mat0\n")
        fp.write("\n".join(face_lines) + "\n")
    if has_uv:
        with open(os.path.join(os.path.dirname(out_path), stem + ".mtl"), 'w') as mp:
            mp.write(f"newmtl mat0\nmap_Kd {stem}.png\n")
    return len(verts_all), len(tris), 1 if has_uv else 0

def _finite_v(v):
    return all(c == c and -1e4 < c < 1e4 for c in v)   # reject NaN/inf/garbage verts

if __name__ == '__main__':
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(os.path.basename(src))[0] + '.obj'
    nv, nf, uv = extract(src, out)
    print(f"{os.path.basename(src)}: {nv} verts, {nf} faces, UVs={'yes' if uv else 'no'} -> {out}")
