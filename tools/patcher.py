"""Apply the selected patches to one main.dol."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features
from dol import Dol
from ops import apply_static
from regions import REGIONS

ORDER = ('pad',)


def detect_region(dol, disc_id=None):
    """Which release this main.dol is, from its own bytes (None if unknown).

    The retail size picks the release (a patched DOL is larger) and the bytes at every site then have to be the
    retail ones or this tool's own patch.
    """
    for region, info in REGIONS.items():
        if disc_id and info['disc_id'] != disc_id:
            continue
        if len(dol.data) < info['dol_size']:
            continue
        if all(v != 'mismatch' for v in status(dol, region).values()):
            return region
    return None


def status(dol, region):
    """{feature: 'clean' | 'patched' | 'mismatch'} for each feature on this DOL."""
    out = {}
    for name in ORDER:
        if not features.available(name, region):
            continue
        f = features.load(name, region)
        if f.is_applied(dol):
            out[name] = 'patched'
        elif not f.check_pristine(dol):
            out[name] = 'clean'
        else:
            out[name] = 'mismatch'
    return out


def patch(dol, region, which):
    """Patch `dol` (a dol.Dol) in place with the features named in `which`."""
    feats = [features.load(n, region) for n in ORDER if n in which]
    if not feats:
        raise ValueError('nothing selected')
    apply_static(dol, feats)
    return [f.title for f in feats]


def patch_file(src, dst, region, which):
    dol = Dol(src)
    done = patch(dol, region, which)
    dol.save(dst)
    return done


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Patch a Creature from the Krusty Krab main.dol')
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--region', choices=sorted(REGIONS), help='default: detect')
    for n in ORDER:
        ap.add_argument('--' + n, action='store_true', help=features.TITLES[n])
    a = ap.parse_args()
    d = Dol(a.src)
    reg = a.region or detect_region(d)
    if not reg:
        sys.exit('could not identify this main.dol; pass --region')
    which = [n for n in ORDER if getattr(a, n)] or list(ORDER)
    print(reg, REGIONS[reg]['label'], '->', ', '.join(patch_file(a.src, a.dst, reg, which)))
