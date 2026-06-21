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
  - geometry is laid out as submeshes: a vertex run followed by its 48-byte face records
"""
import struct, sys, os

def u32(d, o): return struct.unpack_from('<I', d, o)[0]
def f32(d, o): return struct.unpack_from('<f', d, o)[0]

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

def find_face_chunks(d):
    """contiguous runs of 48-byte face records (u32@+16 == 9)."""
    chunks = []
    o = 0
    N = len(d)
    while o + 48 <= N:
        if u32(d, o+16) == 9:
            start = o; tris = []
            while o + 48 <= N and u32(d, o+16) == 9:
                a, b, c = u32(d, o), u32(d, o+4), u32(d, o+8)
                tris.append((a, b, c)); o += 48
            chunks.append((start, tris))
        else:
            o += 4
    return chunks

def extract(path, out_path, scale=100.0):
    d = psca_blob(open(path, 'rb').read())
    vruns = find_vertex_runs(d)
    fchunks = find_face_chunks(d)
    # pair each face chunk with the nearest preceding vertex run
    verts_all = []
    faces_all = []
    for cstart, tris in fchunks:
        vrun = max((v for v in vruns if v[0] < cstart), key=lambda v: v[0], default=None)
        if vrun is None:
            continue
        vstart, vcount = vrun
        maxidx = max(max(t) for t in tris) if tris else -1
        if maxidx >= vcount:
            vcount = maxidx + 1                      # trust the indices
        base = len(verts_all)
        vcount = min(vcount, (len(d) - vstart) // 16)
        for i in range(vcount):
            o = vstart + i*16
            verts_all.append((f32(d, o+4), f32(d, o+12), -f32(d, o+8)))
        for a, b, c in tris:
            if len({a, b, c}) == 3:
                faces_all.append((a+base, b+base, c+base))
    with open(out_path, 'w') as fp:
        for x, y, z in verts_all:
            fp.write(f"v {x*scale:.5f} {y*scale:.5f} {z*scale:.5f}\n")
        for a, b, c in faces_all:
            fp.write(f"f {a+1} {b+1} {c+1}\n")
    return len(verts_all), len(faces_all), len(fchunks)

if __name__ == '__main__':
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(os.path.basename(src))[0] + '.obj'
    nv, nf, ns = extract(src, out)
    print(f"{os.path.basename(src)}: {nv} verts, {nf} faces, {ns} submesh-chunks -> {out}")
