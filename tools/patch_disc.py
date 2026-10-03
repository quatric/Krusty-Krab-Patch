#!/usr/bin/env python3
"""Command-line twin of the GUI: patch a .wbfs/.iso in place.

    python3 tools/patch_disc.py "Mario Strikers Charged (USA).wbfs" --cc --gc
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import disc
import features


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument('image')
    for n in features.FEATURES:
        ap.add_argument('--' + n, action='store_true', help=features.TITLES[n])
    a = ap.parse_args()
    which = [n for n in features.FEATURES if getattr(a, n)] or list(features.FEATURES)
    ok = []
    disc.run_patch(a.image, print, lambda good, msg: ok.append(good), which)
    sys.exit(0 if ok and ok[0] else 1)


if __name__ == '__main__':
    main()
