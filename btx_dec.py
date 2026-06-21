"""Decompress UDG .btx textures (the `fc aa 55 a7` container).

Decompression algorithm ported to Python 3 from BlackDragonHunt's dr_dec.py
(yukinogatari/Danganronpa-Tools, WTFPL); format reverse-engineered by
BlackDragonHunt with help from @FireyFly. PC .btx decompress to DDS (DXT1/DXT5),
Vita .btx to GXT. Credit to them.
"""
GX3 = b'\x47\x58\x33\x00'
CMP = b'\xFC\xAA\x55\xA7'

def _u32(b, o): return b[o] | (b[o+1] << 8) | (b[o+2] << 16) | (b[o+3] << 24)

def dr_dec(data):
    if data[:4] == GX3:
        data = data[4:]
    if data[:4] != CMP:
        return None
    cmp_size = _u32(data, 8)
    res = bytearray()
    p = 12
    prev_off = 1
    while p < cmp_size:
        b = data[p]; p += 1
        if b & 0x80:                                   # 1xxyyyyy yyyyyyyy : copy from output
            b2 = data[p]; p += 1
            count = ((b >> 5) & 0b11) + 4
            offset = ((b & 0x1f) << 8) + b2
            prev_off = offset
            for _ in range(count): res.append(res[-offset])
        elif (b & 0x40) and (b & 0x20):                # 011xxxxx : continue copy, reuse offset
            for _ in range(b & 0x1f): res.append(res[-prev_off])
        elif b & 0x40:                                 # 0100xxxx[ ...] yyyyyyyy : run of one byte
            count = b & 0x0f
            if b & 0x10:
                count = (count << 8) + data[p]; p += 1
            count += 4
            val = data[p]; p += 1
            res += bytes([val]) * count
        else:                                          # 000xxxxx / 001xxxxx ... : raw literal bytes
            count = b & 0x1f
            if b & 0x20:
                count = (count << 8) + data[p]; p += 1
            res += data[p:p+count]; p += count
    return res

def decompress(data):
    """Full .btx -> raw payload (DDS for PC, GXT for Vita). Handles double-compression."""
    dec = dr_dec(data)
    if dec is not None and dec[:4] == GX3:             # double-compressed (GX3 wrapper)
        dec = dr_dec(dec[4:])
    return dec

if __name__ == '__main__':
    import sys, os
    for path in sys.argv[1:]:
        out = decompress(open(path, 'rb').read())
        dst = os.path.splitext(path)[0] + ('.dds' if out and out[:4] == b'DDS ' else '.bin')
        open(dst, 'wb').write(out)
        print(f"{os.path.basename(path)}: {len(out)} bytes -> {os.path.basename(dst)} ({out[:4]})")
