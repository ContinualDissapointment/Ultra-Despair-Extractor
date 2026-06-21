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

def find_faces(d, nv):
    """48-byte face records, found by the universal 0xffff strip-restart signature.
    First four uint32 = a,b,c,d -> triangle (a,b,c), plus (a,c,d) when d is a
    distinct valid index (a quad). Indices are global into the concatenated buffer."""
    faces = []
    o = 0
    N = len(d)
    while o + 48 <= N:
        a, b, c, e = u32(d, o), u32(d, o+4), u32(d, o+8), u32(d, o+12)
        if max(a, b, c, e) < 60000 and len({a, b, c}) == 3 and b'\xff\xff' in d[o+16:o+48]:
            if a < nv and b < nv and c < nv:
                faces.append((a, b, c))
                if e not in (a, b, c) and e < nv:
                    faces.append((a, c, e))
            o += 48
        else:
            o += 4
    return faces

def extract(path, out_path, scale=100.0):
    d = psca_blob(open(path, 'rb').read())
    # one global vertex buffer = every vertex run concatenated in file order;
    # face records index globally into it (not per-run, which was the old bug).
    verts_all = []
    for vstart, vcount in sorted(find_vertex_runs(d)):
        for i in range(vcount):
            o = vstart + i*16
            verts_all.append((f32(d, o+4), f32(d, o+12), -f32(d, o+8)))
    nv = len(verts_all)
    faces_all = [t for t in find_faces(d, nv)
                 if all(all(_finite(c) for c in verts_all[i]) for i in t)]
    with open(out_path, 'w') as fp:
        for x, y, z in verts_all:
            fp.write(f"v {x*scale:.5f} {y*scale:.5f} {z*scale:.5f}\n")
        for a, b, c in faces_all:
            fp.write(f"f {a+1} {b+1} {c+1}\n")
    return len(verts_all), len(faces_all), 0

def _finite(x):
    return x == x and -1e9 < x < 1e9   # reject NaN/inf/garbage

if __name__ == '__main__':
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(os.path.basename(src))[0] + '.obj'
    nv, nf, ns = extract(src, out)
    print(f"{os.path.basename(src)}: {nv} verts, {nf} faces, {ns} submesh-chunks -> {out}")
