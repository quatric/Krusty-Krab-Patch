"""Find the addresses the controller patch needs in any release of Creature from the Krusty Krab.

Everything is written once against the USA main.dol; the other releases share the same compiled code at other
addresses.  A function is located by matching a window of USA instructions against the target DOL with the
relocatable bits (branch displacements, address halves, load/store offsets) masked out, and it must match
exactly once.  Data addresses are then read back from the matched code (the lis + addi/load that references
them), never guessed.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dol import Dol


def mask(w):
    op = w >> 26
    if op == 18:                                   # b / bl: keep opcode, AA, LK
        return w & 0xFC000003
    if op == 16:                                   # bc: keep everything but the displacement
        return w & 0xFFFF0003
    if op in (14, 15, 24, 25, 26, 27, 28, 29):     # addi / lis / ori / oris / xori / andi
        return w & 0xFFFF0000
    if 32 <= op <= 55:                             # loads / stores: drop the displacement
        return w & 0xFFFF0000
    return w


def words(d, va, n):
    b = d.read(va, n * 4)
    return list(struct.unpack('>%dI' % n, b)) if b and len(b) == n * 4 else None


def simm(w):
    v = w & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class Finder:
    def __init__(self, ref, tgt):
        self.ref, self.tgt = ref, tgt
        self.tbase, self.tm = self._masked(tgt)

    @staticmethod
    def _masked(d):
        o, a, s, _ = [x for x in d.secs if x[3] == 1][0]          # the main text section
        return a, [mask(w) for w in struct.unpack('>%dI' % (s // 4), bytes(d.data[o:o + s]))]

    def locate(self, ref_va, n=24):
        """Address in the target of the code at ref_va; must match exactly once."""
        rm = [mask(w) for w in words(self.ref, ref_va, n)]
        hits = []
        for i in range(len(self.tm) - n):
            if self.tm[i] == rm[0] and self.tm[i:i + n] == rm:
                hits.append(self.tbase + i * 4)
        if len(hits) != 1:
            raise SystemExit('anchor %08X: %d matches in %s' % (ref_va, len(hits), self.tgt.path))
        return hits[0]

    def pair(self, ref_va, ref_target, n=64):
        """The target's value for the address that a `lis` + (addi | load | store) pair near ref_va builds
        (ref_target in the reference)."""
        t_va = self.locate(ref_va, 24)
        rw, tw = words(self.ref, ref_va, n), words(self.tgt, t_va, n)
        for i in range(n):
            w = rw[i]
            if w >> 26 != 15:
                continue
            reg = (w >> 21) & 31
            for j in range(i + 1, min(n, i + 24)):
                w2 = rw[j]
                op2 = w2 >> 26
                if (op2 == 14 or 32 <= op2 <= 55) and (w2 >> 16) & 31 == reg:
                    if ((((w & 0xFFFF) << 16) + simm(w2)) & 0xFFFFFFFF) == ref_target:
                        t, t2 = tw[i], tw[j]
                        assert t >> 26 == 15 and (t2 >> 26) == op2, 'pair shape differs'
                        return (((t & 0xFFFF) << 16) + simm(t2)) & 0xFFFFFFFF
        raise SystemExit('no pair for %08X near %08X in %s' % (ref_target, ref_va, self.tgt.path))


# (name, USA address, words to match)
FUNCS = {
    # the game's own per-frame device reader: it calls KPADRead for four channels, then WPADProbe and bPadCopy
    'ReadDevices': (0x80363314, 40),
    'SIGetType': (0x804108C0, 40),
    'SITransfer': (0x804104A4, 40),
    'OSDisableInterrupts': (0x80408B24, 6),
    'OSRestoreInterrupts': (0x80408B4C, 6),
}

# offsets inside ReadDevices of the two instructions that get hooked: the store of KPADRead's sample count (`stw
# r3,164(r21)`, r22 is the channel + 1 by then) and the join point after the WPADProbe call (`lwz r0,152(r30)`)
AFTER_KPAD = 0x54
AFTER_PROBE = 0xC4
AFTER_KPAD_INSN = 0x907500A4
AFTER_PROBE_INSN = 0x801E0098


def resolve(ref, tgt):
    f = Finder(ref, tgt)
    r = {k: f.locate(a, n) for k, (a, n) in FUNCS.items()}
    r['SiTypes'] = f.pair(0x804108C0, 0x8050DFD0)
    r['SiBusy'] = f.pair(0x804104A4, 0x8050DFB8)
    # the SI globals sit in one block, in the same order in every release: the transfer-busy flag, the SIPOLL
    # shadow right after it (SIGetType reads it as `lwz rX,4(busy base)`), then the type table
    assert r['SiBusy'] == r['SiTypes'] - 0x18, 'SI busy flag moved relative to the type table'
    assert f.pair(0x804108C0, 0x8050DFB8) == r['SiBusy'], 'SIGetType and SITransfer disagree on the busy flag'
    r['SiShadow'] = r['SiBusy'] + 4
    body = words(tgt, r['SIGetType'], 80)
    assert any(w >> 26 == 32 and simm(w) == 4 for w in body), 'SIPOLL shadow not read at busy+4'
    r['AfterKpad'] = r['ReadDevices'] + AFTER_KPAD
    r['AfterProbe'] = r['ReadDevices'] + AFTER_PROBE
    for name, insn in (('AfterKpad', AFTER_KPAD_INSN), ('AfterProbe', AFTER_PROBE_INSN)):
        got = words(tgt, r[name], 1)[0]
        assert got == insn, '%s: %08X holds %08X, expected %08X' % (name, r[name], got, insn)
    return r


if __name__ == '__main__':
    ref = Dol(sys.argv[1])
    for p in sys.argv[2:]:
        print(os.path.basename(p), {k: '%08X' % v for k, v in resolve(ref, Dol(p)).items()})
