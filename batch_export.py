"""Batch-export UDG models: sweep a `_chr` folder, convert every static `.bnc`
mesh to a posed, UV-mapped `.obj` (+ `.mtl`), and auto-pair/decode its texture.

This reproduces a full model dump from an unpacked game with one command:

    python batch_export.py --chr  PATH/to/a1/.../data/_chr \
                           --tex  PATH/to/unpacked_game \
                           --out  GameModels

`--tex` is searched recursively for `.btx` textures (across all archives). The
texture step needs Pillow (`pip install pillow`); pass `--no-textures` to skip it.

WORK IN PROGRESS. Simple meshes (props, items, weapons) and skinned characters
that follow the common layout export cleanly; some complex/multi-part models may
still come out imperfect. See README "Current coverage". `_anm`/`_evt`/`_shadow`
variants are skipped on purpose — the static `.bnc` files hold the correct UVs.
"""
import os, re, glob, argparse
import bnc_to_obj

_SKIP = re.compile(r'(_anm\d*|_evt|_shadow)$', re.I)
# mask / shadow / effect texture variants are not the base colour map
_TEX_VARIANT = re.compile(r'(_msk|_sdw|_alpha|_emission|_luminous|_danger|_aura)$', re.I)
_CHAR = re.compile(r'^((?:en|enb|ev|mks|kks|pl|co)\d+[a-z]?)(?:_\w+)?$')


def index_textures(tex_root):
    """Map lower-case base-name -> .btx path for every colour texture found."""
    out = {}
    for p in glob.glob(os.path.join(tex_root, "**", "*.btx"), recursive=True):
        name = os.path.splitext(os.path.basename(p))[0]
        if _TEX_VARIANT.search(name):
            continue
        out.setdefault(name.lower(), p)
    return out


def match_texture(stem, textures):
    """Best-effort pairing of a mesh name to a texture name. Tries the exact name,
    numbered variants, directional-suffix stripping, damage/variant collapsing, and
    character-prefix fallbacks (a part -> its character's body atlas)."""
    s = stem.lower()
    cands = [s, s + "01", s + "02", s + "00", s.replace("_ac_face", "_face")]
    base = re.sub(r'_(l|r|bl|br|fl|fr)$', '', s)            # strip directional
    if base != s:
        cands += [base, base + "01", base + "00"]
    var = re.sub(r'(_body)?d\d+$', '_body', s)              # en00_bodyD1 -> en00_body
    if var != s:
        cands += [var, var + "01", var + "00", re.sub(r'd\d+$', '', s)]
    m = _CHAR.match(s)                                      # part -> character atlas
    if m:
        pre = m.group(1)
        cands += [pre, pre + "01", pre + "00", pre + "_body01", pre + "_body00",
                  pre + "_00", pre + "_body"]
    for c in cands:
        if c in textures:
            return textures[c]
    return None


def main():
    ap = argparse.ArgumentParser(description="Batch-export UDG .bnc models to textured .obj")
    ap.add_argument("--chr", required=True, help="path to an unpacked _chr model folder")
    ap.add_argument("--tex", help="root to search recursively for .btx textures")
    ap.add_argument("--out", default="GameModels", help="output folder")
    ap.add_argument("--no-textures", action="store_true", help="export geometry/UVs only")
    ap.add_argument("--scale", type=float, default=100.0)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    textures = index_textures(args.tex) if (args.tex and not args.no_textures) else {}
    btx_to_png = None
    if textures:
        try:
            import btx_to_png as _b
            btx_to_png = _b
        except Exception as e:
            print(f"(textures disabled: {e})")
            textures = {}

    files = [p for p in sorted(glob.glob(os.path.join(args.chr, "*.bnc")))
             if not _SKIP.search(os.path.splitext(os.path.basename(p))[0])]
    exported = uvd = textured = 0
    for fp in files:
        stem = os.path.splitext(os.path.basename(fp))[0]
        obj = os.path.join(args.out, stem + ".obj")
        try:
            nv, nf, uv = bnc_to_obj.extract(fp, obj, scale=args.scale)
        except Exception:
            continue
        if nf == 0:                                         # nothing decoded; drop stubs
            for ext in (".obj", ".mtl"):
                try: os.remove(os.path.join(args.out, stem + ext))
                except OSError: pass
            continue
        exported += 1
        uvd += 1 if uv else 0
        if textures and uv:
            bp = match_texture(stem, textures)
            if bp:
                try:
                    r = btx_to_png.btx_to_png(bp, os.path.join(args.out, stem + ".png"))
                    if r and str(r).endswith(".png"):
                        textured += 1
                except Exception:
                    pass
    for f in glob.glob(os.path.join(args.out, "*.dds")):    # tidy intermediate DDS
        try: os.remove(f)
        except OSError: pass
    print(f"{exported} models exported -> {args.out}")
    print(f"  with UVs:  {uvd}")
    print(f"  textured:  {textured}")


if __name__ == "__main__":
    main()
