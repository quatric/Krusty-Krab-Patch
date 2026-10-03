"""Masked byte-signature search, used at build time to carry a USA site to the
other regions (branch targets and address-like immediates are ignored)."""
import struct


def mask_word(w):
    op = w >> 26
    if op == 18:
        return w & 0xFC000003                       # b/bl/ba: ignore the displacement
    if op == 16:
        return w & 0xFFFF0003                       # bc: ignore the displacement
    if op == 15:
        return w & 0xFFE00000                       # lis: ignore the immediate
    if op in (14, 24):                              # addi / ori: ignore address-sized low halves
        imm = w & 0xFFFF
        if 0x1000 <= imm < 0xF000 and (w >> 16) & 31 != 1:
            return w & 0xFFFF0000
    if 32 <= op <= 55 and (w >> 16) & 31 in (2, 13):
        return w & 0xFFFF0000                       # small-data-area relative load/store
    return w


def find(dst, usa, addr, before, after):
    pat = [mask_word(struct.unpack('>I', usa.read(addr - 4 * before + 4 * i, 4))[0])
           for i in range(before + after)]
    n = len(pat)
    res = []
    for off, base, size, idx in dst.secs:
        if idx >= 7:
            continue
        words = struct.unpack('>%dI' % (size // 4), bytes(dst.data[off:off + size]))
        mw = [mask_word(w) for w in words]
        for k in range(len(mw) - n):
            if mw[k:k + n] == pat:
                res.append(base + 4 * (k + before))
    return res


def find_unique(usa, dst, addr, before, after):
    r = find(dst, usa, addr, before, after)
    if len(r) != 1:
        raise SystemExit('signature for 0x%08X matched %d places in %s' % (addr, len(r), dst.path))
    return r[0]
