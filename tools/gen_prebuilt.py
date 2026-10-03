#!/usr/bin/env python3
"""Dev-time: regenerate tools/prebuilt/<feature>_<region>.json from src/ and your own retail main.dol dumps.

    KK_DOLS=/dir/with/RQ4E78.dol,RQ4P78.dol python3 tools/gen_prebuilt.py

Needs devkitPPC to compile the hooks.  End users never run this: the patcher reads the JSON.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
import features
from dol import Dol
from regions import REGIONS

import gen_pad


def dol_for(region):
    base = os.environ.get('KK_DOLS', os.path.join(HERE, '..', 'dumps', 'dols'))
    p = os.path.join(base, region + '.dol')
    if not os.path.exists(p):
        sys.exit('set KK_DOLS to a directory holding %s.dol' % region)
    return Dol(p)


def main():
    os.makedirs(features.PREBUILT, exist_ok=True)
    ref = dol_for('RQ4E78')
    for region in REGIONS:
        dol = dol_for(region)
        if len(dol.data) != REGIONS[region]['dol_size']:
            sys.exit('%s: main.dol is %d bytes, expected %d' % (region, len(dol.data), REGIONS[region]['dol_size']))
        for name, feat in (('pad', gen_pad.build(region, dol, ref)),):
            path = os.path.join(features.PREBUILT, '%s_%s.json' % (name, region))
            with open(path, 'w') as f:
                json.dump(features.dump(feat), f, indent=1)
                f.write('\n')
            print('wrote', os.path.relpath(path), sum(len(o.payload) * 4 for o in feat.ops), 'bytes of code')


if __name__ == '__main__':
    main()
