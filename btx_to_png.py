"""Convert UDG .btx textures to PNG.

PC .btx decompress to DDS (DXT1/DXT5) -> PNG via Pillow.
Vita .btx decompress to GXT; use GXTConvert (xdanieldzd) for those.

Decompression credit: BlackDragonHunt & @FireyFly (see btx_dec.py / README).
Requires Pillow for the DDS->PNG step:  pip install pillow
"""
import sys, os, btx_dec

def btx_to_png(path, out=None):
    dec = btx_dec.decompress(open(path, 'rb').read())
    if not dec:
        return None
    i = dec.find(b'DDS ')                  # PC: standard DDS sits after a 'DDS1' tag
    if i < 0:
        # Vita GXT (or unknown) -- dump raw for GXTConvert
        raw = os.path.splitext(path)[0] + '.gxt'
        open(raw, 'wb').write(dec)
        return raw
    dds = bytes(dec[i:])
    out = out or os.path.splitext(path)[0] + '.png'
    from PIL import Image
    open(out + '.dds', 'wb').write(dds)
    Image.open(out + '.dds').save(out)
    os.remove(out + '.dds')
    return out

if __name__ == '__main__':
    for p in sys.argv[1:]:
        r = btx_to_png(p)
        print(f"{os.path.basename(p)} -> {os.path.basename(r) if r else 'FAILED'}")
