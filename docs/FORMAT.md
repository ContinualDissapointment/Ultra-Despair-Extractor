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

- **Simple (~252 models)** — the 48-byte triangle records above, in a flat run.
  Handled today.
- **Complex (~441 models)** — the **same 48-byte records**, but **interleaved with
  the vertex groups** inside the geometry section. The geometry section is bounded
  by the node's four `uint64` section pointers (right after the descriptor):
  `ptr0` = geometry start, last ptr = UV/normal float data.

**Complex layout (validated):** walk the geometry section, alternating
**vertex-groups** and **face-record runs**, accumulating vertices into one global
list; face indices are global across the groups. Each 48-byte record's first four
uint32 are `a,b,c,d` → triangle `(a,b,c)`, plus a second triangle `(a,c,d)` when
`d` is distinct (a quad). The per-vertex marker (`00 0X 00 00`, `X` = bone id) is
`0` for static props and `0x100+` for skinned objects.

This was validated end-to-end on the in-game **shield**: 32 verts / 52 faces, with
the bounding box matching a known-good reference rip on **all three axes**. The
remaining work is *parameter detection* — the vertex marker rule and the record's
count field vary per model, so the decoder must derive them per file (ideally from
the descriptor / submesh range table) rather than hardcode them.

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

---

## 3. `.btx` — textures

A `.btx` is a compressed container, magic `FC AA 55 A7`:

- `@0` magic `FC AA 55 A7`
- `@4` uint32 decompressed size
- `@8` uint32 compressed size (= file size)
- `@12` the compressed payload

The compression is a small LZ with four commands (decompress credit:
BlackDragonHunt & @FireyFly, see README):

| top bits | meaning |
|---|---|
| `1xx yyyyy` + 1 byte | copy `xx+4` bytes from output at 13-bit back-offset `y` (saved as the reuse offset) |
| `011 xxxxx` | copy `x` more bytes reusing the previous offset |
| `0100 xxxx` (+ext) + 1 byte | write `count+4` copies of the next byte (a run) |
| `000 xxxxx` / `001 …` (+ext) | copy `x` raw literal bytes from the input |

Decompressed payload:
- **PC** → a `DDS1` tag then a standard **DDS** (DXT1 / DXT5).
- **Vita** → a **GXT** (PS Vita texture); these may be double-wrapped (`GX3\0`),
  decompress again. Decode the GXT with GXTConvert / Scarlet.

Implemented in [`../btx_dec.py`](../btx_dec.py) and [`../btx_to_png.py`](../btx_to_png.py).

> Applying textures to meshes still needs **UV coordinates**, which live in a
> separate float stream (alongside normals) and are not yet exported.
