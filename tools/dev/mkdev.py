"""Dev-time: patch a retail main.dol with the controller feature and put it where Dolphin boots it from.

    python3 tools/dev/mkdev.py RQ4E78            # patched
    python3 tools/dev/mkdev.py RQ4E78 --clean    # retail
"""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import patcher
from dol import Dol

def main():
    region = sys.argv[1]
    src = os.path.join(ROOT, 'dumps', 'dols', region + '.dol')
    dst = os.path.join(ROOT, 'dumps', 'fst', region, 'sys', 'main.dol')
    if '--clean' in sys.argv:
        shutil.copy(src, dst)
    else:
        patcher.patch_file(src, dst, region, ['pad'])
    print('wrote', dst)

if __name__ == '__main__':
    main()
