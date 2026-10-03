"""Build the controller feature for one release: compile src/pad/kkpad.c for it.

Dev-time only (needs devkitPPC and your own main.dol dumps); tools/gen_prebuilt.py runs it and stores the
result in tools/prebuilt/pad_<region>.json, which is all the patcher needs.
"""
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import anchors
from layout import PAD_BASE, PAD_END, STATE
from ops import Feature, Hook

DEVKIT = os.environ.get('DEVKITPPC', '/opt/devkitpro/devkitPPC')
CC = DEVKIT + '/bin/powerpc-eabi-'
PLACEHOLDER = 0xD15B1ACE

# (hook name, anchor, what it does)
HOOKS = (
    ('KPAD', 'AfterKpad', 'after KPADRead: Classic Controller samples become Nunchuk samples, a GameCube pad writes its own'),
    ('PROBE', 'AfterProbe', 'after WPADProbe: a Classic Controller (or a pad) is reported as a Nunchuk'),
)


def compile_hook(name, defs):
    tmp = tempfile.mkdtemp(prefix='kkpad')
    D = ['-D%s=%s' % kv for kv in defs.items()] + ['-DHOOK_' + name]
    cflags = ['-O2', '-fno-unroll-loops', '-mbig-endian', '-msoft-float', '-msdata=none', '-ffreestanding', '-fno-pic',
              '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-nostdlib', '-Wall', '-Wno-unused-function',
              '-Werror']
    src = os.path.join(HERE, 'pad')
    subprocess.check_call([CC + 'gcc'] + cflags + D + ['-c', src + '/kkpad.c', '-o', tmp + '/g.o'])
    subprocess.check_call([CC + 'gcc', '-mbig-endian', '-c', '-x', 'assembler-with-cpp'] + D +
                          [src + '/hooks.S', '-o', tmp + '/h.o'])
    subprocess.check_call([CC + 'ld', '-T', src + '/link.ld', '-o', tmp + '/b.elf', tmp + '/h.o', tmp + '/g.o'])
    subprocess.check_call([CC + 'objcopy', '-O', 'binary', tmp + '/b.elf', tmp + '/b.bin'])
    # nothing but code may be left behind: any data section would be dropped by the linker script
    sec = subprocess.run([CC + 'objdump', '-h', tmp + '/g.o'], capture_output=True, text=True).stdout
    for line in sec.splitlines():
        parts = line.split()
        if len(parts) > 2 and parts[1].startswith(('.rodata', '.data', '.bss', '.sdata', '.sbss')) and int(parts[2], 16):
            raise SystemExit('%s: the C code needs a %s section, which cannot be injected' % (name, parts[1]))
    b = open(tmp + '/b.bin', 'rb').read()
    return list(struct.unpack('>%dI' % (len(b) // 4), b))


def build(region, dol, ref):
    a = anchors.resolve(ref, dol)
    defs = {
        'STATE': '0x%08Xu' % STATE,
        'SI_TYPES': '0x%08Xu' % a['SiTypes'],
        'SI_BUSY': '0x%08Xu' % a['SiBusy'],
        'SI_SHADOW': '0x%08Xu' % a['SiShadow'],
        'FN_SIGETTYPE': '0x%08Xu' % a['SIGetType'],
        'FN_OSDISABLE': '0x%08Xu' % a['OSDisableInterrupts'],
        'FN_OSRESTORE': '0x%08Xu' % a['OSRestoreInterrupts'],
    }
    ops, cur = [], PAD_BASE
    for name, anchor, note in HOOKS:
        site = a[anchor]
        orig = struct.unpack('>I', dol.read(site, 4))[0]
        w = compile_hook(name, defs)
        assert w[-1] == 0x60000000 and w[-2] == PLACEHOLDER, 'stub shape changed'
        w[-2] = orig                                            # run the displaced instruction
        w[-1] = 0                                               # the branch back, filled in on output
        ops.append(Hook(site, orig, w, cur, note=note))
        cur += (len(w) * 4 + 15) & ~15
    if cur > PAD_END:
        raise SystemExit('%s: pad code overflows its window: 0x%X > 0x%X' % (region, cur, PAD_END))
    return Feature('pad', 'Classic Controller and GameCube controller', region, ops)
