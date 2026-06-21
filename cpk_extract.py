import struct, sys, os

def read_utf(data, base):
    assert data[base:base+4] == b'@UTF', "not @UTF at %d" % base
    size = struct.unpack_from('>I', data, base+4)[0]
    b = base + 8
    rows_off, str_off, data_off, name_off = struct.unpack_from('>IIII', data, b)
    ncols, row_w = struct.unpack_from('>HH', data, b+16)
    nrows = struct.unpack_from('>I', data, b+20)[0]
    rows_off += b; str_off += b; data_off += b
    def getstr(o):
        e = data.index(b'\x00', str_off+o)
        return data[str_off+o:e].decode('utf-8','replace')
    TYPES = {0:('B',1),1:('b',1),2:('>H',2),3:('>h',2),4:('>I',4),5:('>i',4),
             6:('>Q',8),7:('>q',8),8:('>f',4),9:('>d',8),0xA:('str',0),0xB:('data',0)}
    cols = []
    p = b + 24
    for _ in range(ncols):
        flags = data[p]; p += 1
        nm = getstr(struct.unpack_from('>I', data, p)[0]); p += 4
        const = None
        storage = flags & 0xf0
        typ = flags & 0x0f
        if storage == 0x30:  # constant
            const = read_val(data, p, typ, str_off, data_off, getstr)
            p += valsize(typ)
        cols.append((nm, typ, storage, const))
    rows = []
    for r in range(nrows):
        row = {}
        rp = rows_off + r*row_w
        for nm, typ, storage, const in cols:
            if storage == 0x30:
                row[nm] = const
            elif storage == 0x10:
                row[nm] = 0
            else:
                row[nm] = read_val(data, rp, typ, str_off, data_off, getstr)
                rp += valsize(typ)
        rows.append(row)
    return rows

def valsize(typ):
    return {0:1,1:1,2:2,3:2,4:4,5:4,6:8,7:8,8:4,9:8,0xA:4,0xB:8}[typ]

def read_val(data, p, typ, str_off, data_off, getstr):
    if typ == 0xA:
        return getstr(struct.unpack_from('>I', data, p)[0])
    if typ == 0xB:
        o, l = struct.unpack_from('>II', data, p)
        return (data_off+o, l)
    fmt = {0:'B',1:'b',2:'>H',3:'>h',4:'>I',5:'>i',6:'>Q',7:'>q',8:'>f',9:'>d'}[typ]
    return struct.unpack_from(fmt, data, p)[0]

def crilayla_decompress(src):
    if src[:8] != b'CRILAYLA':
        return src
    usize = struct.unpack_from('<I', src, 8)[0]
    csize = struct.unpack_from('<I', src, 12)[0]
    out = bytearray(usize + 0x100)
    out[0:0x100] = src[16+csize:16+csize+0x100]
    byte_pos = 16 + csize - 1
    bit_pool = 0; bits_left = 0
    def get_bits(n):
        nonlocal byte_pos, bit_pool, bits_left
        v = 0
        while n > 0:
            if bits_left == 0:
                bit_pool = src[byte_pos]; bits_left = 8; byte_pos -= 1
            take = min(bits_left, n)
            v = (v << take) | ((bit_pool >> (bits_left - take)) & ((1 << take) - 1))
            bits_left -= take; n -= take
        return v
    opos = 0x100 + usize - 1
    while opos >= 0x100:
        if get_bits(1):
            ref = opos + get_bits(13) + 3
            length = 3
            for nb in (2, 3, 5):
                t = get_bits(nb); length += t
                if t != (1 << nb) - 1:
                    break
            else:
                t = get_bits(8); length += t
                while t == 255:
                    t = get_bits(8); length += t
            for _ in range(length):
                out[opos] = out[ref]; opos -= 1; ref -= 1
        else:
            out[opos] = get_bits(8); opos -= 1
    return bytes(out)

def main():
    cpk = sys.argv[1]
    wanted = sys.argv[2:]  # filenames to extract
    data = open(cpk, 'rb').read()
    assert data[:4] == b'CPK '
    hdr = read_utf(data, 16)[0]
    content = hdr.get('ContentOffset', 0)
    toc = hdr.get('TocOffset', 0)
    # TOC @UTF is after 'TOC ' sig (16 bytes in)
    toc_utf = toc + 16
    rows = read_utf(data, toc_utf)
    base = min(content, toc) if (content and toc) else (content or toc)
    outdir = os.path.join(os.path.dirname(cpk), 'cpk_out')
    os.makedirs(outdir, exist_ok=True)
    found = 0
    for row in rows:
        name = row['FileName']
        if wanted and name not in wanted:
            continue
        off = base + row['FileOffset']
        fsize = row['FileSize']; esize = row.get('ExtractSize', fsize)
        blob = data[off:off+fsize]
        if esize > fsize and blob[:8] == b'CRILAYLA':
            blob = crilayla_decompress(blob)
        outp = os.path.join(outdir, name)
        open(outp, 'wb').write(blob)
        print(f"  extracted {name}  ({len(blob)} bytes)  first={blob[:8].hex(' ')}")
        found += 1
    print(f"done, {found} file(s)")

main()
