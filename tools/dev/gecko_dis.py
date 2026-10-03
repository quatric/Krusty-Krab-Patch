"""Dev-time: disassemble the C2 (insert-asm) codes of a Gecko text file.

    python3 tools/dev/gecko_dis.py src/cc/R4QE01.txt
"""
import os, struct, subprocess, sys, tempfile

def parse(path):
    L = [l.split() for l in open(path).read().splitlines()[1:] if l.strip()]
    i, out = 0, []
    while i < len(L):
        a, n = L[i]; n = int(n, 16); w = []
        for j in range(n):
            w += [int(x, 16) for x in L[i + 1 + j]]
        out.append((0x80000000 | (int(a[2:], 16) & 0x1FFFFFF), w)); i += 1 + n
    return out

def dis(words, base):
    with tempfile.NamedTemporaryFile(suffix='.bin') as f:
        f.write(b''.join(struct.pack('>I', w) for w in words)); f.flush()
        out = subprocess.run(['/opt/devkitpro/devkitPPC/bin/powerpc-eabi-objdump', '-D', '-b', 'binary', '-mpowerpc', '-M', 'gekko',
                              '--endian=big', '--adjust-vma=0x%X' % base, f.name], capture_output=True, text=True).stdout
    return '\n'.join(l for l in out.splitlines() if ':\t' in l)

if __name__ == '__main__':
    for addr, w in parse(sys.argv[1]):
        print('=== C2 %08X (%d words)' % (addr, len(w)))
        print(dis(w, 0x80001800))
