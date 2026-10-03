"""Dev-time: disassemble a range of a retail main.dol with devkitPPC objdump.

    python3 tools/dev/disasm.py dumps/dols/R4QE01.dol 0x80375444 0x30
"""
import os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dol import Dol

def dis(path, va, n):
    d = Dol(path)
    data = d.read(va, n)
    with tempfile.NamedTemporaryFile(suffix='.bin') as f:
        f.write(data); f.flush()
        out = subprocess.run(['/opt/devkitpro/devkitPPC/bin/powerpc-eabi-objdump', '-D', '-b', 'binary', '-mpowerpc', '-M', 'gekko', '--endian=big',
                              '--adjust-vma=0x%X' % va, f.name], capture_output=True, text=True).stdout
    return '\n'.join(l for l in out.splitlines() if ':\t' in l)

if __name__ == '__main__':
    print(dis(sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)))
