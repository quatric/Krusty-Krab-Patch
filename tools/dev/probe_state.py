"""Dev-time: dump the WPAD/KPAD state the game sees for one channel (USA addresses by default)."""
import struct

WPAD_TBL = 0x805D6170
KPAD0, KSTRIDE = 0x805BEB18, 0x524


def snap(d, chan=0, tbl=WPAD_TBL, kpad0=KPAD0):
    wp = d.u32(tbl + 4 * chan)
    w = d.read(wp, 0x9A0)
    st, fmt, dev, extfmt = struct.unpack('>i', w[0x8BC:0x8C0])[0], struct.unpack('>I', w[0x8B8:0x8BC])[0], w[0x8C1], w[0x8C2]
    idx = w[0x8C8]
    k = d.read(kpad0 + chan * KSTRIDE, KSTRIDE)
    hold, trig, rel = struct.unpack('>III', k[0:12])
    kdev = k[0x5C]
    ring_idx, ring_cnt = k[0x10E], k[0x10F]
    sf = struct.unpack('>ff', k[0x6C:0x74])
    sf2 = struct.unpack('>ff', k[0x7C:0x84])
    return dict(wpd=wp, status=st, fmt=fmt, dev=dev, extfmt=extfmt, rec_idx=idx,
                rec0=w[0xA0:0xA0 + 0x38].hex(), rec1=w[0x100:0x100 + 0x38].hex(),
                k_hold=hold, k_dev=kdev, k_ring=(ring_idx, ring_cnt), k_fs=sf, k_cl=sf2,
                k_acc=struct.unpack('>fff', k[0xC:0x18]))


def show(label, s):
    print('%-14s st=%d fmt=%d dev=%d extfmt=%d | k_hold=%04X k_dev=%d ring=%s acc=%s fs=%s cl=%s' % (
        label, s['status'], s['fmt'], s['dev'], s['extfmt'], s['k_hold'], s['k_dev'], s['k_ring'],
        tuple(round(x, 2) for x in s['k_acc']), tuple(round(x, 2) for x in s['k_fs']), tuple(round(x, 2) for x in s['k_cl'])))
    print('               rec0=%s' % s['rec0'])
    print('               rec1=%s' % s['rec1'])
