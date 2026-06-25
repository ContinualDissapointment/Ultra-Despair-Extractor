# Ultra-Despair-Extractor

Tools for extracting 3D models (and the archives/textures around them) from
**Danganronpa Another Episode: Ultra Despair Girls** — the PC (Steam) release and
the original PS Vita build.

These are **tools only**. They contain no game data. You must supply your own
legally-owned copy of the game.

> **Status:** early but real. We are **not the first** to look at this — earlier
> community work (a model-viewer plugin, forum format threads, and GPU rips) blazed
> the trail; see [Prior art & acknowledgments](#prior-art--acknowledgments). What's
> new here is an **open, scriptable native extractor for the PC release** whose
> format model is documented and validated against known-good reference models.
> Simple single-mesh objects export cleanly today; complex multi-submesh characters
> are a work in progress (see [Limitations](#limitations)).

---

## What's here

| File | What it does |
|---|---|
| `cpk_extract.py` | Unpacks CRIWARE **`.cpk`** archives (incl. CRILAYLA-compressed entries). Works on PC `a1..a5.cpk` and Vita `dso_en.cpk`. |
| `bnc_to_obj.py` | Converts a model **`.bnc`** file to a Wavefront **`.obj`** mesh. |
| `btx_dec.py` | Decompresses a **`.btx`** texture container (PC → DDS, Vita → GXT). |
| `btx_to_png.py` | Converts a **`.btx`** texture to **PNG** (PC DDS path; needs Pillow). |
| `docs/FORMAT.md` | The reverse-engineered file-format notes. |

The model/archive tools are pure Python 3 stdlib. `btx_to_png.py`'s DDS→PNG step
needs Pillow (`pip install pillow`); the decompression itself is stdlib.

---

## Quick start (layman's version)

You need: a copy of the game's files, and Python 3 installed.

### 1. Find the game's archives
On the **PC version**, inside the game folder you'll see `en/a1.cpk`, `a2.cpk` …
`a5.cpk`. These are the big archives that hold everything.

### 2. Unpack an archive

```bash
python cpk_extract.py "path/to/a1.cpk"
```

This creates a `cpk_out/` folder next to the script containing the game's files,
including the 3D models, which end in **`.bnc`** (you'll find them in a `_chr`
folder — characters, props, items).

### 3. Turn a model into a `.obj`

```bash
python bnc_to_obj.py "cpk_out/en00_helmet.bnc" helmet.obj
```

It prints something like:
```
en00_helmet.bnc: 68 verts, 132 faces, 1 submesh-chunks -> helmet.obj
```

### 4. Open it
Open `helmet.obj` in **Blender** (File → Import → Wavefront (.obj) — no plugin
needed in Blender 4), or any 3D app.

> **Tip:** models are tiny (a fraction of a unit). If you see "nothing," select the
> object in the Outliner, hover the viewport, and press **Numpad `.`** (View → Frame
> Selected) to zoom to it.

---

## How the format works (the short version)

A `.bnc` is a `PSCa` container. Inside, each mesh is:

- a **vertex buffer** — 16 bytes per vertex: a 4-byte tag (skinning: bone
  index + weights) followed by an XYZ position as three 32-bit floats; and
- a **face list** — one record per triangle whose first three 32-bit integers are
  the three corner indices.

Coordinates are converted to OBJ space as `(x, z, -y)`. Full details, including the
dead ends we ruled out, are in [`docs/FORMAT.md`](docs/FORMAT.md).

The format was reverse-engineered by cross-referencing the raw files against a
handful of known-correct community rips (used purely as an "answer key" to verify
decoding — none of that data is included here).

---

## Current coverage

Models come in two geometry encodings (see [`docs/FORMAT.md`](docs/FORMAT.md)):

- **Simple format** — `bnc_to_obj.py` handles these. Several hundred `a1`
  character/prop models produce geometry that passes an automated edge-sanity check.
  **That check is not a correctness guarantee.** A sample (e.g. the helmet, shield,
  wings) were confirmed correct in Blender / against reference rips; the full set
  has *not* been visually verified — treat counts as "looks plausible," not "known
  good," and check each model you use.
- **Complex format** — appears worked out, but only spot-confirmed: a few models
  decode correctly, including the **shield** (32v / 52f, bounding box matching a
  reference rip on all three axes) and a couple others confirmed by eye. Whether
  it's correct across the whole roster is **not yet confirmed**.

## Limitations

This is a checkpoint, not a finished product. Known gaps:

- **Correctness is only spot-checked.** Only a handful of models are confirmed
  against ground truth / by eye; the rest are unverified.
- **No UVs applied yet.** Geometry exports untextured. `.btx` textures *do* decode
  to PNG (`btx_to_png.py`), but mapping them needs UVs, which are **not** working
  yet (see roadmap).
- **Multi-*node* models** (corpse piles, effects) don't decode cleanly.
- **PC build only** for the model converter. The Vita `.bnc` is a different (older)
  variant; `cpk_extract.py` already unpacks Vita archives, but `bnc_to_obj.py`
  currently targets the PC layout.

---

## Roadmap

1. ~~`.btx` texture decoding~~ — **done** (`btx_dec.py` / `btx_to_png.py`).
2. ~~**UV coordinates**~~ — **done for the simple format.** Each face record's
   `strip[1]` (uint16 at +22) is its index `X` into a 40-byte-strided UV record
   array; `recoff = base + X*40`, three per-corner `(u,v)`, V-flipped. Validated
   132/132 against a reference rip and visually on a diverse set; covers ~237 of
   the `a1` props. Complex/character models still export geometry-only.
3. ~~Material assignment~~ — **done**; `bnc_to_obj.py` emits per-corner `vt` + an
   `.mtl`. Pair textures via `<model>.btx` in the `_tex_pc` archive.
4. **UVs for complex/character models** (interleaved face records) — next.
5. Multi-*node* models (corpse piles / effects) and a full batch export.

---

## Prior art & acknowledgments

We stand on a lot of shoulders. This project would not exist without:

- **akderebur** — author of **UniViewer** and its Danganronpa UDG model-viewer
  plugin. It was the earliest attempt at *natively* parsing this game's models.
  Even though we couldn't get it running on the PC release, decompiling its parse
  logic **independently confirmed our format model** (the 16-byte vertex layout,
  the uint64 section pointers, the uint16 index data, and that the per-vertex tag
  carries skinning/bone data). Huge credit for being first into this format.
- **The XeNTaX and VG-Resource forums** — the community threads where the `.bnc` /
  `.btx` format was first discussed and sample files were shared. The questions
  asked there (and the dead ends noted) saved us real time.
- **The Internet Archive** — for preserving those now-defunct forum threads. The
  XeNTaX forum has shut down; without the Wayback Machine, that knowledge would be
  gone.
- **The Models Resource** (and the rippers who contributed UDG models) — their
  known-good rips were our **answer key**: we matched our decoded vertices and face
  counts against them to *prove* the format was decoded correctly. None of their
  data is redistributed here — it was used solely for verification.

- **BlackDragonHunt / yukinogatari** and **@FireyFly** — they reverse-engineered
  the `.btx` texture compression (the `fc aa 55 a7` container) in
  [Danganronpa-Tools](https://github.com/yukinogatari/Danganronpa-Tools)
  (`dr12ae/dr_dec.py`, WTFPL). `btx_dec.py` here is a Python-3 port of their
  algorithm. We did **not** crack this ourselves — they did, years ago.
- **xdanieldzd** — [GXTConvert](https://github.com/xdanieldzd/GXTConvert) and
  [Scarlet](https://github.com/xdanieldzd/Scarlet) decode the PS Vita **GXT**
  textures the Vita `.btx` decompress to.
- **The Textures Resource** — community-ripped UDG textures, useful as a check.

If you contributed any of the above and want different wording or attribution,
please open an issue.

---

## Legal / ethical note

This project ships **no copyrighted game content** — no models, textures, archives,
or reference rips. It is for personal use, preservation, and interoperability with
your own legally-acquired copy of the game. Danganronpa Another Episode: Ultra
Despair Girls is © Spike Chunsoft. This project is unaffiliated.

## License

MIT — see [`LICENSE`](LICENSE).
