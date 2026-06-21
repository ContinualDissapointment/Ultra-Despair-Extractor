# UDG file formats (reverse-engineered notes)

Notes on the container and model formats used by *Danganronpa Another Episode:
Ultra Despair Girls*. Offsets are little-endian. These were derived by inspection
and validated against known-correct reference meshes; treat them as "good enough to
extract with," not an official spec.

---

## 1. `.cpk` — CRIWARE CPK archive

Standard CRIWARE CPK (the same container used across many Sony-era titles).

- File starts with `CPK ` then a `@UTF` table (CRI's columnar table format) at
  offset `0x10` describing the archive (`ContentOffset`, `TocOffset`, …).
- The TOC is another `@UTF` table (after a `TOC ` tag) with one row per file:
  `DirName`, `FileName`, `FileSize`, `ExtractSize`, `FileOffset`.
- File data lives at `min(ContentOffset, TocOffset) + FileOffset`.
- If `ExtractSize > FileSize`, the entry is **CRILAYLA**-compressed.

### CRILAYLA decompression
- Header: `CRILAYLA`, uint32 `uncompressed_size`, uint32 `compressed_size`.
- Output is `uncompressed_size + 0x100` bytes. The trailing `0x100` raw bytes
  (located at `16 + compressed_size`) are the **start** of the output.
- The compressed stream is read **backwards**, MSB-first, filling the output from
  the end down to `0x100`. Each step: 1 flag bit; `1` = back-reference
  (13-bit offset+3, then variable length via 2/3/5-bit chunks then 8-bit chunks),
  `0` = literal byte.

Implemented in [`../cpk_extract.py`](../cpk_extract.py).

---

## 2. `.bnc` — model container (`PSCa`)

PC release. (Vita uses a related but different, more compact `PSCa` variant.)

### Outer wrapper
- PC files may begin with a 16-byte wrapper, magic `AC 65 12 FE`, followed by two
  section sizes; the `PSCa` data begins at offset `0x10`.
- Vita files have **no** wrapper — they start at `PSCa` directly.

### Header
- `PSCa` magic, a version/flags word, then a pointer table (uint32 offsets starting
  around `0x18`) into sub-structures: node names, a mesh/submesh descriptor, etc.
- A submesh descriptor carries, among other fields, `uint16 vertex_count` and
  `uint16 face_count`. (Example, helmet: right after the name string, the pair
  `44 00 84 00` = 68 verts, 132 faces.)

### Vertex buffer
Interleaved, **16 bytes per vertex**:

| bytes | meaning |
|---|---|
| 0–3 | tag = **skinning data** (bone index + weights). Read as byte/byte/int16. Often looks like `00 0X 00 00`, where `X` varies between submeshes because they bind to different bones — so it doubles as a rough submesh delimiter. |
| 4–15 | position: 3 × float32 (X, Y, Z) |

Convert to OBJ coordinates as **`(x, z, -y)`** (the engine is Z-up). Vertices are
in node-local space and are transformed by their node's matrix in the original
engine; for single-node objects this is identity.

> The skinning meaning of the tag was confirmed by decompiling the UniViewer UDG
> plugin (see the README acknowledgments): its vertex loop reads
> `byte, byte, int16, float×3` then feeds the tag into `boneIndex0-3` / `weight0-3`.

### Face records
A flat list of per-triangle records.

- The **first three uint32** of each record are the triangle's three vertex indices
  (into that submesh's vertex buffer). A fourth uint32 repeats the third.
- A uint32 length/count field follows; the remaining bytes are per-corner strip/UV
  data (not yet decoded).
- On simple models this count is `9` and records are a fixed **48 bytes**.

Implemented in [`../bnc_to_obj.py`](../bnc_to_obj.py).

### Two face formats
A survey of all 947 models shows **two** geometry encodings:

- **Simple (~252 models)** — the 48-byte triangle records above. Handled today.
- **Complex (~441 models)** — geometry is reached through the node's **4 section
  pointers** (uint64s right after the descriptor): `ptr0` = vertex buffer,
  `ptr2` = a **triangle-strip index buffer** (uint16, with `0xffff` restart
  markers), `ptr3` = float data (UVs/normals). This matches the UniViewer plugin's
  parser, which reads the index section as `uint16, uint16, byte` elements. Decoding
  is ~90% there (validated on `barricade`); exact strip params are being finalized.

---

## Dead ends (documented so nobody re-walks them)

- **`UniViewer` + its UDG plugin** (akderebur): does not load PC *or* Vita files in
  practice; swallows its errors; no confirmed UDG rip ever existed with it.
- **The `0x28`-prefixed "strip groups"**: looked like a primitive format but the
  `0x28` was just a vertex index that happened to equal 40 in early records.
- **Reading the vertex buffer at stride 32**: gave a partial, wrong mesh — the real
  stride is 16.
- **The clean uint16 triangle list found elsewhere in the file**: matches a *rip's*
  faces exactly but is in the **unwelded** vertex order (the file stores a welded
  buffer), so it can't index the file's own vertices.

---

## Validation method

Decoding was checked against known-good community reference meshes used purely as an
answer key: match the decoded vertex set/positions and the face count to the
reference, and visually confirm in Blender. No reference data is redistributed here.
